"""
Authentication routes — role selection (no real auth for prototype).
"""
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models import User

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

    # Find the first user matching this role
    user = User.query.filter_by(role=role, is_active=True).first()
    if user:
        session["role"] = role
        session["user_id"] = user.id
        session["user_name"] = user.name
    else:
        session["role"] = role
        session["user_id"] = None
        session["user_name"] = "Зочин"

    # Store role metadata for templates
    role_info = next((r for r in ROLES if r["id"] == role), ROLES[0])
    session["role_name"] = role_info["name"]
    session["role_sub"] = role_info["sub"]
    session["role_color"] = role_info["color"]

    return redirect(url_for("dashboard.dashboard"))


@auth_bp.route("/logout")
def logout():
    """Clear session and return to role selector."""
    session.clear()
    return redirect(url_for("auth.index"))
