"""
REST API endpoints for the Collection Management System.
All endpoints return JSON and check session for role-based access.

Updated for new models.py:
  - CollectionCase removed — Loan is the central table
  - CaseAction → ContactLog
  - CommitteeDecision → CommitteeReview
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, session
from sqlalchemy import func
from app import db
from app.models import (
    Loan, Borrower, User, ContactLog, CaseTransfer,
    OutsourcingAssignment, CommitteeReview,
    LoanStatus, SegmentType, ContactType, ContactDirection,
)


api_bp = Blueprint("api", __name__)


def _require_role():
    """Check that a role is set in the session."""
    if "role" not in session:
        return jsonify({"error": "Нэвтрээгүй байна"}), 401
    return None


@api_bp.route("/cases")
def list_cases():
    """List delinquent loans filtered by the current user\'s role."""
    err = _require_role()
    if err:
        return err
    role = session["role"]
    hide_personal = (role == "outsourcing")
    query = (
        db.session.query(Loan, Borrower)
        .join(Borrower, Loan.borrower_id == Borrower.id)
    )
    # Role-based filtering
    if role == "bpuh":
        query = query.filter(
            Borrower.segment == SegmentType.RETAIL,
            Loan.delinquency_days > 0,
        )
    elif role == "zm":
        user = User.query.get(session.get("user_id"))
        if user and user.branch_id:
            query = query.filter(Loan.branch_id == user.branch_id)
        query = query.filter(Loan.delinquency_days > 0)
    elif role == "jdbbg":
        query = query.filter(
            Borrower.segment == SegmentType.SMB,
            Loan.delinquency_days > 0,
        )
    elif role == "taug":
        query = query.filter(
            Loan.status.in_([
                LoanStatus.TRANSFERRED_TAUG,
                LoanStatus.LEGAL,
                LoanStatus.COURT,
                LoanStatus.OUTSOURCED,
            ])
        )
    elif role == "outsourcing":
        os_loan_ids = [a.loan_id for a in OutsourcingAssignment.query.all()]
        query = query.filter(Loan.id.in_(os_loan_ids))
    else:
        # senior, mgmt — see everything delinquent
        query = query.filter(Loan.delinquency_days > 0)
    results = query.order_by(Loan.delinquency_days.desc()).limit(100).all()
    cases = []
    for loan, borrower in results:
        cases.append({
            **loan.to_dict(),
            "loan": loan.to_dict(),  # backward compat
            "borrower": borrower.to_dict(hide_personal=hide_personal),
        })
    return jsonify({"cases": cases, "total": len(cases)})


@api_bp.route("/cases/<int:loan_id>")
def case_detail(loan_id):
    """Get detailed information about a single loan/case."""
    err = _require_role()
    if err:
        return err
    loan = Loan.query.get_or_404(loan_id)
    borrower = Borrower.query.get(loan.borrower_id)
    hide_personal = (session["role"] == "outsourcing")
    contacts = [
        c.to_dict() for c in
        ContactLog.query.filter_by(loan_id=loan.id)
        .order_by(ContactLog.contact_date.desc())
        .all()
    ]
    transfers = [t.to_dict() for t in CaseTransfer.query.filter_by(loan_id=loan.id).all()]
    decisions = [
        d.to_dict() for d in
        CommitteeReview.query.filter_by(loan_id=loan.id)
        .order_by(CommitteeReview.meeting_date.desc())
        .all()
    ]
    return jsonify({
        "case": loan.to_dict(),  # backward compat key
        "loan": loan.to_dict(),
        "borrower": borrower.to_dict(hide_personal=hide_personal) if borrower else None,
        "actions": contacts,  # backward compat key
        "contacts": contacts,
        "transfers": transfers,
        "decisions": decisions,
    })


