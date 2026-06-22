"""
app/services/branch_stats.py
============================
Widget-shaped data layer for the Branches dashboard.

DESIGN PRINCIPLE:
    Each function is an independent "widget" that:
      - Takes (user, **options)
      - Uses scope_branches() / scope_loans() for security
      - Returns plain Python dicts/lists ready for templates
      - Can be rendered standalone later (Phase I: customizable home)

If you add a new attention signal or metric, ADD A NEW FUNCTION HERE.
Never put query logic inside the dashboard route or template.
"""

from datetime import date, timedelta
from sqlalchemy import func, and_, or_
from app import db
from app.models import (
    Branch, Loan, Region, ContactLog, LoanStatus, User, Borrower,
)
from app.services.access_control import (scope_branches, scope_loans, mask_personal_info,)
from app.services.goal_tracking import get_branch_goals

# ════════════════════════════════════════════════════════════════════════════
# WIDGET 1 — Top KPI summary tiles
# ════════════════════════════════════════════════════════════════════════════

def widget_branches_kpi_summary(user):
    """
    Three top-level numbers for the dashboard header tiles.
    Returns:
        {
            "total_branches": int,
            "total_cases":    int,    # delinquent loans only
            "total_overdue_amount": float,
        }
    """
    # Branches the user can see
    visible_branches = scope_branches(Branch.query, user).all()
    branch_ids = [b.id for b in visible_branches]

    # Loans within those branches (also runs through scope_loans for segment etc.)
    loans_q = scope_loans(Loan.query, user).filter(Loan.delinquency_days > 0)

    total_cases = loans_q.count()
    total_overdue = float(loans_q.with_entities(
        func.coalesce(func.sum(Loan.amount_overdue), 0)
    ).scalar() or 0)

    return {
        "total_branches":        len(branch_ids),
        "total_cases":           total_cases,
        "total_overdue_amount":  total_overdue,
    }


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 2 — Sortable branch comparison table
# ════════════════════════════════════════════════════════════════════════════

# Mapping of sort_by key → SQL order-by expression
_SORT_KEY_MAP = {
    "amount": "total_overdue_amount",
    "count":  "case_count",
    "days":   "avg_delinquency_days",
    "name":   "name",
}


def widget_branches_comparison_table(user, sort_by="amount", sort_dir="desc"):
    """
    One row per branch the user can see, with key metrics.

    Args:
        sort_by:  one of "amount" (default), "count", "days", "name"
        sort_dir: "asc" or "desc" (default "desc")

    Returns:
        [
          {
            "id": int, "name": str, "region_name": str,
            "case_count": int,
            "total_overdue_amount": float,
            "avg_delinquency_days": float,
            "high_risk_count": int,           # 90+ days
            "max_delinquency_days": int,
          },
          ...
        ]
    """
    # Validate sort args (defensive)
    if sort_by not in _SORT_KEY_MAP:
        sort_by = "amount"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    # Branches the user can see
    visible_branches = scope_branches(Branch.query, user).all()
    if not visible_branches:
        return []

    branch_ids = [b.id for b in visible_branches]

    # Build a row per branch using aggregate queries
    # Note: we run scope_loans on a base query then filter per branch — keeps
    # segment/outsourcing scope safe.
    base_loans_q = scope_loans(Loan.query, user).filter(Loan.delinquency_days > 0)

    rows = []
    for b in visible_branches:
        branch_loans = base_loans_q.filter(Loan.branch_id == b.id)

        stats = branch_loans.with_entities(
            func.count(Loan.id).label("cnt"),
            func.coalesce(func.sum(Loan.amount_overdue), 0).label("total"),
            func.coalesce(func.avg(Loan.delinquency_days), 0).label("avg_days"),
            func.coalesce(func.max(Loan.delinquency_days), 0).label("max_days"),
        ).one()

        high_risk_cnt = branch_loans.filter(
            Loan.delinquency_days >= 90
        ).count()

        rows.append({
            "id":                    b.id,
            "name":                  b.name,
            "region_name":           b.region.name if b.region else "—",
            "case_count":            int(stats.cnt or 0),
            "total_overdue_amount":  float(stats.total or 0),
            "avg_delinquency_days":  float(stats.avg_days or 0),
            "high_risk_count":       high_risk_cnt,
            "max_delinquency_days":  int(stats.max_days or 0),
        })

    # In-Python sort (clean and order-by safe across sort fields)
    sort_field = _SORT_KEY_MAP[sort_by]
    reverse = (sort_dir == "desc")
    rows.sort(key=lambda r: r[sort_field], reverse=reverse)
    return rows


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 3 — Top-N risky branches
# ════════════════════════════════════════════════════════════════════════════

