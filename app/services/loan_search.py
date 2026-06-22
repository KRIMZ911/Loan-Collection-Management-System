"""
app/services/loan_search.py
============================
Search and filter engine for the Loans dashboard.

Three responsibilities:
    1) Parse a smart search query string → detect what the user meant
    2) Apply filters from URL query params to a SQLAlchemy Loan query
    3) Build the UI metadata (chips, dropdown options) needed by the template

Design notes
------------
- This module knows NOTHING about who the user is. Scope (branch/region/segment
  restrictions per role) is applied separately via access_control.scope_loans()
  BEFORE the filters here run. That way no filter can ever leak data the user
  is not allowed to see.
- All filter values come from request.args. Empty / missing values are skipped.
- URL params survive page refresh and are bookmarkable / shareable.
"""

import re
from datetime import datetime
from typing import Dict, List, Any, Optional

from sqlalchemy import or_, and_

from app.models import (
    Loan, Borrower, LoanProduct, Branch, DepositAccount,
    SegmentType, LoanStatus, ClassificationLevel,
)
from app.services.access_control import scope_branches


# ════════════════════════════════════════════════════════════════════════════
# 1) SMART SEARCH PARSER
# ════════════════════════════════════════════════════════════════════════════
# Given a raw search string, figure out what the user typed.
# Returns a dict: {"type": str, "value": str, "raw": str}

# Regex patterns for ID detection (compiled once at import time)
_RE_LOAN_NUMBER     = re.compile(r"^LN\d+$", re.IGNORECASE)
_RE_CIF             = re.compile(r"^CIF\d+$", re.IGNORECASE)
_RE_DEPOSIT_ACCOUNT = re.compile(r"^DA\d+$", re.IGNORECASE)
_RE_OFF_BALANCE     = re.compile(r"^OB\d+$", re.IGNORECASE)

# Mongolian register number: 2 Cyrillic letters + 8 digits (e.g. "АА12345678")
_RE_REGISTER        = re.compile(r"^[\u0400-\u04FF]{2}\d{8}$")

# Plain 8-digit phone number (Mongolian mobile)
_RE_PHONE           = re.compile(r"^\d{8}$")


def parse_smart_search(query_string: Optional[str]) -> Dict[str, str]:
    """
    Auto-detect what the user typed in the search box.

    Examples:
        ""             → {"type": "empty"}
        "LN00457"      → {"type": "loan_number", "value": "LN00457"}
        "CIF00123"     → {"type": "cif", "value": "CIF00123"}
        "DA00000045"   → {"type": "deposit_account", "value": "DA00000045"}
        "OB12345678"   → {"type": "off_balance_account", "value": "OB12345678"}
        "АА12345678"   → {"type": "register", "value": "АА12345678"}
        "99119911"     → {"type": "phone", "value": "99119911"}
        "bat@bank.mn"  → {"type": "email", "value": "bat@bank.mn"}
        "Бат"          → {"type": "name", "value": "Бат"}
    """
    raw = (query_string or "").strip()
    if not raw:
        return {"type": "empty", "value": "", "raw": ""}

    # Test ID patterns first (most specific)
    if _RE_LOAN_NUMBER.match(raw):
        return {"type": "loan_number", "value": raw.upper(), "raw": raw}
    if _RE_CIF.match(raw):
        return {"type": "cif", "value": raw.upper(), "raw": raw}
    if _RE_DEPOSIT_ACCOUNT.match(raw):
        return {"type": "deposit_account", "value": raw.upper(), "raw": raw}
    if _RE_OFF_BALANCE.match(raw):
        return {"type": "off_balance_account", "value": raw.upper(), "raw": raw}
    if _RE_REGISTER.match(raw):
        return {"type": "register", "value": raw, "raw": raw}
    if _RE_PHONE.match(raw):
        return {"type": "phone", "value": raw, "raw": raw}
    if "@" in raw:
        return {"type": "email", "value": raw, "raw": raw}

    # Default — treat as a name fragment
    return {"type": "name", "value": raw, "raw": raw}


# ════════════════════════════════════════════════════════════════════════════
# 2) APPLY SEARCH TO QUERY
# ════════════════════════════════════════════════════════════════════════════