@api_bp.route("/cases/<int:loan_id>/actions", methods=["POST"])
def create_action(loan_id):
    """Log a new contact/action on a loan."""
    err = _require_role()
    if err:
        return err
    loan = Loan.query.get_or_404(loan_id)
    data = request.get_json()
    if not data or "action_type" not in data:
        return jsonify({"error": "action_type шаардлагатай"}), 400
    # Map action_type string to ContactType enum
    contact_type_map = {
        "phone_call": ContactType.PHONE_CALL,
        "sms": ContactType.SMS,
        "email": ContactType.EMAIL,
        "official_letter": ContactType.OFFICIAL_NOTICE,
        "meeting": ContactType.IN_PERSON_VISIT,
        "note": ContactType.PHONE_CALL,  # default for generic notes
        "promise_letter": ContactType.COMMITMENT_LETTER,
    }
    ct = contact_type_map.get(data["action_type"], ContactType.PHONE_CALL)
    # Map outcome to was_reached boolean
    outcome = data.get("outcome")
    was_reached = outcome not in ("no_answer", None)
    contact = ContactLog(
        loan_id=loan.id,
        borrower_id=loan.borrower_id,
        contact_type=ct,
        contact_direction=ContactDirection.OUTBOUND,
        was_reached=was_reached,
        notes=data.get("notes", ""),
        promised_payment_date=(
            datetime.fromisoformat(data["scheduled_follow_up"])
            if data.get("scheduled_follow_up") else None
        ),
        contacted_by=session.get("user_id"),
        contact_date=datetime.now(timezone.utc),
    )
    db.session.add(contact)
    # Update loan status based on outcome
    if outcome == "promise_made":
        loan.status = LoanStatus.DELINQUENT
    elif outcome == "payment_made":
        loan.status = LoanStatus.RESOLVED
    elif outcome in ("transfer_to_taug", "transfer_to_outsourcing"):
        loan.status = LoanStatus.TRANSFERRED_TAUG
    loan.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"message": "Амжилттай бүртгэгдлээ!", "action": contact.to_dict()}), 201


@api_bp.route("/cases/<int:loan_id>/transfer", methods=["POST"])
def create_transfer(loan_id):
    """Transfer a loan case to another entity."""
    err = _require_role()
    if err:
        return err
    loan = Loan.query.get_or_404(loan_id)
    data = request.get_json()
    if not data or "to_entity" not in data:
        return jsonify({"error": "to_entity шаардлагатай"}), 400
    transfer = CaseTransfer(
        loan_id=loan.id,
        from_user_id=session.get("user_id"),
        to_entity=data["to_entity"],
        reason=data.get("reason", ""),
        materials_attached=data.get("materials_attached", False),
    )
    db.session.add(transfer)
    loan.status = LoanStatus.TRANSFERRED_TAUG
    loan.is_transferred_to_taug = True
    loan.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"message": "Амжилттай шилжүүлэгдлээ!", "transfer": transfer.to_dict()}), 201


@api_bp.route("/stats")
def stats():
    """Aggregate statistics for senior/management dashboards."""
    err = _require_role()
    if err:
        return err
    total_cases = Loan.query.filter(Loan.delinquency_days > 0).count()
    total_amount = (
        db.session.query(func.sum(Loan.amount_overdue))
        .filter(Loan.delinquency_days > 0)
        .scalar() or 0
    )
    resolved = Loan.query.filter_by(status=LoanStatus.RESOLVED).count()
    new_cases = Loan.query.filter(
        Loan.delinquency_days > 0,
        Loan.delinquency_days <= 5,
    ).count()
    status_breakdown = (
        db.session.query(Loan.status, func.count(Loan.id))
        .filter(Loan.delinquency_days > 0)
        .group_by(Loan.status)
        .all()
    )
    return jsonify({
        "total_cases": total_cases,
        "total_amount": float(total_amount),
        "resolved": resolved,
        "new_cases": new_cases,
        "status_breakdown": {s.value if hasattr(s, 'value') else str(s): c for s, c in status_breakdown},
    })


