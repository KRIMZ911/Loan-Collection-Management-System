"""
app/services/widget_catalog.py
==============================
Registry of all customizable widgets for the home dashboard (Phase I).

Design principle:
    Each widget declares its label, size, required permissions, and which
    existing function to call. The home dashboard reads this catalog +
    user preferences and renders only the widgets the user enabled.

To add a new widget:
    1. Define the widget function in branch_stats.py or bank_stats.py
    2. Add an entry to WIDGET_CATALOG below
    3. UI auto-shows it in the settings page for users with permission
"""

from app import db
from app.models import UserWidgetPreference
from app.services.access_control import current_user, get_dashboards, can_access_dashboard


# ════════════════════════════════════════════════════════════════════════════
# WIDGET CATALOG
# ════════════════════════════════════════════════════════════════════════════

WIDGET_CATALOG = {

    # ─── BANK-LEVEL WIDGETS (executive only) ────────────────────────────
    "bank_goals_aggregate": {
        "label_mn":         "Банкны зорилтын нэгтгэл",
        "icon":             "🎯",
        "description_mn":   "Бүх салбарын зорилт + гүйцэтгэлийн нэгтгэл",
        "width":            "wide",
        "height":           "tall",
        "requires_dashboard": "bank",
        "default_for_roles":  ["executive"],
        "module":             "bank_stats",
        "function_name":      "widget_bank_goals_aggregate",
        "takes_branch_id":    False,
        "sort_order":         10,
    },

    "regions_comparison": {
        "label_mn":         "Бүсийн харьцуулалт",
        "icon":             "🌍",
        "description_mn":   "5 бүсийн гүйцэтгэлийн харьцуулсан хүснэгт",
        "width":            "wide",
        "height":           "tall",
        "requires_dashboard": "regional",
        "default_for_roles":  ["regional_director", "executive"],
        "module":             "bank_stats",
        "function_name":      "widget_regions_comparison",
        "takes_branch_id":    False,
        "sort_order":         20,
    },

    "bank_delinquency_trend": {
        "label_mn":         "6 сарын чиг хандлага",
        "icon":             "📈",
        "description_mn":   "Зөрчилтэй зээлийн 6 сарын чиг хандлагын график",
        "width":            "wide",
        "height":           "short",
        "requires_dashboard": "bank",
        "default_for_roles":  ["executive"],
        "module":             "bank_stats",
        "function_name":      "widget_bank_delinquency_trend",
        "takes_branch_id":    False,
        "sort_order":         30,
    },

    # ─── REGIONAL-LEVEL WIDGETS ────────────────────────────────────────
    "branches_kpi_summary": {
        "label_mn":         "Бүсийн KPI",
        "icon":             "📊",
        "description_mn":   "Бүсийн салбаруудын нэгтгэсэн үндсэн үзүүлэлт",
        "width":            "wide",
        "height":           "short",
        "requires_dashboard": "regional",
        "default_for_roles":  ["regional_director"],
        "module":             "branch_stats",
        "function_name":      "widget_branches_kpi_summary",
        "takes_branch_id":    False,
        "sort_order":         40,
    },

    "top_risk_branches": {
        "label_mn":         "ТОП-5 эрсдэлтэй салбар",
        "icon":             "🔥",
        "description_mn":   "Хамгийн өндөр эрсдэлтэй 5 салбарын жагсаалт",
        "width":            "narrow",
        "height":           "tall",
        "requires_dashboard": "regional",
        "default_for_roles":  ["regional_director", "executive"],
        "module":             "branch_stats",
        "function_name":      "widget_top_risk_branches",
        "takes_branch_id":    False,
        "sort_order":         50,
    },

    # ─── BRANCH-LEVEL WIDGETS (single branch) ──────────────────────────
    "branch_summary_kpis": {
        "label_mn":         "Миний салбарын KPI",
        "icon":             "🏢",
        "description_mn":   "Өөрийн салбарын хэрэг, дүн, ажилтны тоо",
        "width":            "narrow",
        "height":           "short",
        "requires_dashboard": "branch",
        "default_for_roles":  ["branch_director", "senior_specialist", "senior_cust_service", "senior_loan_admin"],
        "module":             "branch_stats",
        "function_name":      "widget_branch_summary_kpis",
        "takes_branch_id":    True,
        "sort_order":         60,
    },

    "branch_goals_progress": {
        "label_mn":         "Миний салбарын зорилт",
        "icon":             "🎯",
        "description_mn":   "3 ангиллын зорилтын хэрэгжилт + хурд",
        "width":            "wide",
        "height":           "tall",
        "requires_dashboard": "branch",
        "default_for_roles":  ["branch_director", "regional_director", "executive"],
        "module":             "branch_stats",
        "function_name":      "widget_branch_goals_progress",
        "takes_branch_id":    True,
        "sort_order":         70,
    },

    "branch_worker_performance": {
        "label_mn":         "Ажилтны гүйцэтгэл",
        "icon":             "👥",
        "description_mn":   "Салбарын ажилтнуудын collection KPI",
        "width":            "wide",
        "height":           "tall",
        "requires_dashboard": "branch",
        "default_for_roles":  ["branch_director"],
        "module":             "branch_stats",
        "function_name":      "widget_branch_worker_performance",
        "takes_branch_id":    True,
        "sort_order":         80,
    },

    "branch_recent_activity": {
        "label_mn":         "Сүүлийн үйл ажиллагаа",
        "icon":             "📰",
        "description_mn":   "Сүүлийн 10 холбоо барилт, мэдэгдэл",
        "width":            "narrow",
        "height":           "tall",
        "requires_dashboard": "branch",
        "default_for_roles":  ["branch_director"],
        "module":             "branch_stats",
        "function_name":      "widget_branch_recent_activity",
        "takes_branch_id":    True,
        "sort_order":         90,
    },
}


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def get_available_widgets(user):
    """
    Return list of widget metadata dicts that the user has permission to see.

    Filters by `requires_dashboard` — user must have access to that dashboard
    type via their ROLE_ACCESS policy.

    Returns: list of dicts, each dict includes the widget_id + all metadata.
    Sorted by the catalog's internal sort_order.
    """
    if user is None or user.role is None:
        return []

    available = []
    for widget_id, meta in WIDGET_CATALOG.items():
        required = meta.get("requires_dashboard")
        if required is None or can_access_dashboard(user, required):
            entry = dict(meta)
            entry["widget_id"] = widget_id
            available.append(entry)

    # Sort by catalog sort_order
    available.sort(key=lambda w: w.get("sort_order", 999))
    return available


