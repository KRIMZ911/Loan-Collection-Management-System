"""
Dashboard routes — renders role-specific dashboards with data from DB.
Risk scoring is applied via the services.scoring module.
"""
from flask import Blueprint, render_template, session, redirect, url_for
from sqlalchemy import func
from app import db
from app.models import (
    User, Borrower, Loan, CollectionCase,
    CaseAction, CaseTransfer, OutsourcingAssignment, CommitteeDecision,
)
from app.services.scoring import score_cases, RISK_LEVELS

dashboard_bp = Blueprint("dashboard", __name__)

# Navigation definitions per role
NAV_ITEMS = {
    "bpuh": [
        {"id": "cases", "icon": "📋", "label": "Миний хэрэг"},
        {"id": "history", "icon": "🕐", "label": "Үйлдлийн түүх"},
        {"id": "cc", "icon": "💳", "label": "Кредит карт тайлан"},
    ],
    "zm": [
        {"id": "cases", "icon": "📋", "label": "Салбарын хэрэг"},
        {"id": "summary", "icon": "📊", "label": "Нэгтгэл"},
        {"id": "transfer", "icon": "➡️", "label": "ТАУГ шилжүүлэг"},
        {"id": "reports", "icon": "📈", "label": "Тайлан"},
    ],
    "jdbbg": [
        {"id": "companies", "icon": "🏢", "label": "Компаниуд"},
        {"id": "cases", "icon": "📋", "label": "Хэрэг"},
        {"id": "reports", "icon": "📈", "label": "Тайлан"},
    ],
    "taug": [
        {"id": "received", "icon": "📥", "label": "Хүлээн авсан"},
        {"id": "assign", "icon": "👤", "label": "Хуваарилалт"},
        {"id": "outsrc", "icon": "🏢", "label": "Outsourcing"},
        {"id": "reqlog", "icon": "📋", "label": "Хүсэлт бүртгэл"},
    ],
    "outsourcing": [
        {"id": "cases", "icon": "📋", "label": "Миний хэрэг"},
        {"id": "perf", "icon": "📊", "label": "Гүйцэтгэл"},
        {"id": "commission", "icon": "💰", "label": "Commission"},
    ],
    "senior": [
        {"id": "dash", "icon": "📊", "label": "Дашбоард"},
        {"id": "perf", "icon": "🏆", "label": "Гүйцэтгэл"},
        {"id": "time", "icon": "⏱️", "label": "Хугацаа"},
        {"id": "queue", "icon": "📋", "label": "Queue"},
    ],
    "mgmt": [
        {"id": "dash", "icon": "📊", "label": "Дашбоард"},
        {"id": "kpi", "icon": "🎯", "label": "KPI"},
        {"id": "outsrc", "icon": "🏢", "label": "Outsourcing"},
        {"id": "reports", "icon": "📈", "label": "Тайлан"},
    ],
}


def get_base_context():
    """Build the shared context passed to every dashboard template."""
    role = session.get("role", "bpuh")
    return {
        "role": role,
        "user_name": session.get("user_name", "Зочин"),
        "role_name": session.get("role_name", ""),
        "role_sub": session.get("role_sub", ""),
        "role_color": session.get("role_color", "#2563EB"),
        "nav_items": NAV_ITEMS.get(role, []),
        "risk_levels": RISK_LEVELS,  # Pass to all templates for legend
    }


@dashboard_bp.route("/dashboard")
def dashboard():
    """Main dashboard — routes to the correct template based on session role."""
    role = session.get("role")
    if not role:
        return redirect(url_for("auth.index"))

    ctx = get_base_context()

    builders = {
        "bpuh": _build_bpuh,
        "zm": _build_zm,
        "jdbbg": _build_jdbbg,
        "taug": _build_taug,
        "outsourcing": _build_outsourcing,
        "senior": _build_senior,
        "mgmt": _build_mgmt,
    }
    builder = builders.get(role, _build_bpuh)
    template, data = builder()
    ctx.update(data)

    return render_template(template, **ctx)
