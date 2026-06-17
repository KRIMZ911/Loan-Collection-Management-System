"""
Risk Scoring Engine for the Collection System.
Calculates a 0-100 risk score based on configurable weighted factors.
Higher score = higher risk = needs attention first.

Architecture:
- Config-driven: all weights and thresholds live in SCORING_CONFIG
- Pure functions: no side effects, easy to test
- Extensible: add new factors by adding to FACTORS dict

Updated for new models.py:
  - CollectionCase → Loan  (Loan is now THE central table)
  - CaseAction → ContactLog  (contact history)
  - case.days_overdue → loan.delinquency_days
  - case.overdue_amount → loan.amount_overdue (Decimal)
  - case.status (string) → loan.status (LoanStatus enum)

Usage:
    from app.services.scoring import score_cases
    scored = score_cases(cases_with_data)  # returns list with risk_info attached
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app import db
from app.models import Loan, ContactLog, LoanStatus


# ─── Risk Level Definitions ──────────────────────────────────
# Each level defines display properties used by templates & CSS.

RISK_LEVELS = {
    "critical": {
        "level": "critical",
        "color": "#DC2626",
        "emoji": "\U0001f534",
        "label_mn": "Маш өндөр",
        "label_en": "Critical",
        "css_class": "risk-critical",
    },
    "high": {
        "level": "high",
        "color": "#EA580C",
        "emoji": "\U0001f7e0",
        "label_mn": "Өндөр",
        "label_en": "High",
        "css_class": "risk-high",
    },
    "medium": {
        "level": "medium",
        "color": "#CA8A04",
        "emoji": "\U0001f7e1",
        "label_mn": "Дунд",
        "label_en": "Medium",
        "css_class": "risk-medium",
    },
    "low": {
        "level": "low",
        "color": "#16A34A",
        "emoji": "\U0001f7e2",
        "label_mn": "Бага",
        "label_en": "Low",
        "css_class": "risk-low",
    },
}


# ─── Scoring Configuration ───────────────────────────────────
# Adjust weights and thresholds here without touching any logic.

SCORING_CONFIG = {
    # Factor weights (must sum to 1.0)
    "weights": {
        "days_overdue": 0.40,   # Heaviest — time is money
        "overdue_amount": 0.25, # Larger amounts = more risk
        "action_recency": 0.20, # Stale cases need attention
        "status": 0.15,         # Some statuses are inherently riskier
    },
}


# ─── Factor Scoring Functions ────────────────────────────────
# Each returns a raw score (0-100) for a single factor.

def _score_days_overdue(days: int) -> int:
    """More overdue days -> higher risk."""
    if days <= 0:
        return 0
    elif days <= 5:
        return 10
    elif days <= 10:
        return 25
    elif days <= 20:
        return 40
    elif days <= 30:
        return 55
    elif days <= 60:
        return 70
    elif days <= 90:
        return 80
    elif days <= 180:
        return 90
    else:
        return 100


def _score_overdue_amount(amount: float) -> int:
    """Larger overdue amounts -> higher risk. Amount is in MNT."""
    if amount <= 0:
        return 0
    elif amount < 1_000_000:
        return 15
    elif amount < 5_000_000:
        return 30
    elif amount < 10_000_000:
        return 50
    elif amount < 50_000_000:
        return 70
    elif amount < 100_000_000:
        return 85
    else:
        return 100


def _score_action_recency(last_action_date: Optional[datetime]) -> int:
    """Cases without recent action need attention."""
    if last_action_date is None:
        return 80  # Never contacted — high risk

    now = datetime.now(timezone.utc)
    # Handle naive datetimes from the DB
    if last_action_date.tzinfo is None:
        elapsed = now.replace(tzinfo=None) - last_action_date
    else:
        elapsed = now - last_action_date

    days_since = elapsed.days

    if days_since > 14:
        return 70
    elif days_since > 7:
        return 50
    elif days_since > 3:
        return 30
    else:
        return 10


def _score_status(status: Any) -> int:
    """Certain loan statuses carry inherent risk."""
    # Handle both LoanStatus enum and plain strings
    status_val = status.value if hasattr(status, "value") else str(status)

    status_scores = {
        "active": 0,
        "delinquent": 30,
        "restructured": 40,
        "outsourced": 50,
        "transferred_taug": 60,
        "legal": 70,
        "court": 80,
        "written_off": 90,
        "closed": 0,
        "resolved": 0,
    }
    return status_scores.get(status_val, 30)


# ─── Core Scoring Function ───────────────────────────────────

def calculate_risk_score(
    loan: Loan,
    last_action_date: Optional[datetime] = None,
) -> dict:
    """
    Calculate the composite risk score for a single loan.

    Args:
        loan: Loan model instance (THE central table — has all delinquency fields)
        last_action_date: datetime of the most recent ContactLog entry for this loan

    Returns:
        dict with keys: score, level, risk_level (display props), factors (breakdown)
    """
    weights = SCORING_CONFIG["weights"]

    # Calculate individual factor scores
    days_score = _score_days_overdue(loan.delinquency_days or 0)
    amount_score = _score_overdue_amount(
        float(loan.amount_overdue) if loan.amount_overdue else 0
    )
    recency_score = _score_action_recency(last_action_date)
    status_score = _score_status(loan.status)

    # Weighted composite
    composite = (
        days_score * weights["days_overdue"]
        + amount_score * weights["overdue_amount"]
        + recency_score * weights["action_recency"]
        + status_score * weights["status"]
    )
    score = round(composite)

    # Determine risk level
    if score >= 75:
        level = "critical"
    elif score >= 50:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"

    return {
        "score": score,
        "level": level,
        "risk_level": RISK_LEVELS[level],
        "factors": {
            "days_overdue": {"raw": days_score, "weighted": round(days_score * weights["days_overdue"])},
            "overdue_amount": {"raw": amount_score, "weighted": round(amount_score * weights["overdue_amount"])},
            "action_recency": {"raw": recency_score, "weighted": round(recency_score * weights["action_recency"])},
            "status": {"raw": status_score, "weighted": round(status_score * weights["status"])},
        },
    }


# ─── Batch Scoring Function ──────────────────────────────────

def score_cases(
    cases_with_data: list[tuple],
) -> list[tuple]:
    """
    Score a batch of loans efficiently.

    Args:
        cases_with_data: list of (loan, borrower) tuples

    Returns:
        list of (loan, borrower, risk_info) tuples, sorted by score descending
    """
    if not cases_with_data:
        return []

    # Batch-fetch latest contact dates for all loans in one query
    loan_ids = [loan.id for loan, _ in cases_with_data]

    from sqlalchemy import func

    latest_contacts = dict(
        db.session.query(
            ContactLog.loan_id,
            func.max(ContactLog.contact_date),
        )
        .filter(ContactLog.loan_id.in_(loan_ids))
        .group_by(ContactLog.loan_id)
        .all()
    )

    # Score each loan
    scored = []
    for loan, borrower in cases_with_data:
        last_action = latest_contacts.get(loan.id)
        risk_info = calculate_risk_score(loan, last_action)
        scored.append((loan, borrower, risk_info))

    # Sort by score descending (highest risk first)
    scored.sort(key=lambda x: -x[2]["score"])

    return scored


def get_priority_order(risk_info: dict) -> int:
    """Return a sort key for ordering (higher score = earlier in list)."""
    return -risk_info.get("score", 0)
