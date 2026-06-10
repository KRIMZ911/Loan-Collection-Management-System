"""
Database models for the Collection Management System.
All models use SQLAlchemy ORM with SQLite (easily switchable to PostgreSQL).
"""
from datetime import datetime, date
from app import db


class User(db.Model):
    """System users — collectors, supervisors, managers, outsourcing agents."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # bpuh, zm, jdbbg, taug, outsourcing, senior, mgmt
    branch = db.Column(db.String(50))
    email = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    assigned_cases = db.relationship("CollectionCase", backref="assigned_user", lazy="dynamic")
    actions = db.relationship("CaseAction", backref="user", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "branch": self.branch,
            "email": self.email,
            "is_active": self.is_active,
        }


class Borrower(db.Model):
    """Loan borrowers — individuals or companies."""
    __tablename__ = "borrowers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    register_no = db.Column(db.String(20))  # Mongolian registration number
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.String(300))
    segment = db.Column(db.String(20), default="consumer")  # consumer / corporate
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    loans = db.relationship("Loan", backref="borrower", lazy="dynamic")

    def to_dict(self, hide_personal=False):
        """Serialize to dict. hide_personal=True for outsourcing view."""
        if hide_personal:
            return {
                "id": self.id,
                "name": "***",
                "segment": self.segment,
            }
        return {
            "id": self.id,
            "name": self.name,
            "register_no": self.register_no,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "segment": self.segment,
        }


class Loan(db.Model):
    """Individual loan accounts."""
    __tablename__ = "loans"

    id = db.Column(db.Integer, primary_key=True)
    borrower_id = db.Column(db.Integer, db.ForeignKey("borrowers.id"), nullable=False)
    loan_number = db.Column(db.String(20), unique=True, nullable=False)
    product_type = db.Column(db.String(50))  # consumer, mortgage, sme, corporate, credit_card
    amount = db.Column(db.Float, nullable=False)  # Original loan amount in MNT
    balance = db.Column(db.Float, nullable=False)  # Current outstanding balance
    disbursement_date = db.Column(db.Date)
    maturity_date = db.Column(db.Date)
    interest_rate = db.Column(db.Float)  # Annual interest rate %
    status = db.Column(db.String(20), default="active")  # active, closed, written_off
    branch = db.Column(db.String(50))

    # Relationships
    collection_cases = db.relationship("CollectionCase", backref="loan", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "borrower_id": self.borrower_id,
            "loan_number": self.loan_number,
            "product_type": self.product_type,
            "amount": self.amount,
            "balance": self.balance,
            "disbursement_date": str(self.disbursement_date) if self.disbursement_date else None,
            "maturity_date": str(self.maturity_date) if self.maturity_date else None,
            "interest_rate": self.interest_rate,
            "status": self.status,
            "branch": self.branch,
        }


class CollectionCase(db.Model):
    """A delinquent loan case being tracked in the collection system."""
    __tablename__ = "collection_cases"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    days_overdue = db.Column(db.Integer, default=0)
    overdue_amount = db.Column(db.Float, default=0)
    priority = db.Column(db.String(10), default="medium")  # high, medium, low
    status = db.Column(db.String(20), default="new")
    # Statuses: new, contacted, promise, no_answer, transferred, legal, court, outsourced, resolved
    queue = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    actions = db.relationship("CaseAction", backref="case", lazy="dynamic", order_by="CaseAction.created_at.desc()")
    transfers = db.relationship("CaseTransfer", backref="case", lazy="dynamic")
    outsourcing = db.relationship("OutsourcingAssignment", backref="case", lazy="dynamic")
    decisions = db.relationship("CommitteeDecision", backref="case", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "assigned_to": self.assigned_to,
            "days_overdue": self.days_overdue,
            "overdue_amount": self.overdue_amount,
            "priority": self.priority,
            "status": self.status,
            "queue": self.queue,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CaseAction(db.Model):
    """Actions taken on a collection case (calls, letters, meetings, etc.)."""
    __tablename__ = "case_actions"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("collection_cases.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action_type = db.Column(db.String(30), nullable=False)
    # Types: phone_call, official_letter, meeting, promise_letter, note, collateral_check, transfer
    outcome = db.Column(db.String(30))
    # Outcomes: promise_made, no_answer, payment_made, callback, transfer_to_taug, transfer_to_outsourcing
    notes = db.Column(db.Text)
    scheduled_follow_up = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "outcome": self.outcome,
            "notes": self.notes,
            "scheduled_follow_up": self.scheduled_follow_up.isoformat() if self.scheduled_follow_up else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CaseTransfer(db.Model):
    """Transfer of a case between entities (e.g., branch -> TAUG)."""
    __tablename__ = "case_transfers"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("collection_cases.id"), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    to_entity = db.Column(db.String(50), nullable=False)  # Target role/entity
    transfer_date = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.Text)
    materials_attached = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="pending")  # pending, accepted, completed

    from_user = db.relationship("User", backref="transfers_sent")

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "from_user_id": self.from_user_id,
            "to_entity": self.to_entity,
            "transfer_date": self.transfer_date.isoformat() if self.transfer_date else None,
            "reason": self.reason,
            "materials_attached": self.materials_attached,
            "status": self.status,
        }


class OutsourcingAssignment(db.Model):
    """Assignment of unsecured loan cases to outsourcing companies."""
    __tablename__ = "outsourcing_assignments"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("collection_cases.id"), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    assigned_date = db.Column(db.Date, default=date.today)
    commission_rate = db.Column(db.Float, default=0.10)  # 10% default
    collected_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default="active")  # active, completed, cancelled

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "company_name": self.company_name,
            "assigned_date": str(self.assigned_date) if self.assigned_date else None,
            "commission_rate": self.commission_rate,
            "collected_amount": self.collected_amount,
            "status": self.status,
        }


class CommitteeDecision(db.Model):
    """Decisions made by the Loan Committee regarding collection cases."""
    __tablename__ = "committee_decisions"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("collection_cases.id"), nullable=False)
    decision_date = db.Column(db.Date, default=date.today)
    decision_text = db.Column(db.Text, nullable=False)
    next_action = db.Column(db.String(200))
    deadline = db.Column(db.Date)
    status = db.Column(db.String(20), default="pending")  # pending, completed, overdue

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "decision_date": str(self.decision_date) if self.decision_date else None,
            "decision_text": self.decision_text,
            "next_action": self.next_action,
            "deadline": str(self.deadline) if self.deadline else None,
            "status": self.status,
        }
