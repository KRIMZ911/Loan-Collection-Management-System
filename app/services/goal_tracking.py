"""
app/services/goal_tracking.py
==============================
The counting brain for annual goals.

For each KPI category (savings_accounts, credit_cards, new_loans), this module
knows how to:
  1. Count actual achievements from the database (count_achievements)
  2. Compute pace status (compute_pace_status)
  3. Project where the branch will end up (project_year_end)

ADDING A NEW CATEGORY (later):
  1. Insert a row into goal_categories table
  2. Add a new elif branch in count_achievements()
  3. Done — UI auto-shows it
"""

from datetime import date, timedelta
from sqlalchemy import extract, func
from app import db
from app.models import (
    GoalCategory, AnnualGoal,
    Branch, Borrower, Loan, LoanProduct,
    DepositAccount, DepositAccountType,
)


# ════════════════════════════════════════════════════════════════════════════
# 1) COUNT ACHIEVEMENTS — per category
# ════════════════════════════════════════════════════════════════════════════

def count_achievements(category_code: str, branch_id: int, year: int) -> int:
    """
    Count how many of this category were achieved at this branch this year.
    Returns 0 for unknown categories.
    """

    # 💰 Savings accounts opened
    if category_code == "savings_accounts":
        return (
            db.session.query(func.count(DepositAccount.id))
            .join(Borrower, DepositAccount.borrower_id == Borrower.id)
            .filter(
                Borrower.branch_id == branch_id,
                DepositAccount.account_type == DepositAccountType.SAVINGS,
                extract("year", DepositAccount.opened_date) == year,
            )
            .scalar() or 0
        )

    # 💳 Credit cards issued
    if category_code == "credit_cards":
        return (
            db.session.query(func.count(Loan.id))
            .join(LoanProduct, Loan.loan_product_id == LoanProduct.id)
            .filter(
                Loan.branch_id == branch_id,
                LoanProduct.name.ilike("%карт%"),
                extract("year", Loan.disbursement_date) == year,
            )
            .scalar() or 0
        )

    # 📑 New loans (any product type)
    if category_code == "new_loans":
        return (
            db.session.query(func.count(Loan.id))
            .filter(
                Loan.branch_id == branch_id,
                extract("year", Loan.disbursement_date) == year,
            )
            .scalar() or 0
        )

    # Unknown category — return 0 (don't crash)
    return 0


# ════════════════════════════════════════════════════════════════════════════
# 2) PACE STATUS COMPUTATION
# ════════════════════════════════════════════════════════════════════════════

# Pace thresholds (ratio of achieved vs expected based on days elapsed)
_PACE_LEVELS = [
    (1.10, {"code": "ahead",    "label": "🚀 Зорилтоо давж байна", "color": "#16A34A", "icon": "🚀"}),
    (0.95, {"code": "on_pace",  "label": "✅ Хэвийн хурдтай",      "color": "#22C55E", "icon": "✅"}),
    (0.80, {"code": "behind",   "label": "⚠️ Хоцорч буй",          "color": "#F59E0B", "icon": "⚠️"}),
    (0.00, {"code": "critical", "label": "🚨 Удааширсан",          "color": "#DC2626", "icon": "🚨"}),
]