def widget_top_risk_branches(user, limit=5):
    """
    Top N branches by count of high-risk (90+ day delinquent) loans.
    Used by the "Top Risk" bar-style widget.

    Returns:
        [{"id": int, "name": str, "high_risk_count": int,
          "total_overdue_amount": float}, ...]
    """
    # Reuse the comparison table (already secured), then top-N by high risk
    full = widget_branches_comparison_table(user, sort_by="amount", sort_dir="desc")
    sorted_by_risk = sorted(
        full, key=lambda r: r["high_risk_count"], reverse=True
    )
    return [
        {
            "id":                    r["id"],
            "name":                  r["name"],
            "high_risk_count":       r["high_risk_count"],
            "total_overdue_amount":  r["total_overdue_amount"],
        }
        for r in sorted_by_risk[:limit]
        if r["high_risk_count"] > 0
    ]


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 4 — Attention Signal A: high concentration of 90+ day loans
# ════════════════════════════════════════════════════════════════════════════

def widget_branches_attention_signal_a(user, days_threshold=90, count_threshold=5):
    """
    Signal A: Branches with `count_threshold`+ loans that are
    `days_threshold`+ days delinquent.

    Returns: [{"id", "name", "severe_count", "total_overdue"}, ...]
    """
    visible_branches = scope_branches(Branch.query, user).all()
    if not visible_branches:
        return []

    base_q = scope_loans(Loan.query, user).filter(
        Loan.delinquency_days >= days_threshold
    )

    out = []
    for b in visible_branches:
        bq = base_q.filter(Loan.branch_id == b.id)
        cnt = bq.count()
        if cnt < count_threshold:
            continue
        total = float(bq.with_entities(
            func.coalesce(func.sum(Loan.amount_overdue), 0)
        ).scalar() or 0)
        out.append({
            "id":             b.id,
            "name":           b.name,
            "severe_count":   cnt,
            "total_overdue":  total,
        })
    # Worst first
    out.sort(key=lambda r: r["severe_count"], reverse=True)
    return out


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 5 — Attention Signal B: TAUG cases without recent contact
# ════════════════════════════════════════════════════════════════════════════

def widget_branches_attention_signal_b(user, stale_days=14):
    """
    Signal B: branches with loans in TAUG status that have NO ContactLog
    entry in the last `stale_days` days.

    Returns: [{"id", "name", "stale_count"}, ...]
    """
    visible_branches = scope_branches(Branch.query, user).all()
    if not visible_branches:
        return []

    cutoff = date.today() - timedelta(days=stale_days)

    # Loans in TAUG status (per loan status), within user's scope
    taug_q = scope_loans(Loan.query, user).filter(
        Loan.status == LoanStatus.TRANSFERRED_TAUG
    )

    out = []
    for b in visible_branches:
        branch_taug_q = taug_q.filter(Loan.branch_id == b.id)
        taug_loan_ids = [lid for (lid,) in branch_taug_q.with_entities(Loan.id).all()]
        if not taug_loan_ids:
            continue

        # Find loans with recent contact
        recent_contacted_ids = {
            cid for (cid,) in (
                db.session.query(ContactLog.loan_id)
                  .filter(ContactLog.loan_id.in_(taug_loan_ids))
                  .filter(ContactLog.contact_date >= cutoff)
                  .distinct()
                  .all()
            )
        }

        stale_count = sum(
            1 for lid in taug_loan_ids if lid not in recent_contacted_ids
        )
        if stale_count == 0:
            continue

        out.append({
            "id":           b.id,
            "name":         b.name,
            "stale_count":  stale_count,
        })
    out.sort(key=lambda r: r["stale_count"], reverse=True)
    return out


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 6 — Attention Signal C: high average delinquency
# ════════════════════════════════════════════════════════════════════════════