def get_default_widgets_for_user(user):
    """
    Return list of widget_ids that should be defaults for this user
    based on their role.code intersecting with each widget's default_for_roles.
    """
    if user is None or user.role is None:
        return []

    role_code = user.role.code
    defaults = []

    for widget_id, meta in WIDGET_CATALOG.items():
        # Must have permission
        required = meta.get("requires_dashboard")
        if required is not None and not can_access_dashboard(user, required):
            continue

        # Must be in role's defaults
        if role_code in meta.get("default_for_roles", []):
            defaults.append((widget_id, meta.get("sort_order", 999)))

    # Sort by catalog sort_order, return just IDs
    defaults.sort(key=lambda x: x[1])
    return [w[0] for w in defaults]


def get_user_widgets(user):
    """
    Return list of widget metadata dicts + their preference order,
    for widgets the user has ENABLED. Pulls from UserWidgetPreference table.

    If user has no preferences set at all (new user), returns defaults
    for their role.

    Returns: list of metadata dicts (with widget_id included), in user's
    chosen sort order.
    """
    if user is None:
        return []

    # Pull user's preferences from DB
    prefs = (
        UserWidgetPreference.query
        .filter_by(user_id=user.id, is_enabled=True)
        .order_by(UserWidgetPreference.sort_order, UserWidgetPreference.id)
        .all()
    )

    # No prefs at all? Use defaults for role
    if not prefs:
        default_ids = get_default_widgets_for_user(user)
        return [
            _build_widget_entry(wid)
            for wid in default_ids
            if wid in WIDGET_CATALOG
        ]

    # Has prefs — return them in their order
    # Also filter: only widgets the user still has permission for
    # (in case a role changed or widget was removed)
    result = []
    for pref in prefs:
        if pref.widget_id not in WIDGET_CATALOG:
            continue
        meta = WIDGET_CATALOG[pref.widget_id]
        required = meta.get("requires_dashboard")
        if required is not None and not can_access_dashboard(user, required):
            continue
        result.append(_build_widget_entry(pref.widget_id))

    return result