def apply_search(query, parsed: Dict[str, str]):
    """
    Apply the parsed search to a Loan query.

    IMPORTANT: We use Loan.borrower.has(...) for all Borrower-related
    searches instead of explicit joins. This avoids the "ambiguous column"
    error when scope_loans() has already joined Borrower for segment filtering.
    """
    if parsed["type"] == "empty":
        return query

    t = parsed["type"]
    v = parsed["value"]

    # Loan-only fields (no Borrower needed)
    if t == "loan_number":
        return query.filter(Loan.loan_account_number == v)

    if t == "off_balance_account":
        return query.filter(Loan.off_balance_account_number == v)

    # Borrower-related searches — use .has() to avoid double joins
    if t == "cif":
        return query.filter(Loan.borrower.has(Borrower.cif_number == v))

    if t == "register":
        return query.filter(Loan.borrower.has(Borrower.register_number == v))

    if t == "phone":
        return query.filter(Loan.borrower.has(or_(
            Borrower.phone_primary == v,
            Borrower.phone_home    == v,
            Borrower.phone_work    == v,
        )))

    if t == "email":
        return query.filter(Loan.borrower.has(
            Borrower.email.ilike(f"%{v}%")
        ))

    if t == "name":
        pattern = f"%{v}%"
        return query.filter(Loan.borrower.has(or_(
            Borrower.last_name.ilike(pattern),
            Borrower.first_name.ilike(pattern),
        )))

    if t == "deposit_account":
        # DepositAccount belongs to Borrower — use a nested .has()
        return query.filter(Loan.borrower.has(
            Borrower.deposit_accounts.any(
                DepositAccount.account_number == v
            )
        ))

    return query


# ════════════════════════════════════════════════════════════════════════════
# 3) APPLY FILTERS TO QUERY
# ════════════════════════════════════════════════════════════════════════════
# Each filter is independent; missing/empty values are skipped.

# Map of date_field → Loan model attribute (used by date range filter)
_DATE_FIELD_MAP = {
    "delinquency":  "delinquency_start_date",
    "disbursement": "disbursement_date",
    "maturity":     "maturity_date",
    "last_payment": "last_payment_date",
    "review":       "review_date",
}