@dashboard_bp.route("/case/<int:case_id>")
def case_detail(case_id):
    """Borrower/case detail page."""
    role = session.get("role")
    if not role:
        return redirect(url_for("auth.index"))

    case = CollectionCase.query.get_or_404(case_id)
    loan = Loan.query.get(case.loan_id)
    borrower = Borrower.query.get(loan.borrower_id) if loan else None

    # Get all actions for this case
    actions = (CaseAction.query
               .filter_by(case_id=case.id)
               .order_by(CaseAction.created_at.desc())
               .all())

    # Get transfers for this case
    transfers = (CaseTransfer.query
                 .filter_by(case_id=case.id)
                 .order_by(CaseTransfer.transfer_date.desc())
                 .all())

    # Risk score
    from app.services.scoring import calculate_risk_score
    from sqlalchemy import func
    last_action_date = (db.session.query(func.max(CaseAction.created_at))
                        .filter(CaseAction.case_id == case.id)
                        .scalar())
    risk = calculate_risk_score(case, loan, last_action_date)

    ctx = get_base_context()
    ctx.update({
        "case": case,
        "loan": loan,
        "borrower": borrower,
        "actions": actions,
        "transfers": transfers,
        "risk": risk,
    })
    return render_template("dashboard/case_detail.html", **ctx)


# ── БПҮХ ──────────────────────────────────────────────────
def _build_bpuh():
    cases_raw = (
        db.session.query(CollectionCase, Loan, Borrower)
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Borrower.segment == "consumer")
        .order_by(CollectionCase.days_overdue.desc())
        .limit(50)
        .all()
    )

    # Apply risk scoring (returns sorted by risk, highest first)
    scored_cases = score_cases(cases_raw)

    total = len(scored_cases)
    promises = sum(1 for c, l, b, r in scored_cases if c.status == "promise")
    over90 = sum(1 for c, l, b, r in scored_cases if c.days_overdue > 90)
    critical = sum(1 for c, l, b, r in scored_cases if r["level"] == "critical")

    return "dashboard/bpuh.html", {
        "kpis": [
            {"label": "Нийт хэрэг", "value": total, "sub": "Миний хариуцсан"},
            {"label": "🔴 Яаралтай", "value": critical, "sub": "Нэн даруй анхаарах"},
            {"label": "Амлалт авсан", "value": promises, "sub": "Энэ долоо хоногт"},
            {"label": "Хугацаа >90 хоног", "value": over90, "sub": "Анхаарах шаардлагатай"},
        ],
        "scored_cases": scored_cases,
    }


# ── ЗМ ────────────────────────────────────────────────────
def _build_zm():
    user = User.query.get(session.get("user_id"))
    branch = user.branch if user else "Баянзүрх"

    cases_raw = (
        db.session.query(CollectionCase, Loan, Borrower)
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Loan.branch == branch)
        .order_by(CollectionCase.days_overdue.desc())
        .limit(100)
        .all()
    )

    scored_cases = score_cases(cases_raw)

    total = len(scored_cases)
    total_amount = sum(c.overdue_amount for c, l, b, r in scored_cases)
    transferred = sum(1 for c, l, b, r in scored_cases if c.status == "transferred")
    critical = sum(1 for c, l, b, r in scored_cases if r["level"] == "critical")

    months = ["1-р сар", "2-р сар", "3-р сар", "4-р сар", "5-р сар", "6-р сар"]
    payments = [280, 310, 265, 295, 320, 340]

    return "dashboard/zm.html", {
        "kpis": [
            {"label": "Нийт зөрчилтэй", "value": total, "sub": f"{branch} салбар"},
            {"label": "🔴 Яаралтай", "value": critical, "sub": "Нэн даруй анхаарах"},
            {"label": "Нийт дүн", "value": f"{total_amount/1e9:.1f} тэрбум₮", "sub": "Зөрчилтэй зээлийн дүн"},
            {"label": "ТАУГ шилжүүлсэн", "value": transferred, "sub": "Энэ сард"},
        ],
        "scored_cases": scored_cases,
        "chart_months": months,
        "chart_payments": payments,
        "branch": branch,
    }


