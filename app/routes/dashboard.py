"""
Dashboard routes — FINAL version with SimpleNamespace wrappers.
Templates stay untouched. Wrappers translate new model attrs to old names.
"""

from types import SimpleNamespace
from flask import Blueprint, render_template, session, redirect, url_for
from sqlalchemy import func
from app import db
from app.models import (
    User, Borrower, Loan, ContactLog, CaseTransfer,
    OutsourcingAssignment, CommitteeReview, Role,
    LoanStatus, SegmentType,
)
from app.services.scoring import score_cases, RISK_LEVELS


dashboard_bp = Blueprint("dashboard", __name__)


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
    role = session.get("role", "bpuh")
    return {
        "role": role,
        "user_name": session.get("user_name", "Зочин"),
        "role_name": session.get("role_name", ""),
        "role_sub": session.get("role_sub", ""),
        "role_color": session.get("role_color", "#2563EB"),
        "nav_items": NAV_ITEMS.get(role, []),
        "risk_levels": RISK_LEVELS,
    }


# ── SimpleNamespace wrappers: new model attrs → old template names ──

def _w_case(loan):
    """Wrap Loan as old CollectionCase for templates."""
    return SimpleNamespace(
        id=loan.id,
        days_overdue=loan.delinquency_days or 0,
        overdue_amount=float(loan.amount_overdue or 0),
        status=loan.status.value if loan.status else "active",
        updated_at=loan.updated_at,
    )


def _w_loan(loan):
    """Wrap Loan with old attribute names for templates."""
    return SimpleNamespace(
        id=loan.id,
        amount=float(loan.amount_original or 0),
        balance=float(loan.amount_outstanding or 0),
        loan_number=loan.loan_account_number,
        product_type=loan.loan_product.name if loan.loan_product else None,
        branch=loan.branch.name if loan.branch else "—",
        interest_rate=float(loan.interest_rate or 0),
        disbursement_date=loan.disbursement_date,
        maturity_date=loan.maturity_date,
    )


def _w_borrower(borrower, hide=False):
    """Wrap Borrower with old attribute names."""
    if hide:
        return SimpleNamespace(name="***", register_no="***", phone="***", email="***", address="***")
    return SimpleNamespace(
        name=f"{borrower.last_name} {borrower.first_name}",
        register_no=borrower.register_number,
        phone=borrower.phone_primary,
        email=borrower.email,
        address=borrower.address_residential,
    )


def _w_risk(risk_info):
    """Flatten risk_info dict into a dot-accessible namespace."""
    rl = risk_info.get('risk_level', {})
    return SimpleNamespace(
        score=risk_info.get('score', 0),
        css_class=rl.get('css_class', 'risk-low'),
        emoji=rl.get('emoji', ''),
        label_mn=rl.get('label_mn', ''),
        color=rl.get('color', '#16A34A'),
        level=rl.get('level', 'low'),
    )


def _w_action(cl):
    """Wrap ContactLog as old CaseAction."""
    return SimpleNamespace(
        created_at=cl.contact_date,
        action_type=cl.contact_type.value if cl.contact_type else 'note',
        outcome='no_answer' if not cl.was_reached else 'contacted',
        notes=cl.notes or '',
    )


def _w_transfer(t):
    """Wrap CaseTransfer with safe attribute access."""
    return SimpleNamespace(
        transfer_date=t.transfer_date,
        to_entity=t.to_entity,
        reason=t.reason or '',
        status=t.status.value if t.status else 'pending',
    )


def _pack_scored(scored):
    """Convert score_cases output to template-friendly 4-tuples."""
    return [(_w_case(l), _w_loan(l), _w_borrower(b), _w_risk(r)) for l, b, r in scored]


def _build_kpis(scored):
    total = len(scored)
    total_amount = sum(float(l.amount_overdue or 0) for l, b, r in scored)
    high_risk = sum(1 for l, b, r in scored if r.get('score', 0) >= 50)
    return [
        {"label": "Нийт хэрэг", "value": total, "sub": "Зөрчилтэй зээл"},
        {"label": "Нийт дүн", "value": f"{total_amount:,.0f} ₮", "sub": "Хэтэрсэн өр"},
        {"label": "Өндөр эрсдэл", "value": high_risk, "sub": "Эрсдэл 50+"},
    ]


@dashboard_bp.route("/dashboard")
def dashboard():
    role = session.get("role")
    if not role:
        return redirect(url_for("auth.index"))
    builders = {
        "bpuh": _build_bpuh, "zm": _build_zm, "jdbbg": _build_jdbbg,
        "taug": _build_taug, "outsourcing": _build_outsourcing,
        "senior": _build_senior, "mgmt": _build_mgmt,
    }
    return builders.get(role, _build_bpuh)()