def _try_int(v):
    """Safe int conversion. Returns None on failure / empty."""
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _try_float(v):
    """Safe float conversion. Returns None on failure / empty."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _try_date(v):
    """Parse ISO date string (YYYY-MM-DD). Returns None on failure / empty."""
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def apply_filters(query, filters: Dict[str, Any]):
    """
    Apply each non-empty filter to the query.
    `filters` is typically request.args (or dict copy).
    """
    # Branch filter
    branch_id = _try_int(filters.get("branch_id"))
    if branch_id:
        query = query.filter(Loan.branch_id == branch_id)

    # Segment filter (needs Borrower join — but only if not already joined)
    segment = (filters.get("segment") or "").upper()
    if segment in ("RETAIL", "SMB"):
        # Use a subquery to avoid double-join issues
        seg_enum = SegmentType.RETAIL if segment == "RETAIL" else SegmentType.SMB
        query = query.filter(Loan.borrower.has(Borrower.segment == seg_enum))

    # Delinquency days range
    days_min = _try_int(filters.get("days_min"))
    days_max = _try_int(filters.get("days_max"))
    if days_min is not None:
        query = query.filter(Loan.delinquency_days >= days_min)
    if days_max is not None:
        query = query.filter(Loan.delinquency_days <= days_max)

    # Amount overdue range
    amount_min = _try_float(filters.get("amount_min"))
    amount_max = _try_float(filters.get("amount_max"))
    if amount_min is not None:
        query = query.filter(Loan.amount_overdue >= amount_min)
    if amount_max is not None:
        query = query.filter(Loan.amount_overdue <= amount_max)

    # Status filter (matches LoanStatus enum)
    status = filters.get("status")
    if status:
        try:
            status_enum = LoanStatus(status)
            query = query.filter(Loan.status == status_enum)
        except ValueError:
            pass  # Invalid status — silently skip

    # Classification filter
    classif = filters.get("classification")
    if classif:
        try:
            classif_enum = ClassificationLevel(classif)
            query = query.filter(Loan.classification == classif_enum)
        except ValueError:
            pass

    # Product filter
    product_id = _try_int(filters.get("product_id"))
    if product_id:
        query = query.filter(Loan.loan_product_id == product_id)

    # Date range filter — needs a field selector
    date_field = filters.get("date_field") or "delinquency"
    date_attr_name = _DATE_FIELD_MAP.get(date_field)
    if date_attr_name and hasattr(Loan, date_attr_name):
        date_attr = getattr(Loan, date_attr_name)
        d_from = _try_date(filters.get("date_from"))
        d_to   = _try_date(filters.get("date_to"))
        if d_from:
            query = query.filter(date_attr >= d_from)
        if d_to:
            query = query.filter(date_attr <= d_to)

    return query


# ════════════════════════════════════════════════════════════════════════════
# 4) BUILD FILTER CHIPS FOR THE UI
# ════════════════════════════════════════════════════════════════════════════
# Generates a list of human-readable chip dicts representing active filters.
# Each chip has a `remove_url` that drops that param while keeping others.

# Mongolian labels for status values
_STATUS_LABELS_MN = {
    "active":           "Идэвхтэй",
    "delinquent":       "Зөрчилтэй",
    "restructured":     "Бүтэц өөрчилсөн",
    "transferred_taug": "ТАУГ-т шилжсэн",
    "outsourced":       "Аутсорсинг",
    "legal":            "Хууль зүй",
    "court":            "Шүүхэд",
    "closed":           "Хаагдсан",
    "written_off":      "Хасагдсан",
    "resolved":         "Шийдвэрлэсэн",
}

_CLASSIFICATION_LABELS_MN = {
    "normal":      "Хэвийн",
    "watch":       "Хяналтад",
    "substandard": "Чанаргүй",
    "doubtful":    "Эргэлзээтэй",
    "loss":        "Алдагдал",
}

_DATE_FIELD_LABELS_MN = {
    "delinquency":  "Зөрчил үүссэн",
    "disbursement": "Олгогдсон",
    "maturity":     "Дуусах",
    "last_payment": "Сүүлийн төлөлт",
    "review":       "Эргэн хянах",
}

# Mongolian label for search type
_SEARCH_TYPE_LABELS_MN = {
    "loan_number":         "Зээлийн дугаар",
    "cif":                 "CIF",
    "deposit_account":     "Дансны дугаар",
    "off_balance_account": "Балансын гадуурх данс",
    "register":            "Регистр",
    "phone":               "Утас",
    "email":               "Имэйл",
    "name":                "Нэр",
}


def _url_without(filters: Dict[str, Any], drop_keys: List[str]) -> str:
    """Build a query string from `filters` with `drop_keys` removed."""
    parts = []
    for k, v in filters.items():
        if k in drop_keys or v is None or v == "":
            continue
        parts.append(f"{k}={v}")
    return "?" + "&".join(parts) if parts else "?"


def build_filter_chips(
    filters: Dict[str, Any],
    parsed_search: Dict[str, str],
    branches_dict: Dict[int, str],
    products_dict: Dict[int, str],
) -> List[Dict[str, str]]:
    """
    Build a list of chip dicts representing each active filter.
    Used by the template to render the "× to remove" chip row.

    Each chip: {"label": str, "remove_url": str, "key": str}
    """
    chips = []

    # Search chip
    if parsed_search and parsed_search["type"] != "empty":
        type_label = _SEARCH_TYPE_LABELS_MN.get(
            parsed_search["type"], parsed_search["type"]
        )
        chips.append({
            "key":        "q",
            "label":      f"{type_label}: {parsed_search['raw']}",
            "remove_url": _url_without(filters, ["q"]),
        })

    # Branch
    branch_id = _try_int(filters.get("branch_id"))
    if branch_id:
        bname = branches_dict.get(branch_id, f"#{branch_id}")
        chips.append({
            "key":        "branch_id",
            "label":      f"Салбар: {bname}",
            "remove_url": _url_without(filters, ["branch_id"]),
        })

    # Segment
    segment = (filters.get("segment") or "").upper()
    if segment == "RETAIL":
        chips.append({
            "key":        "segment",
            "label":      "Сегмент: Иргэдийн",
            "remove_url": _url_without(filters, ["segment"]),
        })
    elif segment == "SMB":
        chips.append({
            "key":        "segment",
            "label":      "Сегмент: ЖДББ",
            "remove_url": _url_without(filters, ["segment"]),
        })

    # Days range
    days_min = _try_int(filters.get("days_min"))
    days_max = _try_int(filters.get("days_max"))
    if days_min is not None or days_max is not None:
        if days_min is not None and days_max is not None:
            label = f"Хоног: {days_min}-{days_max}"
        elif days_min is not None:
            label = f"Хоног: {days_min}+"
        else:
            label = f"Хоног: ≤{days_max}"
        chips.append({
            "key":        "days",
            "label":      label,
            "remove_url": _url_without(filters, ["days_min", "days_max"]),
        })

    # Amount range
    amount_min = _try_float(filters.get("amount_min"))
    amount_max = _try_float(filters.get("amount_max"))
    if amount_min is not None or amount_max is not None:
        def _fmt(v):
            return f"{int(v):,}"
        if amount_min is not None and amount_max is not None:
            label = f"Дүн: {_fmt(amount_min)}-{_fmt(amount_max)}₮"
        elif amount_min is not None:
            label = f"Дүн: {_fmt(amount_min)}₮+"
        else:
            label = f"Дүн: ≤{_fmt(amount_max)}₮"
        chips.append({
            "key":        "amount",
            "label":      label,
            "remove_url": _url_without(filters, ["amount_min", "amount_max"]),
        })

    # Status
    status = filters.get("status")
    if status:
        label = _STATUS_LABELS_MN.get(status, status)
        chips.append({
            "key":        "status",
            "label":      f"Төлөв: {label}",
            "remove_url": _url_without(filters, ["status"]),
        })

    # Classification
    classif = filters.get("classification")
    if classif:
        label = _CLASSIFICATION_LABELS_MN.get(classif, classif)
        chips.append({
            "key":        "classification",
            "label":      f"Ангилал: {label}",
            "remove_url": _url_without(filters, ["classification"]),
        })

    # Product
    product_id = _try_int(filters.get("product_id"))
    if product_id:
        pname = products_dict.get(product_id, f"#{product_id}")
        chips.append({
            "key":        "product_id",
            "label":      f"Бүтээгдэхүүн: {pname}",
            "remove_url": _url_without(filters, ["product_id"]),
        })

    # Date range
    d_from = filters.get("date_from")
    d_to   = filters.get("date_to")
    if d_from or d_to:
        field_label = _DATE_FIELD_LABELS_MN.get(
            filters.get("date_field") or "delinquency", "Огноо"
        )
        if d_from and d_to:
            range_str = f"{d_from} → {d_to}"
        elif d_from:
            range_str = f"{d_from}-аас"
        else:
            range_str = f"{d_to}-хүртэл"
        chips.append({
            "key":        "date",
            "label":      f"{field_label}: {range_str}",
            "remove_url": _url_without(
                filters, ["date_field", "date_from", "date_to"]
            ),
        })

    return chips


# ════════════════════════════════════════════════════════════════════════════
# 5) GET FILTER OPTIONS FOR DROPDOWNS (permission-aware)
# ════════════════════════════════════════════════════════════════════════════

def get_filter_options(user) -> Dict[str, Any]:
    """
    Return all dropdown options + visibility flags for the filter bar,
    adapted to what the user can see.

    A filter dropdown is HIDDEN when it would only have 1 option (useless).
    """
    # Branches visible to this user (uses access_control's scope helper)
    visible_branches = scope_branches(Branch.query, user).order_by(Branch.name).all()

    # Products (everyone sees all products — no per-user product restrictions)
    products = LoanProduct.query.order_by(LoanProduct.name).all()

    # Segment visibility: hide if user is already locked to one segment
    from app.services.access_control import get_policy
    policy = get_policy(user)
    segment_locked = policy.get("segment_filter") is not None
    show_segment_filter = not segment_locked

    # Branch dropdown is only useful if 2+ branches are visible
    show_branch_filter = len(visible_branches) > 1

    return {
        "branches":            [{"id": b.id, "name": b.name} for b in visible_branches],
        "products":            [{"id": p.id, "name": p.name} for p in products],
        "show_branch_filter":  show_branch_filter,
        "show_segment_filter": show_segment_filter,
        "statuses": [
            {"value": s.value, "label": _STATUS_LABELS_MN.get(s.value, s.value)}
            for s in LoanStatus
        ],
        "classifications": [
            {"value": c.value, "label": _CLASSIFICATION_LABELS_MN.get(c.value, c.value)}
            for c in ClassificationLevel
        ],
        "date_fields": [
            {"value": k, "label": v} for k, v in _DATE_FIELD_LABELS_MN.items()
        ],
        # Helper dicts for chip labels (id → name)
        "branches_dict": {b.id: b.name for b in visible_branches},
        "products_dict": {p.id: p.name for p in products},
    }


# ════════════════════════════════════════════════════════════════════════════
# 6) HIGH-LEVEL CONVENIENCE FUNCTION
# ════════════════════════════════════════════════════════════════════════════

def apply_search_and_filters(query, request_args):
    """
    Convenience: parse + apply search + apply filters in one call.
    Returns: (query, parsed_search)
    """
    parsed = parse_smart_search(request_args.get("q"))
    query  = apply_search(query, parsed)
    query  = apply_filters(query, request_args)
    return query, parsed
