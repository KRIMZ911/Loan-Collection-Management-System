"""
app/services/user_workload.py

Phase J.3 — User workload aggregation.

Provides a single function get_user_workload(target_user) that gathers
everything a manager needs to know about a staff member before viewing
their profile or deciding to deactivate them.

Read-only. Does not mutate. Used by:
  - GET /admin/users/<id>           (profile page)
  - GET /admin/users/<id>/deactivate (confirmation page)
"""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import or_, func

from app import db
from app.models import (
    User, Loan, ContactLog, ActionTaken, AnnualGoal, CaseTransfer,
    LoanStatus,
)


# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════════════════

# Loans in these statuses are considered "still active workload" — if the
# target user is attached to any of these, deactivating them leaves orphans.
_ACTIVE_LOAN_STATUSES = [
    LoanStatus.ACTIVE,
    LoanStatus.DELINQUENT,
    LoanStatus.RESTRUCTURED,
    LoanStatus.LEGAL,
    LoanStatus.COURT,
    LoanStatus.TRANSFERRED_TAUG,
    LoanStatus.OUTSOURCED,
]

_RECENT_DAYS = 30


# ════════════════════════════════════════════════════════════════════════════
# QUERY HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _assigned_loans_query(user_id):
    """
    Base query: all loans where this user is attached in ANY assignment slot.
    Uses OR across the 5 assignment columns.
    """
    return Loan.query.filter(
        or_(
            Loan.assigned_to == user_id,
            Loan.assigned_zm_id == user_id,
            Loan.assigned_zkha_id == user_id,
            Loan.assigned_analyst_id == user_id,
            Loan.assigned_hm_id == user_id,
        )
    )


def _active_loans_query(user_id):
    "Same as above, but restricted to active (non-closed) statuses."
    return _assigned_loans_query(user_id).filter(
        Loan.status.in_(_ACTIVE_LOAN_STATUSES)
    )


# ════════════════════════════════════════════════════════════════════════════
# COMPONENT BUILDERS
# ════════════════════════════════════════════════════════════════════════════

def _build_assignments(user_id):
    """
    Return per-slot loan counts. Useful for showing which 'hat' they wear.
    """
    return {
        "primary":  Loan.query.filter(Loan.assigned_to == user_id,
                                      Loan.status.in_(_ACTIVE_LOAN_STATUSES)).count(),
        "zm":       Loan.query.filter(Loan.assigned_zm_id == user_id,
                                      Loan.status.in_(_ACTIVE_LOAN_STATUSES)).count(),
        "zkha":     Loan.query.filter(Loan.assigned_zkha_id == user_id,
                                      Loan.status.in_(_ACTIVE_LOAN_STATUSES)).count(),
        "analyst":  Loan.query.filter(Loan.assigned_analyst_id == user_id,
                                      Loan.status.in_(_ACTIVE_LOAN_STATUSES)).count(),
        "hm":       Loan.query.filter(Loan.assigned_hm_id == user_id,
                                      Loan.status.in_(_ACTIVE_LOAN_STATUSES)).count(),
        "total_distinct": _active_loans_query(user_id).count(),
    }


def _build_overdue_summary(user_id):
    """Total MNT overdue + delinquent loan count across all assignment slots."""
    active = _active_loans_query(user_id)

    total_overdue = db.session.query(
        func.coalesce(func.sum(Loan.amount_overdue), 0)
    ).filter(Loan.id.in_(active.with_entities(Loan.id))).scalar()

    delinquent_count = active.filter(Loan.delinquency_days > 0).count()

    return {
        "total_overdue_mnt": float(total_overdue) if total_overdue else 0.0,
        "delinquent_count": delinquent_count,
    }


