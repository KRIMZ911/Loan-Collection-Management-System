"""
REST API endpoints for the Collection Management System.
All endpoints return JSON and check session for role-based access.
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, session
from app import db
from app.models import (
    CollectionCase, CaseAction, CaseTransfer, Loan, Borrower,
    User, OutsourcingAssignment, CommitteeDecision,
)
from sqlalchemy import func

api_bp = Blueprint("api", __name__)


def _require_role():
    """Check that a role is set in the session."""
    if "role" not in session:
        return jsonify({"error": "Нэвтрээгүй байна"}), 401
    return None


@api_bp.route("/cases")
def list_cases():
    """List collection cases filtered by the current user's role."""
    err = _require_role()
    if err:
        return err

    role = session["role"]
    hide_personal = (role == "outsourcing")

    query = (
        db.session.query(CollectionCase, Loan, Borrower)
        .join(Loan, CollectionCase.loan_id == Loan.id)
        .join(Borrower, Loan.borrower_id == Borrower.id)
    )

    # Role-based filtering
    if role == "bpuh":
        query = query.filter(Borrower.segment == "consumer")
    elif role == "zm":
        user = User.query.get(session.get("user_id"))
        if user:
            query = query.filter(Loan.branch == user.branch)
    elif role == "jdbbg":
        query = query.filter(Borrower.segment == "corporate")
    elif role == "taug":
        query = query.filter(
            CollectionCase.status.in_(["transferred", "legal", "court", "outsourced"])
        )
    elif role == "outsourcing":
        os_case_ids = [a.case_id for a in OutsourcingAssignment.query.all()]
        query = query.filter(CollectionCase.id.in_(os_case_ids))

    results = query.order_by(CollectionCase.days_overdue.desc()).limit(100).all()

    cases = []
    for case, loan, borrower in results:
        cases.append({
            **case.to_dict(),
            "loan": loan.to_dict(),
            "borrower": borrower.to_dict(hide_personal=hide_personal),
        })

    return jsonify({"cases": cases, "total": len(cases)})


@api_bp.route("/cases/<int:case_id>")
def case_detail(case_id):
    """Get detailed information about a single case."""
    err = _require_role()
    if err:
        return err

    case = CollectionCase.query.get_or_404(case_id)
    loan = Loan.query.get(case.loan_id)
    borrower = Borrower.query.get(loan.borrower_id) if loan else None

    hide_personal = (session["role"] == "outsourcing")

    actions = [a.to_dict() for a in case.actions.order_by(CaseAction.created_at.desc()).all()]
    transfers = [t.to_dict() for t in case.transfers.all()]
    decisions = [d.to_dict() for d in case.decisions.all()]

    return jsonify({
        "case": case.to_dict(),
        "loan": loan.to_dict() if loan else None,
        "borrower": borrower.to_dict(hide_personal=hide_personal) if borrower else None,
        "actions": actions,
        "transfers": transfers,
        "decisions": decisions,
    })


@api_bp.route("/cases/<int:case_id>/actions", methods=["POST"])
def create_action(case_id):
    """Log a new action on a collection case."""
    err = _require_role()
    if err:
        return err

    case = CollectionCase.query.get_or_404(case_id)
    data = request.get_json()

    if not data or "action_type" not in data:
        return jsonify({"error": "action_type шаардлагатай"}), 400

    action = CaseAction(
        case_id=case.id,
        user_id=session.get("user_id"),
        action_type=data["action_type"],
        outcome=data.get("outcome"),
        notes=data.get("notes", ""),
        scheduled_follow_up=(
            datetime.fromisoformat(data["scheduled_follow_up"])
            if data.get("scheduled_follow_up") else None
        ),
    )
    db.session.add(action)

    # Update case status based on outcome
    outcome = data.get("outcome")
    if outcome == "promise_made":
        case.status = "promise"
    elif outcome == "no_answer":
        case.status = "no_answer"
    elif outcome == "payment_made":
        case.status = "resolved"
    elif outcome in ("transfer_to_taug", "transfer_to_outsourcing"):
        case.status = "transferred"

    case.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Амжилттай бүртгэгдлээ!", "action": action.to_dict()}), 201