def widget_branches_attention_signal_c(user, avg_days_threshold=60):
    """
    Signal C: branches whose average delinquency_days exceeds threshold.

    Returns: [{"id", "name", "avg_days", "case_count"}, ...]
    """
    visible_branches = scope_branches(Branch.query, user).all()
    if not visible_branches:
        return []

    base_q = scope_loans(Loan.query, user).filter(Loan.delinquency_days > 0)

    out = []
    for b in visible_branches:
        stats = (base_q.filter(Loan.branch_id == b.id)
                       .with_entities(
                           func.count(Loan.id),
                           func.coalesce(func.avg(Loan.delinquency_days), 0),
                       ).one())
        cnt, avg_days = stats
        avg_days = float(avg_days or 0)
        if cnt == 0 or avg_days < avg_days_threshold:
            continue
        out.append({
            "id":          b.id,
            "name":        b.name,
            "avg_days":    avg_days,
            "case_count":  int(cnt),
        })
    out.sort(key=lambda r: r["avg_days"], reverse=True)
    return out


# ════════════════════════════════════════════════════════════════════════════
# CONVENIENCE — Get all attention signals at once
# ════════════════════════════════════════════════════════════════════════════

def get_all_attention_signals(user):
    """
    Convenience: run all 3 attention signals.
    Returns: {"signal_a": [...], "signal_b": [...], "signal_c": [...]}
    """
    return {
        "signal_a": widget_branches_attention_signal_a(user),
        "signal_b": widget_branches_attention_signal_b(user),
        "signal_c": widget_branches_attention_signal_c(user),
    }


# ════════════════════════════════════════════════════════════════════════════
# APPEND TO branch_stats.py — Phase E.2 widgets (single-branch detail)
# ════════════════════════════════════════════════════════════════════════════

# Extra imports needed for these widgets — add to the top of the file if not there:
#   from datetime import date, timedelta
#   from app.models import User
#   from app.services.goal_tracking import get_branch_goals
#   from app.services.access_control import mask_personal_info


def _verify_branch_access(user, branch_id):
    """
    Raise ValueError if the user cannot see this branch.
    Used as a guard at the start of every single-branch widget.
    """
    accessible = (
        scope_branches(Branch.query, user)
        .filter(Branch.id == branch_id)
        .first()
    )
    if accessible is None:
        raise ValueError("Access denied to this branch.")
    return accessible


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 7 — Single branch summary KPIs
# ════════════════════════════════════════════════════════════════════════════

def widget_branch_summary_kpis(user, branch_id):
    """
    Top-of-page KPI tiles for ONE branch.
    Returns:
        {
            "branch":              Branch obj,
            "total_cases":         int,    # delinquent loans
            "total_overdue_amount": float,
            "active_workers_count": int,
        }
    """
    branch = _verify_branch_access(user, branch_id)

    # Loans in this branch (scope_loans applies segment/outsourcing if relevant)
    loans_q = (
        scope_loans(Loan.query, user)
        .filter(Loan.branch_id == branch_id)
        .filter(Loan.delinquency_days > 0)
    )
    total_cases = loans_q.count()
    total_overdue = float(
        loans_q.with_entities(
            func.coalesce(func.sum(Loan.amount_overdue), 0)
        ).scalar() or 0
    )

    # Active workers assigned to this branch
    active_workers = (
        User.query
        .filter(User.branch_id == branch_id, User.is_active == True)
        .count()
    )

    return {
        "branch":               branch,
        "total_cases":          total_cases,
        "total_overdue_amount": total_overdue,
        "active_workers_count": active_workers,
    }


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 8 — Annual goal progress for this branch
# ════════════════════════════════════════════════════════════════════════════

