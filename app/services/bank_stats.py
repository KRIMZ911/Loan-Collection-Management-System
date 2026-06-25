"""
app/services/bank_stats.py
===========================
Widget-shaped data layer for the BANK dashboard (executives only).

DESIGN PRINCIPLE:
    Each widget function:
      - Takes (user, **options)
      - Uses scope helpers (scope_branches, scope_loans) for security
      - Returns plain Python dicts/lists ready for templates
      - Can be rendered standalone later (Phase I customizable home)
"""

from datetime import date, timedelta
from sqlalchemy import func, extract, and_

from app import db
from app.models import (
    Branch, Loan, Region,
    DelinquencyHistory, LoanStatus,
    GoalCategory, AnnualGoal,
)
from app.services.access_control import scope_branches, scope_loans
from app.services.goal_tracking import count_achievements


# ════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _get_visible_branch_ids(user):
    """List of branch IDs this user can see (via scope_branches)."""
    return [b.id for b in scope_branches(Branch.query, user).all()]


def _get_visible_region_ids(user):
    """List of region IDs derived from the user's visible branches."""
    branch_ids = _get_visible_branch_ids(user)
    if not branch_ids:
        return []
    region_ids = (
        db.session.query(Branch.region_id)
        .filter(Branch.id.in_(branch_ids))
        .distinct()
        .all()
    )
    return [r[0] for r in region_ids if r[0] is not None]


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 1 — Bank-wide goal aggregate
# ════════════════════════════════════════════════════════════════════════════

def widget_bank_goals_aggregate(user, year=None):
    """Roll up annual goals across all branches the user can see."""
    year = year or date.today().year
    branch_ids = _get_visible_branch_ids(user)

    if not branch_ids:
        return []

    categories = (
        GoalCategory.query
        .filter_by(is_active=True)
        .order_by(GoalCategory.sort_order, GoalCategory.id)
        .all()
    )

    result = []
    for cat in categories:
        target_sum = (
            db.session.query(func.coalesce(func.sum(AnnualGoal.target_count), 0))
            .filter(
                AnnualGoal.category_id == cat.id,
                AnnualGoal.year == year,
                AnnualGoal.branch_id.in_(branch_ids),
                AnnualGoal.deleted_at.is_(None),
            )
            .scalar() or 0
        )

        branches_with_goals = (
            db.session.query(func.count(AnnualGoal.id))
            .filter(
                AnnualGoal.category_id == cat.id,
                AnnualGoal.year == year,
                AnnualGoal.branch_id.in_(branch_ids),
                AnnualGoal.deleted_at.is_(None),
            )
            .scalar() or 0
        )

        achieved_sum = 0
        for bid in branch_ids:
            achieved_sum += count_achievements(cat.code, bid, year)

        percentage = (
            (achieved_sum / target_sum * 100)
            if target_sum > 0 else None
        )

        result.append({
            "category":            cat,
            "total_target":        int(target_sum),
            "total_achieved":      int(achieved_sum),
            "percentage":          percentage,
            "branches_with_goals": int(branches_with_goals),
            "branches_total":      len(branch_ids),
        })

    return result


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 2 — Per-region comparison
# ════════════════════════════════════════════════════════════════════════════

def widget_regions_comparison(user):
    """Per-region performance summary for executive overview."""
    region_ids = _get_visible_region_ids(user)
    if not region_ids:
        return []

    branch_ids = _get_visible_branch_ids(user)
    if not branch_ids:
        return []

    regions = Region.query.filter(Region.id.in_(region_ids)).all()

    branch_to_region = {
        b.id: b.region_id
        for b in Branch.query.filter(Branch.id.in_(branch_ids)).all()
    }

    base_loans = (
        scope_loans(Loan.query, user)
        .filter(Loan.delinquency_days > 0)
    )

    result = []
    for region in regions:
        region_branch_ids = [
            bid for bid, rid in branch_to_region.items()
            if rid == region.id
        ]
        if not region_branch_ids:
            continue

        loan_stats = (
            base_loans.filter(Loan.branch_id.in_(region_branch_ids))
            .with_entities(
                func.count(Loan.id).label("cnt"),
                func.coalesce(func.sum(Loan.amount_overdue), 0).label("total"),
                func.coalesce(func.avg(Loan.delinquency_days), 0).label("avg_days"),
            )
            .one()
        )

        high_risk_count = (
            base_loans
            .filter(Loan.branch_id.in_(region_branch_ids))
            .filter(Loan.delinquency_days >= 90)
            .count()
        )

        result.append({
            "id":                   region.id,
            "name":                 region.name,
            "branch_count":         len(region_branch_ids),
            "total_cases":          int(loan_stats.cnt or 0),
            "total_overdue_amount": float(loan_stats.total or 0),
            "avg_delinquency_days": float(loan_stats.avg_days or 0),
            "high_risk_count":      high_risk_count,
        })

    result.sort(key=lambda r: r["total_overdue_amount"], reverse=True)
    return result


# ════════════════════════════════════════════════════════════════════════════
# WIDGET 3 — Bank-wide delinquency trend
# ════════════════════════════════════════════════════════════════════════════

_MN_MONTHS = {
    1:  "1-р сар",  2:  "2-р сар",  3:  "3-р сар",
    4:  "4-р сар",  5:  "5-р сар",  6:  "6-р сар",
    7:  "7-р сар",  8:  "8-р сар",  9:  "9-р сар",
    10: "10-р сар", 11: "11-р сар", 12: "12-р сар",
}


def widget_bank_delinquency_trend(user, months_back=6):
    """Monthly delinquent loan counts for the last N months."""
    branch_ids = _get_visible_branch_ids(user)
    if not branch_ids:
        return []

    today = date.today()

    months = []
    y, m = today.year, today.month
    for _ in range(months_back):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()

    result = []
    for year, month in months:
        if month == 12:
            month_end = date(year, 12, 31)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        if month_end > today:
            month_end = today

        latest_per_loan = (
            db.session.query(
                DelinquencyHistory.loan_id,
                func.max(DelinquencyHistory.snapshot_date).label("latest_date"),
            )
            .filter(DelinquencyHistory.snapshot_date <= month_end)
            .group_by(DelinquencyHistory.loan_id)
            .subquery()
        )

        month_query = (
            db.session.query(DelinquencyHistory)
            .join(
                latest_per_loan,
                and_(
                    DelinquencyHistory.loan_id == latest_per_loan.c.loan_id,
                    DelinquencyHistory.snapshot_date == latest_per_loan.c.latest_date,
                ),
            )
            .join(Loan, DelinquencyHistory.loan_id == Loan.id)
            .filter(Loan.branch_id.in_(branch_ids))
            .filter(DelinquencyHistory.delinquency_days > 0)
        )

        snapshots = month_query.all()
        delinquent_count = len(snapshots)
        total_overdue = sum(float(s.amount_overdue or 0) for s in snapshots)

        result.append({
            "month_label":          _MN_MONTHS.get(month, str(month)),
            "year_month":           f"{year}-{month:02d}",
            "delinquent_count":     delinquent_count,
            "total_overdue_amount": total_overdue,
        })

    return result


# ════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ════════════════════════════════════════════════════════════════════════════

def get_all_bank_widgets(user, months_back=6, year=None):
    """Fetch all 3 bank dashboard widgets in one call."""
    return {
        "goals_aggregate":    widget_bank_goals_aggregate(user, year=year),
        "regions_comparison": widget_regions_comparison(user),
        "delinquency_trend":  widget_bank_delinquency_trend(user, months_back=months_back),
    }