def _build_top_risk_loans(user_id, limit=5):
    """Top N highest-overdue loans this user owns. For drill-down links."""
    rows = (_active_loans_query(user_id)
            .filter(Loan.delinquency_days > 0)
            .order_by(Loan.amount_overdue.desc().nullslast(),
                      Loan.delinquency_days.desc())
            .limit(limit)
            .all())

    out = []
    for loan in rows:
        out.append({
            "id":               loan.id,
            "loan_account":     loan.loan_account_number,
            "borrower_name":    (f"{loan.borrower.last_name} {loan.borrower.first_name}"
                                 if loan.borrower else "—"),
            "amount_overdue":   float(loan.amount_overdue) if loan.amount_overdue else 0.0,
            "delinquency_days": loan.delinquency_days or 0,
            "branch_name":      loan.branch.name if loan.branch else "—",
        })
    return out


def _build_recent_activity(user_id):
    """Contact logs, actions, transfers in the last 30 days."""
    cutoff = date.today() - timedelta(days=_RECENT_DAYS)

    contact_total = ContactLog.query.filter(
        ContactLog.contacted_by == user_id,
        ContactLog.contact_date >= cutoff,
    ).count()

    action_total = ActionTaken.query.filter(
        ActionTaken.performed_by == user_id,
        ActionTaken.performed_at >= cutoff,
    ).count()

    transfer_total = CaseTransfer.query.filter(
        CaseTransfer.from_user_id == user_id,
        CaseTransfer.transfer_date >= cutoff,
    ).count() if hasattr(CaseTransfer, "transfer_date") else 0

    return {
        "contact_logs":    contact_total,
        "actions_taken":   action_total,
        "case_transfers":  transfer_total,
        "window_days":     _RECENT_DAYS,
    }


def _build_goals_managed(user_id):
    """Annual goals this user has created or edited (non-deleted)."""
    set_count = AnnualGoal.query.filter(
        AnnualGoal.set_by_user_id == user_id,
        AnnualGoal.deleted_at.is_(None),
    ).count()
    edited_count = AnnualGoal.query.filter(
        AnnualGoal.updated_by_user_id == user_id,
        AnnualGoal.deleted_at.is_(None),
    ).count()
    return {"set": set_count, "edited": edited_count}


def _compute_danger_level(assignments, overdue_summary):
    """
    Decide which banner to show on the deactivate page.
    - "none": no active loans → safe to deactivate
    - "low":  1–5 active loans, no big overdue → reassignment needed but small
    - "high": >5 active loans OR >10M MNT overdue → reassign FIRST, then deactivate
    """
    total = assignments["total_distinct"]
    overdue = overdue_summary["total_overdue_mnt"]

    if total == 0:
        return "none"
    if total <= 5 and overdue < 10_000_000:
        return "low"
    return "high"


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════════════

def get_user_workload(target_user):
    """
    Aggregate everything we want to show on the user profile and
    deactivation confirmation pages.

    Returns a dict (never None). Empty fields default to 0 / [] so
    templates can render unconditionally without {% if %} guards.
    """
    if target_user is None:
        return _empty_workload()

    uid = target_user.id

    assignments     = _build_assignments(uid)
    overdue_summary = _build_overdue_summary(uid)

    return {
        "user_id":         uid,
        "assignments":     assignments,
        "overdue_summary": overdue_summary,
        "top_risk_loans":  _build_top_risk_loans(uid, limit=5),
        "recent_activity": _build_recent_activity(uid),
        "goals_managed":   _build_goals_managed(uid),
        "danger_level":    _compute_danger_level(assignments, overdue_summary),
    }


def _empty_workload():
    "Fallback shape — never crashes templates."
    return {
        "user_id":         None,
        "assignments":     {"primary": 0, "zm": 0, "zkha": 0, "analyst": 0,
                            "hm": 0, "total_distinct": 0},
        "overdue_summary": {"total_overdue_mnt": 0.0, "delinquent_count": 0},
        "top_risk_loans":  [],
        "recent_activity": {"contact_logs": 0, "actions_taken": 0,
                            "case_transfers": 0, "window_days": _RECENT_DAYS},
        "goals_managed":   {"set": 0, "edited": 0},
        "danger_level":    "none",
    }