@dashboard_bp.route("/case/<int:loan_id>")
def case_detail(loan_id):
    role = session.get("role")
    if not role:
        return redirect(url_for("auth.index"))
    loan = Loan.query.get_or_404(loan_id)
    borrower = Borrower.query.get(loan.borrower_id)
    hide = (role == "outsourcing")
    contacts = ContactLog.query.filter_by(loan_id=loan.id).order_by(ContactLog.contact_date.desc()).limit(50).all()
    transfers = CaseTransfer.query.filter_by(loan_id=loan.id).all()
    scored = score_cases([(loan, borrower)])
    ri = scored[0][2] if scored else {}
    ctx = get_base_context()
    ctx.update({
        "loan": _w_loan(loan),
        "case": _w_case(loan),
        "borrower": _w_borrower(borrower, hide=hide) if borrower else SimpleNamespace(name="—", register_no="—", phone="—", email="—", address="—"),
        "risk": _w_risk(ri),
        "actions": [_w_action(c) for c in contacts],
        "transfers": [_w_transfer(t) for t in transfers],
    })
    return render_template("dashboard/case_detail.html", **ctx)


def _build_bpuh():
    cases_raw = (
        db.session.query(Loan, Borrower)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Borrower.segment == SegmentType.RETAIL)
        .filter(Loan.delinquency_days > 0)
        .order_by(Loan.delinquency_days.desc())
        .limit(50).all()
    )
    scored = score_cases(cases_raw)
    ctx = get_base_context()
    ctx.update({"scored_cases": _pack_scored(scored), "kpis": _build_kpis(scored)})
    return render_template("dashboard/bpuh.html", **ctx)


def _build_zm():
    user = User.query.get(session.get("user_id"))
    branch_id = user.branch_id if user else None
    branch_name = user.branch.name if user and user.branch else "—"
    query = (
        db.session.query(Loan, Borrower)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Loan.delinquency_days > 0)
    )
    if branch_id:
        query = query.filter(Loan.branch_id == branch_id)
    cases_raw = query.order_by(Loan.delinquency_days.desc()).all()
    scored = score_cases(cases_raw)
    months = ['1-р сар', '2-р сар', '3-р сар', '4-р сар', '5-р сар', '6-р сар']
    import random; payments = [random.randint(3, 15) for _ in months]
    ctx = get_base_context()
    ctx.update({
        "scored_cases": _pack_scored(scored),
        "kpis": _build_kpis(scored),
        "branch": branch_name,
        "chart_months": months,
        "chart_payments": payments,
    })
    return render_template("dashboard/zm.html", **ctx)


def _build_jdbbg():
    cases_raw = (
        db.session.query(Loan, Borrower)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Borrower.segment == SegmentType.SMB)
        .filter(Loan.delinquency_days > 0)
        .order_by(Loan.delinquency_days.desc()).all()
    )
    scored = score_cases(cases_raw)
    # Group by borrower name as 'companies'
    companies = {}
    for loan, borrower, risk_info in scored:
        name = f"{borrower.last_name} {borrower.first_name}"
        if name not in companies:
            companies[name] = SimpleNamespace(
                worst_risk=_w_risk(risk_info),
                cases=[],
                delinquent_amount=0,
                total_loans=0,
            )
        c = companies[name]
        c.cases.append((_w_case(loan), _w_loan(loan), _w_borrower(borrower), _w_risk(risk_info)))
        c.delinquent_amount += float(loan.amount_overdue or 0)
        c.total_loans += 1
        if risk_info.get('score', 0) > c.worst_risk.score:
            c.worst_risk = _w_risk(risk_info)
    ctx = get_base_context()
    ctx.update({"companies": companies, "kpis": _build_kpis(scored)})
    return render_template("dashboard/jdbbg.html", **ctx)


def _build_taug():
    cases_raw = (
        db.session.query(Loan, Borrower)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Loan.status.in_([
            LoanStatus.TRANSFERRED_TAUG, LoanStatus.LEGAL,
            LoanStatus.COURT, LoanStatus.OUTSOURCED,
        ]))
        .order_by(Loan.updated_at.desc()).all()
    )
    scored = score_cases(cases_raw)
    ctx = get_base_context()
    ctx.update({"scored_cases": _pack_scored(scored), "kpis": _build_kpis(scored)})
    return render_template("dashboard/taug.html", **ctx)