def _build_widget_entry(widget_id):
    """Internal: build a flat dict with widget_id + metadata."""
    meta = WIDGET_CATALOG.get(widget_id, {})
    entry = dict(meta)
    entry["widget_id"] = widget_id
    return entry


def save_user_widgets(user, widget_ids_in_order):
    """
    Save user's widget preferences.

    Strategy: wipe existing preferences for this user, then insert new ones
    based on the ordered list. Position in list = sort_order.

    Args:
        user: User obj
        widget_ids_in_order: list of widget_id strings in display order
                            (only widgets the user wants ENABLED)
    """
    if user is None:
        return

    # Filter: only valid widget_ids + only ones user has permission for
    valid_ids = []
    for wid in widget_ids_in_order:
        if wid not in WIDGET_CATALOG:
            continue
        meta = WIDGET_CATALOG[wid]
        required = meta.get("requires_dashboard")
        if required is not None and not can_access_dashboard(user, required):
            continue
        valid_ids.append(wid)

    # Wipe existing preferences
    UserWidgetPreference.query.filter_by(user_id=user.id).delete()

    # Insert new preferences
    for idx, wid in enumerate(valid_ids):
        pref = UserWidgetPreference(
            user_id=user.id,
            widget_id=wid,
            sort_order=idx,
            is_enabled=True,
        )
        db.session.add(pref)

    db.session.commit()


# ════════════════════════════════════════════════════════════════════════════
# WIDGET FUNCTION RESOLUTION & RENDERING
# ════════════════════════════════════════════════════════════════════════════

def resolve_widget_function(widget_id):
    """
    Dynamically import and return the widget function by module + name.
    Returns None if widget_id is unknown or function not found.
    """
    meta = WIDGET_CATALOG.get(widget_id)
    if meta is None:
        return None

    module_name = meta.get("module")
    func_name = meta.get("function_name")
    if not module_name or not func_name:
        return None

    try:
        if module_name == "branch_stats":
            from app.services import branch_stats
            return getattr(branch_stats, func_name, None)
        if module_name == "bank_stats":
            from app.services import bank_stats
            return getattr(bank_stats, func_name, None)
    except ImportError:
        return None

    return None


def render_widget_data(user, widget_meta, branch_id=None):
    """
    Call the widget function with appropriate args and return the data.
    Returns None if the widget can't render (missing func, error, etc.).

    Args:
        user: User obj
        widget_meta: dict from WIDGET_CATALOG (must include widget_id)
        branch_id: int, required for widgets where takes_branch_id is True
    """
    func = resolve_widget_function(widget_meta.get("widget_id"))
    if func is None:
        return None

    try:
        if widget_meta.get("takes_branch_id"):
            # Branch widget needs branch_id. If not provided, fall back
            # to user's own branch.
            if branch_id is None:
                branch_id = user.branch_id if user else None
            if branch_id is None:
                return None
            return func(user, branch_id)
        else:
            return func(user)
    except Exception as e:
        # Don't crash the dashboard if one widget fails
        print(f"Widget {widget_meta.get('widget_id')} failed: {e}")
        return None
