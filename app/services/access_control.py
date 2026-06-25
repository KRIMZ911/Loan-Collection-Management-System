"""
app/services/access_control.py
================================
Hybrid access control for the Collection Management System.

PHASE A REFACTOR (multi-dashboard support):
    - Each role now has a LIST of accessible dashboards (in display order),
      not a single one.
    - 4 universal dashboards: bank, regional, branches, loans.
    - Single-dashboard users will skip the menu (handled in auth.py — Phase B).
    - Multi-dashboard users land on /menu (handled in auth.py — Phase B).

What this module IS
-------------------
The single source of truth for "who can see what data" in the app:
    - Static policy table (ROLE_ACCESS) — keyed by Role.code
    - Universal dashboard catalog (DASHBOARD_CATALOG)
    - Runtime scope resolution from the logged-in User
    - SQLAlchemy query scoping helpers per model
    - Route decorators: @require_login and @require_dashboard

What this module IS NOT
-----------------------
    - NOT the 15-step regulatory permission matrix (that's the `permissions`
      table — execute/control/dual-control flags from File 3). Stays separate.
    - NOT authentication. Login lives in routes/auth.py.

Layers
------
    Role.code (e.g. "zm_control")
        │
        ▼
    ROLE_ACCESS["zm_control"]   ← static policy (this file)
        │
        ▼
    get_dashboards(user)         ← list of dashboards user can see
    get_default_dashboard(user)  ← first one (for skip-menu logic)
    can_access_dashboard(user, "loans")  ← guard check
        │
        ▼
    scope_loans(query, user)     ← applies geo + segment scope to a query
    scope_borrowers(query, user)
    scope_users(query, user)
    can(user, "action")          ← feature flags
    mask_personal_info(user)     ← outsourcing masking
"""

from functools import wraps
from typing import Optional, Dict, Any, List
from flask import session, redirect, url_for, abort, g
from sqlalchemy.orm import Query

from app import db
from app.models import (
    User, Loan, Borrower, Branch,
    OutsourcingAssignment, ContactLog,
    SegmentType,
)


# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════════════════════

# Geographic scope
GEO_OWN_BRANCH      = "own_branch"
GEO_OWN_REGION      = "own_region"
GEO_BANK_WIDE       = "bank_wide"
GEO_OWN_ASSIGNMENTS = "own_assignments"
GEO_NONE            = "none"     # no access (used as default fallback)

# Segment filter (matches SegmentType enum values)
SEG_RETAIL = "RETAIL"
SEG_SMB    = "SMB"

# Dashboard types — the 4 universal dashboards
DASH_BANK     = "bank"
DASH_REGIONAL = "regional"
DASH_BRANCH = "branch"
DASH_LOANS    = "loans"
DASH_HOME     = "home"


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD CATALOG — visual + meta info for the 4 universal dashboards
# ════════════════════════════════════════════════════════════════════════════
# Used by the /menu page and dashboard headers. Add new dashboards here.
DASHBOARD_CATALOG: Dict[str, Dict[str, str]] = {
    DASH_BANK: {
        "icon":     "🏦",
        "label_mn": "Банкны нэгтгэл",
        "label_en": "Bank Overview",
        "color":    "#7C3AED",
        "sub_mn":   "Бүх бүс, салбаруудын нэгтгэл",
    },
    DASH_REGIONAL: {
        "icon":     "🌍",
        "label_mn": "Бүсийн самбар",
        "label_en": "Regional Dashboard",
        "color":    "#0D9488",
        "sub_mn":   "Бүсийн доторх салбаруудын харьцуулалт",
    },
    DASH_BRANCH: {
        "icon":     "🏢",
        "label_mn": "Салбарын самбар",
        "label_en": "Branch Dashboard",
        "color":    "#16A34A",
        "sub_mn":   "Зорилт, ажилтан, гүйцэтгэл",
    },
    DASH_LOANS: {
        "icon":     "📋",
        "label_mn": "Зээлийн жагсаалт",
        "label_en": "Loans Dashboard",
        "color":    "#2563EB",
        "sub_mn":   "Зээлийн хэрэг, дэлгэрэнгүй мэдээлэл",
    },
    DASH_HOME: {
        "icon":     "🏠",
        "label_mn": "Миний самбар",
        "label_en": "My Dashboard",
        "color":    "#0EA5E9",
        "sub_mn":   "Өөрийн сонгосон виджетүүд",
    },
}