def _build_outsourcing():
    rows = (
        db.session.query(OutsourcingAssignment, Loan, Borrower)
        .join(Loan, OutsourcingAssignment.loan_id == Loan.id)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .all()
    )
    assignments = [(oa, _w_case(loan), _w_loan(loan)) for oa, loan, b in rows]
    total_assigned = sum(float(l.amount_overdue or 0) for oa, l, b in rows)
    total_collected = sum(float(oa.collected_amount or 0) for oa, l, b in rows)
    kpis = [
        {"label": "Нийт хэрэг", "value": len(assignments), "sub": "Хуваарилагдсан"},
        {"label": "Нийт дүн", "value": f"{total_assigned:,.0f} ₮", "sub": "Хэтэрсэн өр"},
        {"label": "Цуглуулсан", "value": f"{total_collected:,.0f} ₮", "sub": f"{round((total_collected/total_assigned*100) if total_assigned>0 else 0)}%"},
    ]
    ctx = get_base_context()
    ctx.update({"assignments": assignments, "kpis": kpis})
    return render_template("dashboard/outsourcing.html", **ctx)


def _build_senior():
    rows = (
        db.session.query(User, func.count(Loan.id).label('cc'))
        .join(Loan, Loan.assigned_to == User.id)
        .filter(Loan.delinquency_days > 0)
        .group_by(User.id).all()
    )
    collectors = []
    for user, cc in rows:
        ac = ContactLog.query.filter_by(contacted_by=user.id).count()
        res = Loan.query.filter_by(assigned_to=user.id, status=LoanStatus.RESOLVED).count()
        avg_d = db.session.query(func.avg(Loan.delinquency_days)).filter(Loan.assigned_to==user.id, Loan.delinquency_days>0).scalar() or 0
        collectors.append(SimpleNamespace(
            name=user.name, cases=cc, actions=ac, resolved=res,
            success_rate=round((res/cc*100) if cc>0 else 0),
            avg_days=round(avg_d),
        ))
    collectors.sort(key=lambda x: x.success_rate, reverse=True)
    total_d = Loan.query.filter(Loan.delinquency_days > 0).count()
    total_a = float(db.session.query(func.sum(Loan.amount_overdue)).filter(Loan.delinquency_days > 0).scalar() or 0)
    kpis = [
        {"label": "Нийт хэрэг", "value": total_d, "sub": "Зөрчилтэй"},
        {"label": "Нийт дүн", "value": f"{total_a:,.0f} ₮", "sub": "Хэтэрсэн өр"},
        {"label": "Ажилтан", "value": len(collectors), "sub": "Хянагч"},
    ]
    ctx = get_base_context()
    ctx.update({"collectors": collectors, "kpis": kpis})
    return render_template("dashboard/senior.html", **ctx)


def _build_mgmt():
    total_loans = Loan.query.count()
    total_d = Loan.query.filter(Loan.delinquency_days > 0).count()
    total_a = float(db.session.query(func.sum(Loan.amount_overdue)).filter(Loan.delinquency_days > 0).scalar() or 0)
    resolved = Loan.query.filter_by(status=LoanStatus.RESOLVED).count()
    court = Loan.query.filter_by(status=LoanStatus.COURT).count()
    court_pct = round((court/total_d*100) if total_d>0 else 0)
    kpis = [
        {"label": "Нийт зээл", "value": total_loans, "sub": "Нийт багц"},
        {"label": "Зөрчилтэй", "value": total_d, "sub": f"{round(total_d/total_loans*100) if total_loans>0 else 0}%"},
        {"label": "Нийт дүн", "value": f"{total_a:,.0f} ₮", "sub": "Хэтэрсэн өр"},
        {"label": "Шүүх", "value": court, "sub": f"{court_pct}%"},
    ]
    months = ['1-р сар','2-р сар','3-р сар','4-р сар','5-р сар','6-р сар']
    import random; chart_values = [random.randint(5,30) for _ in months]
    # Outsourcing perf
    os_rows = (
        db.session.query(OutsourcingAssignment.company_name, func.count(OutsourcingAssignment.id), func.sum(OutsourcingAssignment.collected_amount))
        .group_by(OutsourcingAssignment.company_name).all()
    )
    outsourcing_perf = [SimpleNamespace(company=n, total=c, collected=float(s or 0), commission=round(float(s or 0)*0.1)) for n,c,s in os_rows]
    # Branch perf
    from app.models import Branch
    br_rows = (
        db.session.query(Branch.name, func.count(Loan.id))
        .join(Loan, Loan.branch_id == Branch.id)
        .filter(Loan.delinquency_days > 0)
        .group_by(Branch.name).all()
    )
    branch_perf = [SimpleNamespace(branch=n, cases=c) for n,c in br_rows]
    ctx = get_base_context()
    ctx.update({
        "kpis": kpis,
        "chart_months": months,
        "chart_values": chart_values,
        "outsourcing_perf": outsourcing_perf,
        "branch_perf": branch_perf,
        "total_cases": total_d,
        "total_amount": total_a,
        "resolved": resolved,
        "court": court,
        "court_pct": court_pct,
    })
    return render_template("dashboard/mgmt.html", **ctx)