# ── ЖДББГ ─────────────────────────────────────────────────
def _build_jdbbg():
    cases_raw = (
        db.session.query(CollectionCase, Loan, Borrower)
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Borrower.segment == "corporate")
        .order_by(CollectionCase.days_overdue.desc())
        .all()
    )

    scored_cases = score_cases(cases_raw)

    # Group by company
    companies = {}
    for c, l, b, r in scored_cases:
        if b.name not in companies:
            companies[b.name] = {
                "cases": [],
                "total_loans": 0,
                "delinquent_amount": 0,
                "worst_risk": r,
            }
        companies[b.name]["cases"].append((c, l, b, r))
        companies[b.name]["total_loans"] += l.amount
        companies[b.name]["delinquent_amount"] += c.overdue_amount
        # Track worst risk per company
        if r["score"] > companies[b.name]["worst_risk"]["score"]:
            companies[b.name]["worst_risk"] = r

    total_companies = len(companies)
    total_cases = len(scored_cases)
    total_amount = sum(c.overdue_amount for c, l, b, r in scored_cases)
    resolved = sum(1 for c, l, b, r in scored_cases if c.status == "resolved")

    return "dashboard/jdbbg.html", {
        "kpis": [
            {"label": "Хариуцсан компани", "value": total_companies},
            {"label": "Зөрчилтэй зээл", "value": total_cases},
            {"label": "Нийт дүн", "value": f"{total_amount/1e9:.1f} тэрбум₮"},
            {"label": "Шийдвэрлэсэн", "value": resolved, "sub": "Энэ улиралд"},
        ],
        "companies": companies,
        "scored_cases": scored_cases,
    }


# ── ТАУГ ──────────────────────────────────────────────────
def _build_taug():
    cases_raw = (
        db.session.query(CollectionCase, Loan, Borrower)
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(CollectionCase.status.in_(["transferred", "legal", "court", "outsourced"]))
        .order_by(CollectionCase.updated_at.desc())
        .all()
    )

    scored_cases = score_cases(cases_raw)

    transfers = CaseTransfer.query.order_by(CaseTransfer.transfer_date.desc()).limit(20).all()

    total = len(scored_cases)
    legal = sum(1 for c, l, b, r in scored_cases if c.status == "legal")
    court = sum(1 for c, l, b, r in scored_cases if c.status == "court")
    outsourced = sum(1 for c, l, b, r in scored_cases if c.status == "outsourced")

    return "dashboard/taug.html", {
        "kpis": [
            {"label": "Хүлээн авсан", "value": total, "sub": "Энэ сард"},
            {"label": "ТАХ ажилтанд", "value": legal, "sub": "Хуваарилагдсан"},
            {"label": "Хуулийн фирмд", "value": court},
            {"label": "Outsourcing", "value": outsourced, "sub": "Барьцаагүй зээл"},
        ],
        "scored_cases": scored_cases,
        "transfers": transfers,
    }


# ── OUTSOURCING ───────────────────────────────────────────
def _build_outsourcing():
    assignments = (
        db.session.query(OutsourcingAssignment, CollectionCase, Loan)
        .join(CollectionCase, OutsourcingAssignment.case_id == CollectionCase.id)
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .all()
    )

    total = len(assignments)
    collected = sum(a.collected_amount for a, c, l in assignments)
    commission = sum(a.collected_amount * a.commission_rate for a, c, l in assignments)
    completed = sum(1 for a, c, l in assignments if a.status == "completed")
    success_rate = round((completed / total * 100) if total > 0 else 0)

    return "dashboard/outsourcing.html", {
        "kpis": [
            {"label": "Хариуцсан хэрэг", "value": total},
            {"label": "Цуглуулсан дүн", "value": f"{collected/1e6:.0f} сая₮"},
            {"label": "Commission", "value": f"{commission/1e6:.1f} сая₮", "sub": "Нийт тооцоо"},
            {"label": "Амжилтын хувь", "value": f"{success_rate}%", "sub": f"{completed} хэрэг шийдвэрлэсэн"},
        ],
        "assignments": [(a, c, l) for a, c, l in assignments],
    }