# ════════════════════════════════════════════════════════════════════════════
# 1) STATIC POLICY — ROLE_ACCESS
# ════════════════════════════════════════════════════════════════════════════
# Add a new role → add an entry. That's the whole onboarding.
#
# Required keys per entry:
#   dashboards:                list[str] — dashboard types user can access,
#                                          in display order on the menu
#   geo_scope:                 str       — one of GEO_* constants
#   segment_filter:            str|None  — SEG_RETAIL / SEG_SMB / None (both)
#   hide_personal:             bool      — mask borrower PII?
#   can_see_employees:         bool      — can list other staff?
#   can_see_employee_performance: bool   — can view KPIs of staff?
#   can_assign_cases:          bool      — can reassign loans?
#   can_export:                bool      — can export CSV/Excel?

def _branch_worker(segment: Optional[str] = None) -> Dict[str, Any]:
    """Default profile: branch-floor worker. One dashboard: loans."""
    return {
        "dashboards":                  [DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_OWN_BRANCH,
        "segment_filter":              segment,
        "hide_personal":               False,
        "can_see_employees":           False,
        "can_see_employee_performance": False,
        "can_assign_cases":            False,
        "can_export":                  False,
    }


def _branch_manager() -> Dict[str, Any]:
    """Default profile: branch-level manager. Two dashboards: branches + loans."""
    return {
        "dashboards":                  [DASH_BRANCH, DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_OWN_BRANCH,
        "segment_filter":              None,
        "hide_personal":               False,
        "can_see_employees":           True,
        "can_see_employee_performance": True,
        "can_assign_cases":            False,
        "can_export":                  False,
    }


def _hq_specialist(segment: Optional[str] = None) -> Dict[str, Any]:
    """Default profile: HQ specialist (BPUH, TAUG, etc.). Bank-wide loans only."""
    return {
        "dashboards":                  [DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_BANK_WIDE,
        "segment_filter":              segment,
        "hide_personal":               False,
        "can_see_employees":           False,
        "can_see_employee_performance": False,
        "can_assign_cases":            False,
        "can_export":                  True,
    }


ROLE_ACCESS: Dict[str, Dict[str, Any]] = {

    # ─── BRANCH WORKERS — single dashboard (loans), own branch only ───────
    "zm_research":           _branch_worker(),
    "zm_control":            _branch_worker(),
    "retail_hm":             _branch_worker(segment=SEG_RETAIL),
    "smb_hm":                _branch_worker(segment=SEG_SMB),
    "admin_officer":         _branch_worker(),
    "cust_service":          _branch_worker(),
    "loan_admin":            _branch_worker(),

    # ─── BRANCH SENIORS — two dashboards (branches + loans), own branch ────
    "senior_specialist":     _branch_manager(),
    "senior_cust_service":   _branch_manager(),
    "senior_loan_admin":     _branch_manager(),

    # ─── BRANCH DIRECTOR — same as managers but can assign + export ───────
    "branch_director": {
        **_branch_manager(),
        "can_assign_cases":  True,
        "can_export":        True,
        "can_set_worker_goals": True,
    },

    # ─── REGIONAL DIRECTOR — three dashboards, own region ─────────────────
    "regional_director": {
        "dashboards":                  [DASH_REGIONAL, DASH_BRANCH, DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_OWN_REGION,
        "segment_filter":              None,
        "hide_personal":               False,
        "can_see_employees":           True,
        "can_see_employee_performance": True,
        "can_assign_cases":            True,
        "can_export":                  True,
        "can_set_branch_goals":       True,
    },

    # ─── HQ PROCESS CONTROL (БПҮХ) — retail loans, bank-wide ──────────────
    "process_control":       _hq_specialist(segment=SEG_RETAIL),

    # ─── ЖДББГ (SMB segment HQ) ───────────────────────────────────────────
    "segment_office": {
        **_hq_specialist(segment=SEG_SMB),
        "can_see_employees":           True,
        "can_see_employee_performance": True,
        "can_assign_cases":            True,
    },
    "segment_specialist":    _hq_specialist(segment=SEG_SMB),

    # ─── ТАУГ (NPL department) ────────────────────────────────────────────
    "taug_specialist": {
        **_hq_specialist(),
        "can_assign_cases":  True,
    },
    "lawyer":                _hq_specialist(),
    "insurance_specialist":  _hq_specialist(),

    # ─── COMMITTEE SECRETARY ──────────────────────────────────────────────
    "committee_secretary":   _hq_specialist(),

    # ─── RISK DEPARTMENT (ЗЭГ) ────────────────────────────────────────────
    "risk_analyst":          _hq_specialist(),
    "senior_analyst":        _hq_specialist(),
    "property_valuator":     _hq_specialist(),
    "aml_analyst":           _hq_specialist(),
    "compliance":            _hq_specialist(),
    "finance_control":       _hq_specialist(),

    # Risk dept director — gets branches dashboard too for oversight
    "risk_dept_director": {
        "dashboards":                  [DASH_BRANCH, DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_BANK_WIDE,
        "segment_filter":              None,
        "hide_personal":               False,
        "can_see_employees":           True,
        "can_see_employee_performance": True,
        "can_assign_cases":            True,
        "can_export":                  True,
    },

    # ─── OUTSOURCING — masked PII, scoped to assignments ──────────────────
    # NOTE: OutsourcingAssignment has no user FK yet — for now we scope by
    # company_name matching User.name. TODO: add assigned_to_user_id field.
    "outsourcing_agent": {
        "dashboards":                  [DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_OWN_ASSIGNMENTS,
        "segment_filter":              None,
        "hide_personal":               True,
        "can_see_employees":           False,
        "can_see_employee_performance": False,
        "can_assign_cases":            False,
        "can_export":                  False,
    },

    # ─── EXECUTIVE (Удирдлага) — all four dashboards, full visibility ─────
    "executive": {
        "dashboards":                  [DASH_BANK, DASH_REGIONAL, DASH_BRANCH, DASH_LOANS, DASH_HOME],
        "geo_scope":                   GEO_BANK_WIDE,
        "segment_filter":              None,
        "hide_personal":               False,
        "can_see_employees":           True,
        "can_see_employee_performance": True,
        "can_assign_cases":            False,
        "can_export":                  True,
        "can_set_branch_goals":        True,     # ← NEW
        "can_set_worker_goals":        True,     # ← NEW

    },
}


# Fallback for any role.code not in ROLE_ACCESS — locked down by default
_NO_ACCESS: Dict[str, Any] = {
    "dashboards":                  [],
    "geo_scope":                   GEO_NONE,
    "segment_filter":              None,
    "hide_personal":               True,
    "can_see_employees":           False,
    "can_see_employee_performance": False,
    "can_assign_cases":            False,
    "can_export":                  False,
    "can_set_branch_goals":        False,    # ← NEW
    "can_set_worker_goals":        False,    # ← NEW

}


# ════════════════════════════════════════════════════════════════════════════
# 2) USER / SCOPE RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

def current_user() -> Optional[User]:
    """Return the currently logged-in User (cached on flask.g per request)."""
    if "user" in g:
        return g.user
    uid = session.get("user_id")
    g.user = User.query.get(uid) if uid else None
    return g.user


def get_policy(user: User) -> Dict[str, Any]:
    """Look up the static ROLE_ACCESS entry for a user. Locked-down if unknown."""
    if user is None or user.role is None:
        return _NO_ACCESS
    return ROLE_ACCESS.get(user.role.code, _NO_ACCESS)


def get_scope(user: User) -> Dict[str, Any]:
    """
    Resolve a runtime scope dict for the user.
    Returns:
        {
            "geo_scope":      str,         # one of GEO_*
            "branch_ids":     list[int] | "all" | [],
            "segment_filter": str | None,  # "RETAIL" / "SMB" / None
            "user_id":        int | None,
        }
    """
    policy = get_policy(user)
    geo = policy["geo_scope"]
    scope = {
        "geo_scope":      geo,
        "branch_ids":     [],
        "segment_filter": policy["segment_filter"],
        "user_id":        user.id if user else None,
    }

    if geo == GEO_OWN_BRANCH:
        scope["branch_ids"] = [user.branch_id] if user.branch_id else []
    elif geo == GEO_OWN_REGION:
        if user.region_id:
            branches = Branch.query.filter_by(region_id=user.region_id).all()
            scope["branch_ids"] = [b.id for b in branches]
    elif geo == GEO_BANK_WIDE:
        scope["branch_ids"] = "all"
    elif geo == GEO_OWN_ASSIGNMENTS:
        scope["branch_ids"] = "all"     # joined via OutsourcingAssignment below

    return scope


# ════════════════════════════════════════════════════════════════════════════
# 3) DASHBOARD ACCESS HELPERS
# ════════════════════════════════════════════════════════════════════════════

def get_dashboards(user: User) -> List[str]:
    """Return the list of dashboard types this user can access (in display order)."""
    return list(get_policy(user).get("dashboards", []))


def get_default_dashboard(user: User) -> Optional[str]:
    """
    Return the dashboard to redirect to after login.
    - 0 dashboards → None  (no access; auth.py shows error)
    - 1+ dashboards → first item  (skip menu if exactly 1)
    """
    dashboards = get_dashboards(user)
    return dashboards[0] if dashboards else None


def has_multiple_dashboards(user: User) -> bool:
    """True if user should see the menu instead of skipping to a dashboard."""
    return len(get_dashboards(user)) > 1


def get_scope_label(user: User) -> Dict[str, str]:
    """
    Return a human-readable label describing what the user can see.
    Used in the dashboard header badge.

    Returns dict with:
        icon  — emoji for the scope
        text  — short label ("Баянзүрх салбар", "Төв бүс", etc.)
        sub   — extra context ("5 салбар", "Retail зээл", etc.)
    """
    if user is None:
        return {"icon": "🔒", "text": "Эрх байхгүй", "sub": ""}

    policy = get_policy(user)
    geo = policy["geo_scope"]
    segment = policy["segment_filter"]

    # Geographic label
    if geo == GEO_OWN_BRANCH:
        text = user.branch.name if user.branch else "Тодорхойгүй салбар"
        icon = "🏢"
    elif geo == GEO_OWN_REGION:
        if user.region_id:
            from app.models import Region
            region = Region.query.get(user.region_id)
            branches_count = Branch.query.filter_by(region_id=user.region_id).count()
            text = region.name if region else "Тодорхойгүй бүс"
            icon = "🌍"
        else:
            text, icon = "Бүсгүй", "🌍"
            branches_count = 0
    elif geo == GEO_BANK_WIDE:
        text = "Бүх банк"
        icon = "🏦"
        branches_count = Branch.query.count()
    elif geo == GEO_OWN_ASSIGNMENTS:
        text = "Миний хариуцсан хэрэг"
        icon = "🔒"
        branches_count = 0
    else:
        return {"icon": "🔒", "text": "Эрх байхгүй", "sub": ""}

    # Sub text (segment / branch count)
    sub_parts = []
    if geo == GEO_OWN_REGION and branches_count:
        sub_parts.append(f"{branches_count} салбар")
    elif geo == GEO_BANK_WIDE and branches_count:
        sub_parts.append(f"{branches_count} салбар")

    if segment == SEG_RETAIL:
        sub_parts.append("Иргэдийн зээл")
    elif segment == SEG_SMB:
        sub_parts.append("ЖДББ зээл")

    return {
        "icon": icon,
        "text": text,
        "sub": " • ".join(sub_parts),
    }


def can_access_dashboard(user: User, dashboard_type: str) -> bool:
    """Check if user is allowed to view a specific dashboard type."""
    return dashboard_type in get_dashboards(user)


# Backward compatibility — old code that called get_dashboard_code(user)
# still works. Returns the default (first) dashboard.
def get_dashboard_code(user: User) -> Optional[str]:
    """Deprecated alias for get_default_dashboard. Kept for backward compat."""
    return get_default_dashboard(user)


# ════════════════════════════════════════════════════════════════════════════
# 4) FEATURE FLAG HELPERS
# ════════════════════════════════════════════════════════════════════════════

def can(user: User, action: str) -> bool:
    """Check a single capability flag. Unknown actions = denied."""
    return bool(get_policy(user).get(action, False))


def mask_personal_info(user: User) -> bool:
    """Should borrower PII (name/phone/address) be masked for this user?"""
    return bool(get_policy(user).get("hide_personal", True))


# ════════════════════════════════════════════════════════════════════════════
# 5) QUERY SCOPING HELPERS — one per model
# ════════════════════════════════════════════════════════════════════════════
# Each takes (query, user) → query. Apply BEFORE other filters in dashboards.

def scope_loans(query: Query, user: User) -> Query:
    """Filter a Loan query down to what the user can see."""
    scope = get_scope(user)

    # Geographic
    if scope["branch_ids"] == "all":
        pass        # bank-wide
    elif scope["geo_scope"] == GEO_OWN_ASSIGNMENTS:
        if user and user.name:
            query = (query
                .join(OutsourcingAssignment, OutsourcingAssignment.loan_id == Loan.id)
                .filter(OutsourcingAssignment.company_name == user.name))
        else:
            query = query.filter(db.false())
    elif scope["branch_ids"]:
        query = query.filter(Loan.branch_id.in_(scope["branch_ids"]))
    else:
        query = query.filter(db.false())     # no access

    # Segment
    if scope["segment_filter"] == SEG_RETAIL:
        query = (query.join(Borrower, Loan.borrower_id == Borrower.id)
                      .filter(Borrower.segment == SegmentType.RETAIL))
    elif scope["segment_filter"] == SEG_SMB:
        query = (query.join(Borrower, Loan.borrower_id == Borrower.id)
                      .filter(Borrower.segment == SegmentType.SMB))

    return query


def scope_borrowers(query: Query, user: User) -> Query:
    """Filter a Borrower query down to what the user can see."""
    scope = get_scope(user)

    if scope["branch_ids"] == "all":
        pass
    elif scope["geo_scope"] == GEO_OWN_ASSIGNMENTS:
        if user and user.name:
            query = (query
                .join(Loan, Loan.borrower_id == Borrower.id)
                .join(OutsourcingAssignment, OutsourcingAssignment.loan_id == Loan.id)
                .filter(OutsourcingAssignment.company_name == user.name)
                .distinct())
        else:
            query = query.filter(db.false())
    elif scope["branch_ids"]:
        query = query.filter(Borrower.branch_id.in_(scope["branch_ids"]))
    else:
        query = query.filter(db.false())

    if scope["segment_filter"] == SEG_RETAIL:
        query = query.filter(Borrower.segment == SegmentType.RETAIL)
    elif scope["segment_filter"] == SEG_SMB:
        query = query.filter(Borrower.segment == SegmentType.SMB)

    return query


def scope_users(query: Query, user: User) -> Query:
    """Filter the employee directory (User table) by the user's scope."""
    if not can(user, "can_see_employees"):
        return query.filter(db.false())

    scope = get_scope(user)
    if scope["branch_ids"] == "all":
        return query
    if scope["branch_ids"]:
        return query.filter(User.branch_id.in_(scope["branch_ids"]))
    return query.filter(db.false())


def scope_branches(query: Query, user: User) -> Query:
    """Filter the Branch query by user scope. NEW for branches dashboard."""
    scope = get_scope(user)
    if scope["branch_ids"] == "all":
        return query
    if scope["branch_ids"]:
        return query.filter(Branch.id.in_(scope["branch_ids"]))
    return query.filter(db.false())


def scope_contact_logs(query: Query, user: User) -> Query:
    """Filter ContactLog via the parent Loan's branch."""
    scope = get_scope(user)

    if scope["branch_ids"] == "all" and not scope["segment_filter"]:
        return query

    query = query.join(Loan, ContactLog.loan_id == Loan.id)
    if scope["branch_ids"] != "all":
        if scope["branch_ids"]:
            query = query.filter(Loan.branch_id.in_(scope["branch_ids"]))
        else:
            return query.filter(db.false())

    if scope["segment_filter"]:
        query = query.join(Borrower, Loan.borrower_id == Borrower.id)
        if scope["segment_filter"] == SEG_RETAIL:
            query = query.filter(Borrower.segment == SegmentType.RETAIL)
        elif scope["segment_filter"] == SEG_SMB:
            query = query.filter(Borrower.segment == SegmentType.SMB)
    return query


def can_view_loan(user: User, loan: Loan) -> bool:
    """Cheap per-record check — used by /case/<id> route guard."""
    if loan is None or user is None:
        return False
    scope = get_scope(user)

    # Segment check
    if scope["segment_filter"]:
        seg = loan.borrower.segment if loan.borrower else None
        wanted = SegmentType.RETAIL if scope["segment_filter"] == SEG_RETAIL else SegmentType.SMB
        if seg != wanted:
            return False

    # Geographic check
    if scope["branch_ids"] == "all":
        return True
    if scope["geo_scope"] == GEO_OWN_ASSIGNMENTS:
        return OutsourcingAssignment.query.filter_by(
            loan_id=loan.id, company_name=user.name
        ).first() is not None
    return loan.branch_id in (scope["branch_ids"] or [])


# ════════════════════════════════════════════════════════════════════════════
# 6) ROUTE DECORATORS
# ════════════════════════════════════════════════════════════════════════════

def require_login(view_fn):
    """Redirect to the login page if not logged in."""
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.index"))
        return view_fn(*args, **kwargs)
    return wrapper


def require_dashboard(dashboard_type: str):
    """Block users who don't have this dashboard_type in their dashboards list."""
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.index"))
            if not can_access_dashboard(user, dashboard_type):
                abort(403)
            return view_fn(*args, **kwargs)
        return wrapper
    return decorator

def require_capability(capability_key: str):
    """
    Block users whose policy doesn't grant this capability flag.
    Used for admin actions like setting goals, exporting data, etc.

    Usage:
        @require_capability("can_set_branch_goals")
        def view():
            ...

    Behavior:
        - Not logged in → redirect to login page
        - Logged in but no capability → 403 Forbidden
        - Logged in with capability → view runs normally
    """
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.index"))
            if not can(user, capability_key):
                abort(403)
            return view_fn(*args, **kwargs)
        return wrapper
    return decorator