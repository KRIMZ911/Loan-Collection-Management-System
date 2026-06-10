"""
Risk Scoring Engine for Collection Cases.

Calculates a 0-100 risk score based on configurable weighted factors.
Higher score = higher risk = needs attention first.

Architecture:
    - Config-driven: all weights and thresholds live in SCORING_CONFIG
    - Pure functions: no side effects, easy to test
    - Extensible: add new factors by adding to FACTORS dict

Usage:
    from app.services.scoring import score_cases
    scored = score_cases(cases_with_data)  # returns list with risk_info attached
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from app import db
from app.models import CaseAction, CollectionCase


# ─── Risk Level Definitions ──────────────────────────────────
# Each level defines display properties used by templates & CSS.

RISK_LEVELS = {
    "critical": {
        "level": "critical",
        "color": "#DC2626",
        "emoji": "🔴",
        "label_mn": "Маш өндөр",
        "label_en": "Critical",
        "css_class": "risk-critical",
    },
    "high": {
        "level": "high",
        "color": "#EA580C",
        "emoji": "🟠",
        "label_mn": "Өндөр",
        "label_en": "High",
        "css_class": "risk-high",
    },
    "medium": {
        "level": "medium",
        "color": "#CA8A04",
        "emoji": "🟡",
        "label_mn": "Дунд",
        "label_en": "Medium",
        "css_class": "risk-medium",
    },
    "low": {
        "level": "low",
        "color": "#16A34A",
        "emoji": "🟢",
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

    # Level thresholds (score >= threshold → level)
    "thresholds": {
        "critical": 75,
        "high": 50,
        "medium": 25,
        "low": 0,
    },
}


# ─── Factor Scoring Functions ────────────────────────────────
# Each returns a raw score (0-100) for a single factor.
# Keeping them separate makes testing and tuning straightforward.

def _score_days_overdue(days: int) -> int:
    """More overdue days → higher risk.

    Brackets based on standard banking delinquency buckets:
    - 0-30:   Early stage, soft collection
    - 31-60:  Escalation stage
    - 61-90:  Pre-legal stage
    - 91-120: Legal consideration
    - 120+:   Critical delinquency
    """
    if days <= 30:
        return 5
    elif days <= 60:
        return 20
    elif days <= 90:
        return 40
    elif days <= 120:
        return 55
    else:
        return 70


def _score_overdue_amount(amount: float) -> int:
    """Larger overdue amounts → higher risk.

    Thresholds calibrated for Mongolian Tugrik (MNT):
    - <5M:     Small consumer loan
    - 5-20M:   Typical consumer loan
    - 20-50M:  Large consumer / small SME
    - 50-200M: SME range
    - 200M+:   Corporate exposure
    """
    if amount < 5_000_000:
        return 5
    elif amount < 20_000_000:
        return 20
    elif amount < 50_000_000:
        return 40
    elif amount < 200_000_000:
        return 60
    else:
        return 80


def _score_action_recency(last_action_date: Optional[datetime]) -> int:
    """Cases without recent action need attention.

    No action taken = highest risk in this factor.
    Recent action = collector is actively working it.
    """
    if last_action_date is None:
        return 80  # Never been touched

    days_since = (datetime.utcnow() - last_action_date).days

    if days_since <= 3:
        return 5
    elif days_since <= 7:
        return 20
    elif days_since <= 14:
        return 40
    elif days_since <= 30:
        return 60
    else:
        return 80


def _score_status(status: str) -> int:
    """Certain case statuses carry inherent risk.

    - resolved/promise: low risk (progress made)
    - new/contacted: moderate (work started)
    - no_answer/transferred: high (stuck)
    - legal/court: critical (escalated)
    """
    status_scores = {
        "resolved": 0,
        "promise": 15,
        "contacted": 25,
        "new": 40,
        "no_answer": 60,
        "transferred": 50,
        "outsourced": 45,
        "legal": 70,
        "court": 80,
    }
    return status_scores.get(status, 40)


# ─── Core Scoring Function ───────────────────────────────────

def calculate_risk_score(
    case: CollectionCase,
    loan: Any = None,
    last_action_date: Optional[datetime] = None,
) -> dict:
    """Calculate the composite risk score for a single collection case.

    Args:
        case: CollectionCase model instance (or any object with
              days_overdue, overdue_amount, status attributes)
        loan: Optional Loan object (reserved for future factors)
        last_action_date: When the last action was taken on this case

    Returns:
        dict with keys: score, level, color, emoji, label_mn, label_en, css_class
    """
    weights = SCORING_CONFIG["weights"]
    thresholds = SCORING_CONFIG["thresholds"]

    # Calculate each factor
    raw_scores = {
        "days_overdue": _score_days_overdue(case.days_overdue or 0),
        "overdue_amount": _score_overdue_amount(case.overdue_amount or 0),
        "action_recency": _score_action_recency(last_action_date),
        "status": _score_status(case.status or "new"),
    }

    # Weighted sum
    total = sum(
        raw_scores[factor] * weights[factor]
        for factor in weights
    )

    # Clamp to 0-100
    score = max(0, min(100, round(total)))

    # Determine risk level from thresholds (check highest first)
    level = "low"
    for lvl in ("critical", "high", "medium", "low"):
        if score >= thresholds[lvl]:
            level = lvl
            break

    risk_info = RISK_LEVELS[level].copy()
    risk_info["score"] = score
    risk_info["raw_scores"] = raw_scores  # Useful for debugging / tooltips

    return risk_info


# ─── Batch Scoring Function ──────────────────────────────────

def score_cases(
    cases_with_data: list[tuple],
) -> list[tuple]:
    """Score a batch of cases efficiently.

    Args:
        cases_with_data: list of (CollectionCase, Loan, Borrower) tuples

    Returns:
        list of (CollectionCase, Loan, Borrower, risk_info) tuples,
        sorted by risk score descending (highest risk first).
    """
    if not cases_with_data:
        return []

    # Batch-fetch the last action date for all cases in one query
    # This avoids N+1 query problem
    case_ids = [c.id for c, l, b in cases_with_data]

    from sqlalchemy import func
    last_actions = dict(
        db.session.query(
            CaseAction.case_id,
            func.max(CaseAction.created_at),
        )
        .filter(CaseAction.case_id.in_(case_ids))
        .group_by(CaseAction.case_id)
        .all()
    )

    # Score each case
    scored = []
    for case, loan, borrower in cases_with_data:
        last_action = last_actions.get(case.id)
        risk_info = calculate_risk_score(case, loan, last_action)
        scored.append((case, loan, borrower, risk_info))

    # Sort by score descending (most urgent first)
    scored.sort(key=lambda x: x[3]["score"], reverse=True)

    return scored


def get_priority_order(risk_info: dict) -> int:
    """Return a sort key for ordering (higher score = earlier in list)."""
    return -risk_info.get("score", 0)