def widget_branch_goals_progress(user, branch_id):
    """
    Wraps goal_tracking.get_branch_goals() with an access check.
    Returns the list of goal dicts (one per category).
    """
    _verify_branch_access(user, branch_id)
    return get_branch_goals(branch_id)


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 9 — Worker performance leaderboard (collection KPIs)
# ════════════════════════════════════════════════════════════════════════════

def widget_branch_worker_performance(user, branch_id):
    """
    Per-worker collection performance for this branch.
    Returns a list of dicts, sorted by case_count desc.

    Each item:
        {
            "id":              int,
            "name":            str,
            "role_name":       str,
            "case_count":      int,
            "resolved_count":  int,
            "success_rate":    float (0-100),
            "contact_count":   int (last 30 days),
            "last_activity":   datetime or None,
        }
    """
    _verify_branch_access(user, branch_id)

    # All active users at this branch
    workers = (
        User.query
        .filter(User.branch_id == branch_id, User.is_active == True)
        .all()
    )
    if not workers:
        return []

    contact_cutoff = date.today() - timedelta(days=30)
    rows = []

    for w in workers:
        # Loans assigned to this worker
        assigned_q = Loan.query.filter(Loan.assigned_to == w.id)
        case_count = assigned_q.filter(Loan.delinquency_days > 0).count()
        resolved_count = assigned_q.filter(Loan.status == LoanStatus.RESOLVED).count()

        if case_count == 0 and resolved_count == 0:
            continue  # Skip workers with no loan activity at all

        success_rate = (
            (resolved_count / (case_count + resolved_count) * 100)
            if (case_count + resolved_count) > 0 else 0
        )

        # Contact activity in last 30 days
        contact_count = (
            ContactLog.query
            .filter(ContactLog.contacted_by == w.id)
            .filter(ContactLog.contact_date >= contact_cutoff)
            .count()
        )

        last_activity = (
            ContactLog.query
            .filter(ContactLog.contacted_by == w.id)
            .with_entities(func.max(ContactLog.contact_date))
            .scalar()
        )

        rows.append({
            "id":             w.id,
            "name":           w.name,
            "role_name":      w.role.name_mn if w.role else "—",
            "case_count":     case_count,
            "resolved_count": resolved_count,
            "success_rate":   round(success_rate, 1),
            "contact_count":  contact_count,
            "last_activity":  last_activity,
        })

    # Sort: most active first
    rows.sort(key=lambda r: r["case_count"], reverse=True)
    return rows


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 10 — Recent activity feed for this branch
# ════════════════════════════════════════════════════════════════════════════

def widget_branch_recent_activity(user, branch_id, limit=10):
    """
    Last N contact log entries for loans in this branch.
    Useful for the "what just happened" feed.

    Each item:
        {
            "contact_date":  datetime,
            "type":          str (contact_type.value),
            "was_reached":   bool,
            "borrower_name": str (masked if outsourcing user),
            "worker_name":   str,
            "loan_id":       int,
            "notes":         str (truncated to 80 chars),
        }
    """
    _verify_branch_access(user, branch_id)

    hide = mask_personal_info(user)

    logs = (
        ContactLog.query
        .join(Loan, ContactLog.loan_id == Loan.id)
        .filter(Loan.branch_id == branch_id)
        .order_by(ContactLog.contact_date.desc())
        .limit(limit)
        .all()
    )

    out = []
    for cl in logs:
        loan = Loan.query.get(cl.loan_id)
        borrower = Borrower.query.get(loan.borrower_id) if loan else None
        worker = User.query.get(cl.contacted_by) if cl.contacted_by else None

        if borrower and not hide:
            b_name = f"{borrower.last_name} {borrower.first_name}"
        elif borrower and hide:
            b_name = "***"
        else:
            b_name = "—"

        notes = (cl.notes or "")
        if len(notes) > 80:
            notes = notes[:77] + "..."

        out.append({
            "contact_date":  cl.contact_date,
            "type":          cl.contact_type.value if cl.contact_type else "note",
            "was_reached":   cl.was_reached,
            "borrower_name": b_name,
            "worker_name":   worker.name if worker else "—",
            "loan_id":       cl.loan_id,
            "notes":         notes,
        })

    return out