@api_bp.route("/collectors/performance")
def collector_performance():
    """Performance data for all collectors."""
    err = _require_role()
    if err:
        return err
    collectors = (
        db.session.query(
            User,
            func.count(Loan.id).label("case_count"),
        )
        .join(Loan, Loan.assigned_to == User.id)
        .filter(Loan.delinquency_days > 0)
        .group_by(User.id)
        .all()
    )
    result = []
    for user, case_count in collectors:
        contact_count = ContactLog.query.filter_by(contacted_by=user.id).count()
        resolved = Loan.query.filter_by(assigned_to=user.id, status=LoanStatus.RESOLVED).count()
        result.append({
            "user": user.to_dict(),
            "cases": case_count,
            "actions": contact_count,  # backward compat key
            "contacts": contact_count,
            "resolved": resolved,
            "success_rate": round((resolved / case_count * 100) if case_count > 0 else 0),
        })
    result.sort(key=lambda x: x["success_rate"], reverse=True)
    return jsonify({"collectors": result})


@api_bp.route("/cases/<int:loan_id>/quick-action", methods=["POST"])
def quick_action(loan_id):
    """One-click quick action — auto-generates note from outcome."""
    err = _require_role()
    if err:
        return err
    loan = Loan.query.get_or_404(loan_id)
    data = request.get_json() or {}
    action_type = data.get("action_type", "phone_call")
    outcome = data.get("outcome", "callback")
    # Map to ContactType
    ct_map = {
        "phone_call": ContactType.PHONE_CALL,
        "sms": ContactType.SMS,
        "email": ContactType.EMAIL,
        "meeting": ContactType.IN_PERSON_VISIT,
    }
    ct = ct_map.get(action_type, ContactType.PHONE_CALL)
    # Auto-generate note based on outcome
    auto_notes = {
        "callback": "Утсаар холбогдож, төлбөрийн талаар мэдэгдсэн.",
        "promise_made": "Зээлдэгч төлнө гэж амласан.",
        "no_answer": "Утас авсангүй, дахин залгах шаардлагатай.",
        "payment_made": "Төлбөр хийгдсэн.",
    }
    note = auto_notes.get(outcome, "Үйлдэл бүртгэсэн.")
    contact = ContactLog(
        loan_id=loan.id,
        borrower_id=loan.borrower_id,
        contact_type=ct,
        contact_direction=ContactDirection.OUTBOUND,
        was_reached=(outcome != "no_answer"),
        notes=note,
        contacted_by=session.get("user_id"),
        contact_date=datetime.now(timezone.utc),
    )
    db.session.add(contact)
    # Update loan status
    status_map = {
        "promise_made": LoanStatus.DELINQUENT,
        "no_answer": LoanStatus.DELINQUENT,
        "payment_made": LoanStatus.RESOLVED,
    }
    if outcome in status_map:
        loan.status = status_map[outcome]
    loan.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"message": "Амжилттай!", "action": contact.to_dict()}), 201