def compute_pace_status(achieved: int, target: int, today=None) -> dict:
    """
    Compute pace status given current achievement vs target.

    Returns:
        {
            "code": "ahead" | "on_pace" | "behind" | "critical",
            "label": str (Mongolian, with icon),
            "color": str (hex),
            "icon":  str (emoji),
            "days_elapsed": int,
            "days_total":   int,
            "days_remaining": int,
            "expected_count": float (where they SHOULD be today),
            "ratio": float (actual / expected),
        }
    """
    today = today or date.today()
    year = today.year
    year_start = date(year, 1, 1)
    year_end   = date(year, 12, 31)

    days_elapsed   = (today - year_start).days + 1
    days_total     = (year_end - year_start).days + 1
    days_remaining = max(0, (year_end - today).days)

    if target is None or target <= 0:
        # No meaningful target — return neutral
        return {
            "code": "no_target",
            "label": "Зорилт тогтоогдоогүй",
            "color": "#94A3B8",
            "icon": "—",
            "days_elapsed": days_elapsed,
            "days_total": days_total,
            "days_remaining": days_remaining,
            "expected_count": 0,
            "ratio": 0,
        }

    expected = target * (days_elapsed / days_total)
    ratio = (achieved / expected) if expected > 0 else 0

    # Pick the bucket
    for threshold, status in _PACE_LEVELS:
        if ratio >= threshold:
            result = dict(status)  # shallow copy
            result.update({
                "days_elapsed":   days_elapsed,
                "days_total":     days_total,
                "days_remaining": days_remaining,
                "expected_count": expected,
                "ratio":          ratio,
            })
            return result

    # Fallback (shouldn't reach here since 0.00 always matches)
    fallback = dict(_PACE_LEVELS[-1][1])
    fallback.update({
        "days_elapsed":   days_elapsed,
        "days_total":     days_total,
        "days_remaining": days_remaining,
        "expected_count": expected,
        "ratio":          ratio,
    })
    return fallback


# ════════════════════════════════════════════════════════════════════════════
# 3) YEAR-END PROJECTION
# ════════════════════════════════════════════════════════════════════════════

def project_year_end(achieved: int, today=None) -> int:
    """
    Linear projection: if current pace continues, where will this end at year-end?
    Returns 0 if year just started (days_elapsed == 0).
    """
    today = today or date.today()
    year = today.year
    year_start = date(year, 1, 1)
    year_end   = date(year, 12, 31)

    days_elapsed = (today - year_start).days + 1
    days_total   = (year_end - year_start).days + 1

    if days_elapsed <= 0:
        return 0
    return int(achieved * (days_total / days_elapsed))


# ════════════════════════════════════════════════════════════════════════════
# 4) GET BRANCH GOALS — the main dashboard helper
# ════════════════════════════════════════════════════════════════════════════

def get_branch_goals(branch_id: int, year: int = None) -> list:
    """
    Return a list of goal dicts for one branch, one per active GoalCategory.

    Each item:
        {
            "category": GoalCategory obj,
            "goal":     AnnualGoal obj or None,
            "target":   int or None,
            "achieved": int,
            "percentage": float (0-100+) or None,
            "has_goal": bool,
            "pace_status": dict (from compute_pace_status),
            "projected_year_end": int,
            "remaining": int (target - achieved, or 0 if no target),
        }
    """
    year = year or date.today().year

    categories = (
        GoalCategory.query
        .filter_by(is_active=True)
        .order_by(GoalCategory.sort_order, GoalCategory.id)
        .all()
    )

    existing_goals = {
    g.category_id: g
    for g in AnnualGoal.query.filter_by(branch_id=branch_id, year=year)
                            .filter(AnnualGoal.deleted_at.is_(None))   # 🆕 ignore soft-deleted
                            .all()
    }

    result = []
    for cat in categories:
        goal     = existing_goals.get(cat.id)
        target   = goal.target_count if goal else None
        achieved = count_achievements(cat.code, branch_id, year)

        if target and target > 0:
            percentage = (achieved / target) * 100
            remaining = max(0, target - achieved)
        else:
            percentage = None
            remaining = 0

        pace = compute_pace_status(achieved, target)
        projected = project_year_end(achieved) if target else 0

        result.append({
            "category":           cat,
            "goal":               goal,
            "target":             target,
            "achieved":           achieved,
            "percentage":         percentage,
            "has_goal":           goal is not None,
            "pace_status":        pace,
            "projected_year_end": projected,
            "remaining":          remaining,
        })

    return result


# ════════════════════════════════════════════════════════════════════════════
# 5) BULK HELPER — many branches at once
# ════════════════════════════════════════════════════════════════════════════

def get_all_branch_goals_summary(branch_ids: list, year: int = None) -> dict:
    """
    Convenience: get goal summaries for multiple branches at once.
    Used later by the Regional dashboard.

    Returns: {branch_id: [goal_dict, goal_dict, ...]}
    """
    year = year or date.today().year
    return {
        bid: get_branch_goals(bid, year)
        for bid in branch_ids
    }