# ── ЗЭГ АХЛАХ ────────────────────────────────────────────
def _build_senior():
    collectors = (
        db.session.query(
            User,
            func.count(CollectionCase.id).label("case_count"),
        )
        .join(CollectionCase, CollectionCase.assigned_to == User.id)
        .filter(User.role.in_(["bpuh", "zm", "jdbbg"]))
        .group_by(User.id)
        .all()
    )

    collector_stats = []
    for user, case_count in collectors:
        action_count = CaseAction.query.filter_by(user_id=user.id).count()
        resolved = CollectionCase.query.filter_by(assigned_to=user.id, status="resolved").count()
        success_rate = round((resolved / case_count * 100) if case_count > 0 else 0)
        collector_stats.append({
            "name": user.name,
            "cases": case_count,
            "actions": action_count,
            "success_rate": success_rate,
            "avg_days": round(2.0 + (100 - success_rate) * 0.03, 1),
        })

    collector_stats.sort(key=lambda x: x["success_rate"], reverse=True)

    total_collectors = len(collectors)
    no_action_cases = CollectionCase.query.filter_by(status="new").count()

    return "dashboard/senior.html", {
        "kpis": [
            {"label": "Нийт Collector", "value": total_collectors},
            {"label": "Хугацаандаа хийсэн", "value": "78%", "sub": "Зорилт: 90%"},
            {"label": "Roll Forward", "value": "12%", "sub": "Сүүлийн сард"},
            {"label": "Ажилбаргүй хэрэг", "value": no_action_cases, "sub": "Анхаарах шаардлагатай"},
        ],
        "collectors": collector_stats,
    }


# ── УДИРДЛАГА ─────────────────────────────────────────────
def _build_mgmt():
    total_cases = CollectionCase.query.count()
    total_amount = db.session.query(func.sum(CollectionCase.overdue_amount)).scalar() or 0
    court = CollectionCase.query.filter_by(status="court").count()
    court_pct = round((court / total_cases * 100) if total_cases > 0 else 0)

    os_data = (
        db.session.query(
            OutsourcingAssignment.company_name,
            func.count(OutsourcingAssignment.id).label("total"),
            func.sum(OutsourcingAssignment.collected_amount).label("collected"),
        )
        .group_by(OutsourcingAssignment.company_name)
        .all()
    )

    outsourcing_perf = []
    for company, total, collected in os_data:
        outsourcing_perf.append({
            "company": company,
            "total": total,
            "collected": collected or 0,
            "commission": round((collected or 0) * 0.10),
        })

    branch_data = (
        db.session.query(
            Loan.branch,
            func.count(CollectionCase.id).label("total"),
            func.sum(CollectionCase.overdue_amount).label("amount"),
        )
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .group_by(Loan.branch)
        .all()
    )

    branch_perf = []
    for branch, count, amount in branch_data:
        branch_perf.append({
            "branch": branch,
            "cases": count,
            "amount": amount or 0,
        })

    chart_months = ["1-р сар", "2-р сар", "3-р сар", "4-р сар", "5-р сар", "6-р сар"]
    chart_values = [1200, 1350, 1100, 1450, 1580, 1820]

    return "dashboard/mgmt.html", {
        "kpis": [
            {"label": "Нийт зөрчилтэй", "value": f"{total_cases:,}", "sub": "Бүх салбар"},
            {"label": "Нийт дүн", "value": f"{total_amount/1e9:.1f} тэрбум₮"},
            {"label": "Эхний дуудлагаар төлсөн", "value": "23%", "sub": "Зорилт: 30%"},
            {"label": "Шүүхэд шилжсэн", "value": f"{court_pct}%", "sub": f"{court} хэрэг"},
        ],
        "outsourcing_perf": outsourcing_perf,
        "branch_perf": branch_perf,
        "chart_months": chart_months,
        "chart_values": chart_values,
    }
