"""
Authentication routes — role selection (no real auth for prototype).

Updated for new models.py:
  - User.role is now a relationship to Role model, not a string
  - Find users by Role.dashboard_code instead of User.role string
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models import User, Role


auth_bp = Blueprint("auth", __name__)


# Role definitions for the selector page
ROLES = [
    {"id": "bpuh", "name": "БПҮХ Хяналтын мэргэжилтэн", "sub": "Consumer Loan Monitor", "icon": "📞", "color": "#1565C0"},
    {"id": "zm", "name": "Бүсийн төв – ЗМ /хяналт/", "sub": "Branch Loan Manager", "icon": "🏦", "color": "#2E7D32"},
    {"id": "jdbbg", "name": "ЖДББГ/ББГ мэргэжилтэн", "sub": "Corporate Segment Monitor", "icon": "🏢", "color": "#E65100"},
    {"id": "taug", "name": "ТАУГ мэргэжилтэн", "sub": "Legal Action Specialist", "icon": "⚖️", "color": "#6A1B9A"},
    {"id": "outsourcing", "name": "Outsourcing компани", "sub": "External Collection Agency", "icon": "🔒", "color": "#B71C1C"},
    {"id": "senior", "name": "ЗЭГ Ахлах ажилтан", "sub": "Senior Supervisor", "icon": "👁️", "color": "#455A64"},
    {"id": "mgmt", "name": "Удирдлага", "sub": "Executive Management", "icon": "📊", "color": "#0F172A"},
]


@auth_bp.route("/")
def index():
    """Landing page — role selector."""
    return render_template("select_role.html", roles=ROLES)


@auth_bp.route("/select-role", methods=["POST"])
def select_role():
    """Set the selected role in session and redirect to dashboard."""
    role = request.form.get("role")
    if not role:
        return redirect(url_for("auth.index"))

    # Find role info from ROLES list
    role_info = next((r for r in ROLES if r['id'] == role), None)
    if not role_info:
        return redirect(url_for("auth.index"))

    # Find a user with this dashboard_code via the Role relationship
    user = (
        User.query
        .join(Role, User.role_id == Role.id)
        .filter(Role.dashboard_code == role)
        .first()
    )

    # Set session
    session["role"] = role
    session["role_name"] = role_info["name"]
    session["role_sub"] = role_info["sub"]
    session["role_color"] = role_info["color"]

    if user:
        session["user_id"] = user.id
        session["user_name"] = user.name
    else:
        session["user_id"] = None
        session["user_name"] = "Зочин"

    return redirect(url_for("dashboard.dashboard"))


@auth_bp.route("/logout")
def logout():
    """Clear session and return to role selector."""
    session.clear()
    return redirect(url_for("auth.index"))

