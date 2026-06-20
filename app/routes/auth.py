"""
app/routes/auth.py
==================
Session-based login for the prototype. Users pick themselves from a list.

Phase B flow:
    Login → if 1 dashboard available → redirect to /dashboard/<type>
          → if 2+ dashboards available → redirect to /menu

Production migration path: replace the user picker with a real password / SSO
check. The session contract stays the same: session['user_id'] = User.id.
"""
from flask import Blueprint, render_template, request, session, redirect, url_for, abort
from app.models import User
from app.services.access_control import (
    get_default_dashboard,
    has_multiple_dashboards,
)

auth_bp = Blueprint("auth", __name__)


# Visual metadata per dashboard — used only by the login screen for card colors.
DASHBOARD_META = {
    "bank":     {"icon": "ð¦", "color": "#7C3AED", "label": "Bank"},
    "regional": {"icon": "ð", "color": "#0D9488", "label": "Regional"},
    "branches": {"icon": "ð¢", "color": "#16A34A", "label": "Branches"},
    "loans":    {"icon": "ð", "color": "#2563EB", "label": "Loans"},
}
_DEFAULT_META = {"icon": "ð¤", "color": "#64748B", "label": ""}


@auth_bp.route("/")
def index():
    """Show the user-picker. Lists active users with their role + branch."""
    users = (User.query
             .filter_by(is_active=True)
             .join(User.role)
             .order_by(User.role_id, User.name)
             .all())

    # For coloring cards on the login screen, use the user's DEFAULT dashboard
    # (the first one in their list). If they have none, fall back to default meta.
    def _meta_for(user):
        from app.services.access_control import get_default_dashboard
        dash = get_default_dashboard(user)
        return DASHBOARD_META.get(dash, _DEFAULT_META)

    return render_template(
        "select_role.html",
        users=users,
        dashboard_meta=DASHBOARD_META,
        default_meta=_DEFAULT_META,
    )


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Pick a user → set session → redirect.
    Smart routing:
        - 0 dashboards  → 403 (locked-out role)
        - 1 dashboard   → go straight to it (skip menu)
        - 2+ dashboards → go to /menu (let user pick)
    """
    user_id = request.form.get("user_id", type=int)
    user = User.query.get(user_id) if user_id else None
    if user is None or not user.is_active:
        abort(400, "Invalid user.")

    session.clear()
    session["user_id"]   = user.id
    session["user_name"] = user.name
    session["role_code"] = user.role.code
    session["role_name"] = user.role.name_mn

    # Check what the user can access
    default_dash = get_default_dashboard(user)
    if default_dash is None:
        abort(403, "Your role has no dashboards assigned.")

    # If user has multiple dashboards, show the menu first
    if has_multiple_dashboards(user):
        return redirect(url_for("dashboard.menu"))

    # Otherwise skip menu and go straight to the single dashboard
    return redirect(url_for("dashboard.dashboard", dashboard_type=default_dash))


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("auth.index"))