@api_bp.route("/deepwork/queue")
def deepwork_queue():
    """Get paginated queue of delinquent loans for deep work mode."""
    err = _require_role()
    if err:
        return err

    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    # Query delinquent loans ordered by days desc (highest priority first)
    rows = (
        db.session.query(Loan, Borrower)
        .join(Borrower, Loan.borrower_id == Borrower.id)
        .filter(Loan.delinquency_days > 0)
        .order_by(Loan.delinquency_days.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    # Import scoring
    from app.services.scoring import score_cases
    scored = score_cases(rows)

    cases = []
    for loan, borrower, risk_info in scored:
        # Recent contacts (last 5)
        contacts = (
            ContactLog.query
            .filter_by(loan_id=loan.id)
            .order_by(ContactLog.contact_date.desc())
            .limit(5)
            .all()
        )
        recent = []
        for cl in contacts:
            recent.append({
                "date": cl.contact_date.strftime("%m/%d %H:%M") if cl.contact_date else "",
                "type_icon": {"phone_call": "\U0001f4de", "sms": "\U0001f4f1", "email": "\U0001f4e7", "in_person_visit": "\U0001f6b6"}.get(cl.contact_type.value if cl.contact_type else "", "\U0001f4cb"),
                "type_label": {"phone_call": "\u0423\u0442\u0430\u0441", "sms": "SMS", "email": "\u0418-\u043c\u044d\u0439\u043b", "in_person_visit": "\u0423\u0443\u043b\u0437\u0430\u043b\u0442"}.get(cl.contact_type.value if cl.contact_type else "", "\u0411\u0443\u0441\u0430\u0434"),
                "was_reached": cl.was_reached,
                "notes": cl.notes[:50] if cl.notes else "",
            })

        # No-answer streak
        streak = 0
        for cl in contacts:
            if not cl.was_reached:
                streak += 1
            else:
                break

        # Broken promise check
        broken = None
        from datetime import date
        for cl in contacts:
            if cl.promised_payment_date and cl.promised_payment_date < date.today():
                broken = cl.promised_payment_date.strftime("%Y-%m-%d")
                break

        # Related parties
        from app.models import RelatedParty
        parties_raw = RelatedParty.query.filter_by(borrower_id=borrower.id).all()
        parties = [{"name": p.name, "phone": p.phone_primary or "", "relationship": p.relationship or p.party_type.value} for p in parties_raw]

        rl = risk_info.get("risk_level", {})
        cases.append({
            "loan_id": loan.id,
            "borrower_name": f"{borrower.last_name} {borrower.first_name}",
            "register_no": borrower.register_number,
            "phone_primary": borrower.phone_primary,
            "phone_secondary": borrower.phone_secondary,
            "email": borrower.email,
            "address": borrower.address_residential,
            "loan_amount": float(loan.amount_original or 0),
            "balance": float(loan.amount_outstanding or 0),
            "overdue_amount": float(loan.amount_overdue or 0),
            "days_overdue": loan.delinquency_days,
            "product_type": loan.loan_product.name if loan.loan_product else None,
            "branch": loan.branch.name if loan.branch else None,
            "classification": loan.classification.value if loan.classification else "normal",
            "escalation_stage": loan.current_escalation_stage or 0,
            "loan_number": loan.loan_account_number,
            "risk_score": risk_info.get("score", 0),
            "risk_level": rl.get("level", "low"),
            "recent_contacts": recent,
            "no_answer_streak": streak,
            "broken_promise": broken,
            "related_parties": parties,
        })

    return jsonify({"cases": cases, "page": page, "total": len(cases)})


@api_bp.route("/deepwork/action", methods=["POST"])
def deepwork_action():
    """Save an action from deep work mode."""
    err = _require_role()
    if err:
        return err

    data = request.get_json()
    if not data or "loan_id" not in data:
        return jsonify({"error": "loan_id \u0448\u0430\u0430\u0440\u0434\u043b\u0430\u0433\u0430\u0442\u0430\u0439"}), 400

    loan = Loan.query.get(data["loan_id"])
    if not loan:
        return jsonify({"error": "\u0417\u044d\u044d\u043b \u043e\u043b\u0434\u0441\u043e\u043d\u0433\u04af\u0439"}), 404

    # Map contact type
    ct_map = {
        "phone_call": ContactType.PHONE_CALL,
        "sms": ContactType.SMS,
        "email": ContactType.EMAIL,
        "visit": ContactType.IN_PERSON_VISIT,
    }
    ct = ct_map.get(data.get("contact_type"), ContactType.PHONE_CALL)

    promised_date = None
    if data.get("promised_date"):
        from datetime import date as dt_date
        try:
            parts = data["promised_date"].split("-")
            promised_date = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            pass

    contact = ContactLog(
        loan_id=loan.id,
        borrower_id=loan.borrower_id,
        contact_type=ct,
        contact_direction=ContactDirection.OUTBOUND,
        was_reached=data.get("was_reached", False),
        notes=data.get("notes", ""),
        promised_payment_date=promised_date,
        contacted_by=session.get("user_id"),
        contact_date=datetime.now(timezone.utc),
    )
    db.session.add(contact)

    # Update status if payment made
    outcome = data.get("outcome")
    if outcome == "payment_made":
        loan.status = LoanStatus.RESOLVED

    loan.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"message": "\u0410\u043c\u0436\u0438\u043b\u0442\u0442\u0430\u0439!"}), 201