@api_bp.route("/cases/<int:case_id>/transfer", methods=["POST"])
def create_transfer(case_id):
    """Transfer a case to another entity."""
    err = _require_role()
    if err:
        return err

    case = CollectionCase.query.get_or_404(case_id)
    data = request.get_json()

    if not data or "to_entity" not in data:
        return jsonify({"error": "to_entity шаардлагатай"}), 400

    transfer = CaseTransfer(
        case_id=case.id,
        from_user_id=session.get("user_id"),
        to_entity=data["to_entity"],
        reason=data.get("reason", ""),
        materials_attached=data.get("materials_attached", False),
    )
    db.session.add(transfer)

    case.status = "transferred"
    case.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Амжилттай шилжүүлэгдлээ!", "transfer": transfer.to_dict()}), 201


@api_bp.route("/stats")
def stats():
    """Aggregate statistics for senior/management dashboards."""
    err = _require_role()
    if err:
        return err

    total_cases = CollectionCase.query.count()
    total_amount = db.session.query(func.sum(CollectionCase.overdue_amount)).scalar() or 0
    resolved = CollectionCase.query.filter_by(status="resolved").count()
    new_cases = CollectionCase.query.filter_by(status="new").count()

    status_breakdown = (
        db.session.query(CollectionCase.status, func.count(CollectionCase.id))
        .group_by(CollectionCase.status)
        .all()
    )

    return jsonify({
        "total_cases": total_cases,
        "total_amount": total_amount,
        "resolved": resolved,
        "new_cases": new_cases,
        "status_breakdown": {s: c for s, c in status_breakdown},
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
            func.count(CollectionCase.id).label("case_count"),
        )
        .join(CollectionCase, CollectionCase.assigned_to == User.id)
        .filter(User.role.in_(["bpuh", "zm", "jdbbg"]))
        .group_by(User.id)
        .all()
    )

    result = []
    for user, case_count in collectors:
        action_count = CaseAction.query.filter_by(user_id=user.id).count()
        resolved = CollectionCase.query.filter_by(assigned_to=user.id, status="resolved").count()
        result.append({
            "user": user.to_dict(),
            "cases": case_count,
            "actions": action_count,
            "resolved": resolved,
            "success_rate": round((resolved / case_count * 100) if case_count > 0 else 0),
        })

    result.sort(key=lambda x: x["success_rate"], reverse=True)
    return jsonify({"collectors": result})

@api_bp.route("/cases/<int:case_id>/quick-action", methods=["POST"])
def quick_action(case_id):
    """One-click quick action — auto-generates note from outcome."""
    err = _require_role()
    if err:
        return err

    case = CollectionCase.query.get_or_404(case_id)
    data = request.get_json() or {}
    action_type = data.get("action_type", "phone_call")
    outcome = data.get("outcome", "callback")

    # Auto-generate note based on outcome
    auto_notes = {
        "callback": "Утсаар холбогдож, төлбөрийн талаар мэдэгдсэн.",
        "promise_made": "Зээлдэгч төлнө гэж амласан.",
        "no_answer": "Утас авсангүй, дахин залгах шаардлагатай.",
        "payment_made": "Төлбөр хийгдсэн.",
    }
    note = auto_notes.get(outcome, "Үйлдэл бүртгэсэн.")

    action = CaseAction(
        case_id=case.id,
        user_id=session.get("user_id"),
        action_type=action_type,
        outcome=outcome,
        notes=note,
    )
    db.session.add(action)

    # Update case status
    status_map = {
        "promise_made": "promise",
        "no_answer": "no_answer",
        "payment_made": "resolved",
    }
    if outcome in status_map:
        case.status = status_map[outcome]

    case.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Амжилттай!", "action": action.to_dict()}), 201