"""
=============================================================================
Collection System — SQLAlchemy Models (UPDATED — Full Bank Data Coverage)
=============================================================================
Зээлийн өр барагдуулалтын системийн мэдээллийн сангийн бүтэц.

UPDATES IN THIS VERSION:
  - 34 new fields added to cover both BPUH Excel reports (97% / 100% coverage)
  - NEW table: DepositAccount (deposit/payment accounts per borrower)
  - Borrower: workplace_name, phone_home, phone_work
  - Loan: 22 new fields (interest breakdown, off-balance, model calc, etc.)
  - Collateral: coverage_percent, is_unregistered

Source documents:
  - Excess process all.xlsx
  - Excess conference all.xlsx
  - Зээлийн үйл ажиллагааны матрит (түр).xlsx
  - Өр үүссэн зээлийн мэдээ-Шинэ.xlsx (BPUH daily report v1)
  - 2nd_version BPUH daily report (v2)

Total: 26 tables, ~314 fields
=============================================================================
"""

import enum
from datetime import datetime, date, timezone
from typing import Optional

from app import db


# ============================================================================
# ENUMS
# ============================================================================

class SegmentType(enum.Enum):
    """Сегментийн төрөл"""
    RETAIL = "retail"
    SMB = "smb"


class PartyType(enum.Enum):
    """Холбоотой этгээдийн төрөл"""
    CO_BORROWER = "co_borrower"
    GUARANTOR = "guarantor"
    COLLATERAL_PROVIDER = "collateral_provider"
    FAMILY_MEMBER = "family_member"


class ContactType(enum.Enum):
    """Холбогдох төрөл"""
    PHONE_CALL = "phone_call"
    SMS = "sms"
    EMAIL = "email"
    IN_PERSON_VISIT = "in_person_visit"
    OFFICIAL_NOTICE = "official_notice"
    COMMITMENT_LETTER = "commitment_letter"


class ContactDirection(enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class ActionType(enum.Enum):
    """Авах арга хэмжээний төрөл"""
    REPORT_PULLED = "report_pulled"
    SMS_SENT = "sms_sent"
    EMAIL_SENT = "email_sent"
    CALL_MADE = "call_made"
    BRANCH_NOTIFIED = "branch_notified"
    VISIT_CONDUCTED = "visit_conducted"
    COMMITMENT_OBTAINED = "commitment_obtained"
    OFFICIAL_NOTICE_SENT = "official_notice_sent"
    INSURANCE_TRANSFER = "insurance_transfer"
    RESTRUCTURE_PROPOSED = "restructure_proposed"
    COMMITTEE_SUBMITTED = "committee_submitted"
    TAUG_TRANSFER = "taug_transfer"
    COLLATERAL_REVIEW = "collateral_review"
    LEGAL_NOTICE = "legal_notice"
    ZBDS_CLAIM = "zbds_claim"
    MATERIAL_HANDOVER = "material_handover"


class CommitteeType(enum.Enum):
    ZDKH = "zdkh"
    CHAKH = "chakh"
    ZKH = "zkh"
    BZZ = "bzz"


class CommitteeDecisionType(enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    RESTRUCTURE = "restructure"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    MAINTAIN = "maintain"
    TRANSFER_TAUG = "transfer_taug"


class ReviewStatus(enum.Enum):
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    DECIDED = "decided"
    FINALIZED = "finalized"


class ClassificationLevel(enum.Enum):
    NORMAL = "normal"
    WATCH = "watch"
    SUBSTANDARD = "substandard"
    DOUBTFUL = "doubtful"
    LOSS = "loss"


class LoanStatus(enum.Enum):
    ACTIVE = "active"
    DELINQUENT = "delinquent"
    RESTRUCTURED = "restructured"
    TRANSFERRED_TAUG = "transferred_taug"
    OUTSOURCED = "outsourced"
    LEGAL = "legal"
    COURT = "court"
    CLOSED = "closed"
    WRITTEN_OFF = "written_off"
    RESOLVED = "resolved"


class CollateralType(enum.Enum):
    REAL_ESTATE = "real_estate"
    MOVABLE_PROPERTY = "movable_property"
    VEHICLE = "vehicle"
    DEPOSIT = "deposit"
    INTANGIBLE = "intangible"


class CollateralStatus(enum.Enum):
    ACTIVE = "active"
    DAMAGED = "damaged"
    DESTROYED = "destroyed"
    MISSING = "missing"
    SEIZED = "seized"
    SOLD = "sold"


class DocumentType(enum.Enum):
    COMMITMENT_LETTER = "commitment_letter"
    OFFICIAL_NOTICE = "official_notice"
    LEGAL_NOTICE = "legal_notice"
    ZBDS_CLAIM = "zbds_claim"
    HANDOVER_ANNEX = "handover_annex"
    COMMITTEE_MATERIAL = "committee_material"
    MEETING_NOTES = "meeting_notes"
    CONTRACT = "contract"
    PERSONAL_FILE_CHECKLIST = "personal_file_checklist"


class DocumentStatus(enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SIGNED = "signed"
    DELIVERED = "delivered"
    ARCHIVED = "archived"


class NotificationType(enum.Enum):
    DELINQUENT_HBZ = "delinquent_hbz"
    PENSION_MONTHLY = "pension_monthly"
    NO_CONTACT_INFO = "no_contact_info"
    COMMITTEE_SCHEDULE = "committee_schedule"
    CLASSIFICATION_CHANGE = "classification_change"
    ACTION_OVERDUE = "action_overdue"
    ESCALATION_TRIGGER = "escalation_trigger"


class NotificationChannel(enum.Enum):
    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"


class NotificationStatus(enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    READ = "read"
    FAILED = "failed"


class PermissionType(enum.Enum):
    EXECUTE = "execute"
    CONTROL = "control"
    DUAL_CONTROL = "dual_control"
    SUPPORT = "support"
    SUBSTITUTE = "substitute"


class InsuranceDecision(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    PAID = "paid"


class RestructureDecision(enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class EscalationFrequency(enum.Enum):
    DAILY = "daily"
    AS_NEEDED = "as_needed"
    MONTHLY = "monthly"
    NONE = "none"


class TransferStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    REJECTED = "rejected"


class OutsourcingStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RETURNED = "returned"


# NEW ENUM for DepositAccount
class DepositAccountType(enum.Enum):
    """Депозит дансны төрөл — type of deposit account"""
    PAYMENT = "payment"      # Тоlбөр төлөх данс
    SAVINGS = "savings"      # Хадгаламжийн данс
    CURRENT = "current"      # Харилцах данс
    OTHER = "other"          # Бусад


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _utcnow():
    return datetime.now(timezone.utc)


def _date_to_str(d):
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _enum_to_str(e):
    if e is None:
        return None
    return e.value if hasattr(e, "value") else str(e)


def _to_float(v):
    """Safely convert Decimal/None to float for JSON."""
    if v is None:
        return None
    return float(v)


# ============================================================================
# MODELS — Organisational Structure (unchanged)
# ============================================================================

class Segment(db.Model):
    """Сегмент — Retail / SMB"""
    __tablename__ = "segments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    segment_type = db.Column(db.Enum(SegmentType), nullable=False)
    department_code = db.Column(db.String(20))

    regions = db.relationship("Region", back_populates="segment", lazy="dynamic")
    loan_products = db.relationship("LoanProduct", back_populates="segment", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "segment_type": _enum_to_str(self.segment_type),
            "department_code": self.department_code,
        }

    def __repr__(self):
        return f"<Segment {self.name}>"


class Region(db.Model):
    """Бүс — Regional grouping"""
    __tablename__ = "regions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    segment_id = db.Column(db.Integer, db.ForeignKey("segments.id"), nullable=False)

    segment = db.relationship("Segment", back_populates="regions")
    branches = db.relationship("Branch", back_populates="region", lazy="dynamic")
    users = db.relationship("User", back_populates="region", lazy="dynamic")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "segment_id": self.segment_id}

    def __repr__(self):
        return f"<Region {self.name}>"


class Branch(db.Model):
    """Салбар — Bank branch"""
    __tablename__ = "branches"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), unique=True)
    region_id = db.Column(db.Integer, db.ForeignKey("regions.id"), nullable=False)
    address = db.Column(db.String(300))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))

    region = db.relationship("Region", back_populates="branches")
    users = db.relationship("User", back_populates="branch", lazy="dynamic")
    borrowers = db.relationship("Borrower", back_populates="branch", lazy="dynamic")
    loans = db.relationship("Loan", back_populates="branch", lazy="dynamic")
    notifications = db.relationship("Notification", back_populates="recipient_branch", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "region_id": self.region_id,
            "address": self.address,
            "email": self.email,
            "phone": self.phone,
        }

    def __repr__(self):
        return f"<Branch {self.code} — {self.name}>"


class Role(db.Model):
    """Албан тушаал — Staff roles"""
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    name_mn = db.Column(db.String(150), nullable=False)
    name_en = db.Column(db.String(150))
    dashboard_code = db.Column(db.String(20))

    users = db.relationship("User", back_populates="role", lazy="dynamic")
    permissions = db.relationship("Permission", back_populates="role", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name_mn": self.name_mn,
            "name_en": self.name_en,
            "dashboard_code": self.dashboard_code,
        }

    def __repr__(self):
        return f"<Role {self.code}>"


class User(db.Model):
    """Хэрэглэгч / Ажилтан"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(30), unique=True)
    username = db.Column(db.String(80), unique=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150))
    password_hash = db.Column(db.String(256))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))
    region_id = db.Column(db.Integer, db.ForeignKey("regions.id"))
    segment_id = db.Column(db.Integer, db.ForeignKey("segments.id"))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    role = db.relationship("Role", back_populates="users")
    branch = db.relationship("Branch", back_populates="users")
    region = db.relationship("Region", back_populates="users")
    segment = db.relationship("Segment")

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "name": self.name,
            "email": self.email,
            "role": self.role.code if self.role else None,
            "role_name": self.role.name_mn if self.role else None,
            "branch": self.branch.name if self.branch else None,
            "branch_id": self.branch_id,
            "region": self.region.name if self.region else None,
            "region_id": self.region_id,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<User {self.name}>"


class Permission(db.Model):
    """Эрхийн матриц"""
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    process_step_code = db.Column(db.String(10), nullable=False)
    permission_type = db.Column(db.Enum(PermissionType), nullable=False)
    permission_level = db.Column(db.String(5))
    description = db.Column(db.Text)

    role = db.relationship("Role", back_populates="permissions")

    __table_args__ = (db.Index("ix_permissions_role_step", "role_id", "process_step_code"),)

    def to_dict(self):
        return {
            "id": self.id,
            "role_id": self.role_id,
            "process_step_code": self.process_step_code,
            "permission_type": _enum_to_str(self.permission_type),
            "permission_level": self.permission_level,
            "description": self.description,
        }

    def __repr__(self):
        return f"<Permission role={self.role_id} step={self.process_step_code}>"

# ============================================================================
# MODELS — Annual Goals (NEW for Phase E.1)
# ============================================================================

class GoalCategory(db.Model):
    """
    Зорилтын ангилал — KPI categories that can have annual goals.

    Each category defines WHAT to track (savings accounts, credit cards, etc.).
    Adding a new category = insert a row + add a counting function in
    goal_tracking.py. No schema migration needed.
    """
    __tablename__ = "goal_categories"

    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(50), unique=True, nullable=False)
    name_mn     = db.Column(db.String(100), nullable=False)
    icon        = db.Column(db.String(10), default="🎯")
    unit_mn     = db.Column(db.String(20), default="ширхэг")
    is_active   = db.Column(db.Boolean, default=True)
    sort_order  = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=_utcnow)

    # Reverse relationship — all goals using this category
    goals = db.relationship("AnnualGoal", back_populates="category")

    def __repr__(self):
        return f"<GoalCategory {self.code}>"


class AnnualGoal(db.Model):
    """
    Жилийн зорилт — Annual KPI target for a (year, branch, category).

    Set by regional directors (or executives override).
    Branch directors see them but can't edit them in Phase E.
    Worker-level goals deferred to Phase E.4.
    """
    __tablename__ = "annual_goals"

    id              = db.Column(db.Integer, primary_key=True)
    year            = db.Column(db.Integer, nullable=False, index=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    category_id     = db.Column(db.Integer, db.ForeignKey("goal_categories.id"), nullable=False)

    target_count    = db.Column(db.Integer, nullable=False, default=0)
    set_by_user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    set_at          = db.Column(db.DateTime, default=_utcnow)
    notes           = db.Column(db.Text, nullable=True)

    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    deleted_at         = db.Column(db.DateTime, nullable=True, index=True)
    deleted_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at      = db.Column(db.DateTime, default=_utcnow)
    updated_at      = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    branch    = db.relationship("Branch")
    category  = db.relationship("GoalCategory", back_populates="goals")
    set_by    = db.relationship("User", foreign_keys=[set_by_user_id])

    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])      # 🆕
    deleted_by = db.relationship("User", foreign_keys=[deleted_by_user_id])      # 🆕

    # Only ONE non-deleted goal per (year, branch, category).
    # Soft-deleted rows (deleted_at IS NOT NULL) are exempt from uniqueness
    # so the audit trail can preserve old deleted goals + new ones.
    __table_args__ = (
        db.Index(
            "uq_active_goal_per_branch",
            "year", "branch_id", "category_id",
            unique=True,
            sqlite_where=db.text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self):
        return f"<AnnualGoal {self.year} branch={self.branch_id} cat={self.category_id}>"


# ============================================================================
# MODELS — User Widget Preferences (NEW for Phase I)
# ============================================================================

class UserWidgetPreference(db.Model):
    """
    Хэрэглэгчийн виджет тохиргоо — Per-user customization for the
    home dashboard. One row per (user, widget_id) combo.
    """
    __tablename__ = "user_widget_preferences"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    widget_id    = db.Column(db.String(60), nullable=False)
    sort_order   = db.Column(db.Integer, default=0)
    is_enabled   = db.Column(db.Boolean, default=True)

    created_at   = db.Column(db.DateTime, default=_utcnow)
    updated_at   = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    user         = db.relationship("User")

    # Unique: one preference row per (user, widget)
    __table_args__ = (
        db.UniqueConstraint("user_id", "widget_id", name="uq_user_widget"),
    )

    def __repr__(self):
        return f"<UserWidgetPreference user={self.user_id} widget={self.widget_id}>"

class LoanProduct(db.Model):
    """Бүтээгдэхүүний төрөл"""
    __tablename__ = "loan_products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    category = db.Column(db.String(100))
    segment_id = db.Column(db.Integer, db.ForeignKey("segments.id"))
    is_digital = db.Column(db.Boolean, default=False)
    auto_sms_day = db.Column(db.Integer)

    segment = db.relationship("Segment", back_populates="loan_products")
    loans = db.relationship("Loan", back_populates="loan_product", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "is_digital": self.is_digital,
            "auto_sms_day": self.auto_sms_day,
        }

    def __repr__(self):
        return f"<LoanProduct {self.name}>"


class SourceSystem(db.Model):
    """Эх системүүд"""
    __tablename__ = "source_systems"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name, "description": self.description}

    def __repr__(self):
        return f"<SourceSystem {self.code}>"


# ============================================================================
# MODEL — Borrower (UPDATED: 3 new fields)
# ============================================================================

class Borrower(db.Model):
    """
    Зээлдэгч — The central person/entity who took the loan.

    UPDATED: Added workplace_name, phone_home, phone_work for BPUH Excel coverage.
    """
    __tablename__ = "borrowers"

    id = db.Column(db.Integer, primary_key=True)
    cif_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    last_name = db.Column(db.String(80), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    register_number = db.Column(db.String(20), unique=True, index=True)

    # Contact
    phone_primary = db.Column(db.String(20))
    phone_secondary = db.Column(db.String(20))
    phone_verified = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(150))

    # 🆕 NEW: Additional phone numbers
    phone_home = db.Column(db.String(20))    # Гэрийн утас
    phone_work = db.Column(db.String(20))    # Ажлын утас

    # Address
    address_residential = db.Column(db.String(500))
    address_work = db.Column(db.String(500))
    address_verified = db.Column(db.Boolean, default=False)

    # 🆕 NEW: Workplace
    workplace_name = db.Column(db.String(300))    # Ажлын газар

    # Status
    employment_status = db.Column(db.String(50))
    income_source = db.Column(db.String(100))
    health_status = db.Column(db.String(100))
    is_deceased = db.Column(db.Boolean, default=False)

    # Organisation
    segment = db.Column(db.Enum(SegmentType))
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    branch = db.relationship("Branch", back_populates="borrowers")
    loans = db.relationship("Loan", back_populates="borrower", lazy="dynamic")
    related_parties = db.relationship("RelatedParty", back_populates="borrower", lazy="dynamic")
    contact_logs = db.relationship("ContactLog", back_populates="borrower", lazy="dynamic")
    deposit_accounts = db.relationship("DepositAccount", back_populates="borrower", lazy="dynamic")  # 🆕

    __table_args__ = (db.Index("ix_borrowers_name", "last_name", "first_name"),)

    def to_dict(self, hide_personal=False):
        if hide_personal:
            return {
                "id": self.id,
                "name": "***",
                "segment": _enum_to_str(self.segment),
                "branch_id": self.branch_id,
            }
        return {
            "id": self.id,
            "cif_number": self.cif_number,
            "name": f"{self.last_name} {self.first_name}",
            "last_name": self.last_name,
            "first_name": self.first_name,
            "register_number": self.register_number,
            "phone": self.phone_primary,
            "phone_primary": self.phone_primary,
            "phone_secondary": self.phone_secondary,
            "phone_home": self.phone_home,       # 🆕
            "phone_work": self.phone_work,       # 🆕
            "phone_verified": self.phone_verified,
            "email": self.email,
            "address": self.address_residential,
            "address_residential": self.address_residential,
            "address_work": self.address_work,
            "address_verified": self.address_verified,
            "workplace_name": self.workplace_name,  # 🆕
            "employment_status": self.employment_status,
            "income_source": self.income_source,
            "is_deceased": self.is_deceased,
            "segment": _enum_to_str(self.segment),
            "branch_id": self.branch_id,
        }

    def __repr__(self):
        return f"<Borrower {self.cif_number} — {self.last_name}>"


# ============================================================================
# MODEL — RelatedParty (unchanged)
# ============================================================================

class RelatedParty(db.Model):
    """Холбоотой этгээдүүд — Co-borrowers, guarantors, family"""
    __tablename__ = "related_parties"

    id = db.Column(db.Integer, primary_key=True)
    borrower_id = db.Column(db.Integer, db.ForeignKey("borrowers.id"), nullable=False)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"))
    party_type = db.Column(db.Enum(PartyType), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    register_number = db.Column(db.String(20))
    phone_primary = db.Column(db.String(20))
    phone_verified = db.Column(db.Boolean, default=False)
    relationship = db.Column(db.String(100))
    address = db.Column(db.String(500))
    employment_status = db.Column(db.String(50))

    borrower = db.relationship("Borrower", back_populates="related_parties")
    loan = db.relationship("Loan", back_populates="related_parties")
    contact_logs = db.relationship("ContactLog", back_populates="related_party", lazy="dynamic")

    __table_args__ = (db.Index("ix_related_parties_borrower", "borrower_id"),)

    def to_dict(self):
        return {
            "id": self.id,
            "borrower_id": self.borrower_id,
            "loan_id": self.loan_id,
            "party_type": _enum_to_str(self.party_type),
            "name": self.name,
            "register_number": self.register_number,
            "phone_primary": self.phone_primary,
            "phone_verified": self.phone_verified,
            "relationship": self.relationship,
            "address": self.address,
            "employment_status": self.employment_status,
        }

    def __repr__(self):
        return f"<RelatedParty {self.party_type.value}: {self.name}>"



# ============================================================================
# MODEL — Loan (UPDATED: 22 new fields for BPUH Excel coverage)
# ============================================================================

class Loan(db.Model):
    """
    Зээл — THE CENTRAL TABLE. Individual loan account + delinquency tracking.

    UPDATED: Added 22 fields covering BPUH daily Excel reports:
      - 2 staff assignments (analyst, relationship manager)
      - 4 tracking dates/balances (theoretical, last payment, review, notes)
      - 8 overdue principal/interest breakdown fields
      - 3 accrued interest amounts
      - 4 off-balance account fields
      - 2 model calculation fields
    """
    __tablename__ = "loans"

    id = db.Column(db.Integer, primary_key=True)
    borrower_id = db.Column(db.Integer, db.ForeignKey("borrowers.id"), nullable=False)
    loan_product_id = db.Column(db.Integer, db.ForeignKey("loan_products.id"))
    loan_account_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    contract_number = db.Column(db.String(50))

    # Financials
    amount_original = db.Column(db.Numeric(18, 2), nullable=False)
    amount_outstanding = db.Column(db.Numeric(18, 2))
    amount_overdue = db.Column(db.Numeric(18, 2), default=0)
    currency = db.Column(db.String(3), default="MNT")
    interest_rate = db.Column(db.Numeric(6, 3))

    # Term
    term_months = db.Column(db.Integer)
    disbursement_date = db.Column(db.Date)
    maturity_date = db.Column(db.Date)
    payment_schedule_type = db.Column(db.String(50))

    # Status & Classification
    status = db.Column(db.Enum(LoanStatus), default=LoanStatus.ACTIVE, nullable=False)
    classification = db.Column(db.Enum(ClassificationLevel), default=ClassificationLevel.NORMAL, nullable=False)

    # Delinquency tracking
    delinquency_days = db.Column(db.Integer, default=0, nullable=False, index=True)
    delinquency_start_date = db.Column(db.Date)
    current_escalation_stage = db.Column(db.Integer, default=0)
    priority = db.Column(db.String(10), default="medium")

    # Insurance & Transfers
    is_insurance_eligible = db.Column(db.Boolean, default=False)
    is_transferred_to_taug = db.Column(db.Boolean, default=False)
    taug_transfer_date = db.Column(db.Date)
    restructure_count = db.Column(db.Integer, default=0)
    has_zbds_guarantee = db.Column(db.Boolean, default=False)

    # Assignment (existing)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_zm_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_zkha_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # 🆕 GROUP A — Additional staff assignments (from BPUH Excel)
    assigned_analyst_id = db.Column(db.Integer, db.ForeignKey("users.id"))  # Зээлийн шинжээч
    assigned_hm_id = db.Column(db.Integer, db.ForeignKey("users.id"))       # Харилцааны менежер

    # 🆕 GROUP B — Tracking dates and theoretical balance
    theoretical_balance = db.Column(db.Numeric(18, 2))      # Онолын үлдэгдэл
    last_payment_date = db.Column(db.Date)                  # Сүүлийн төлөлтийн огноо
    review_date = db.Column(db.Date)                        # Эргэн хянах өдөр
    gb_notes = db.Column(db.Text)                           # ГБ тайлбар

    # 🆕 GROUP C — Overdue principal/interest breakdown (very important for BPUH)
    overdue_principal = db.Column(db.Numeric(18, 2))                  # Үндсэн зээл
    overdue_principal_days = db.Column(db.Integer)                    # Зээлийн хоног
    overdue_interest = db.Column(db.Numeric(18, 2))                   # Хүү
    overdue_interest_days = db.Column(db.Integer)                     # Хүүгийн хоног
    overdue_commission_interest = db.Column(db.Numeric(18, 2))        # Ком хүү
    overdue_commission_days = db.Column(db.Integer)                   # Ком хүүний хоног
    overdue_penalty_interest = db.Column(db.Numeric(18, 2))           # Торгуулийн хүү
    overdue_penalty_days = db.Column(db.Integer)                      # Торгуулийн хүүний хоног

    # 🆕 GROUP D — Accrued interest amounts (хуримтлагдсан хүү)
    accrued_principal_interest = db.Column(db.Numeric(18, 2))         # Хур.үнд.хүү
    accrued_commission_interest = db.Column(db.Numeric(18, 2))        # Хур.ком.хүү
    accrued_penalty_interest = db.Column(db.Numeric(18, 2))           # Хур.тор.

    # 🆕 GROUP E — Off-balance account (Балансын гадуурх данс)
    off_balance_account_number = db.Column(db.String(50))             # Балансын гадуурх данс
    off_balance_principal_interest = db.Column(db.Numeric(18, 2))     # Б/Г Хур.үнд.хүү
    off_balance_commission_interest = db.Column(db.Numeric(18, 2))    # Б/Г Хур.ком.хүү
    off_balance_penalty_interest = db.Column(db.Numeric(18, 2))       # Б/Г Хур.тор.хүү

    # 🆕 GROUP F — Model calculation (their internal scoring)
    model_calculation_date = db.Column(db.Date)                       # Модель тооцоолол огноо
    model_calculation_value = db.Column(db.Numeric(10, 2))            # Модель тооцоолол

    # Import tracking
    source_system = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    borrower = db.relationship("Borrower", back_populates="loans")
    loan_product = db.relationship("LoanProduct", back_populates="loans")
    branch = db.relationship("Branch", back_populates="loans")
    assigned_user = db.relationship("User", foreign_keys=[assigned_to])
    assigned_zm = db.relationship("User", foreign_keys=[assigned_zm_id])
    assigned_zkha = db.relationship("User", foreign_keys=[assigned_zkha_id])
    assigned_analyst = db.relationship("User", foreign_keys=[assigned_analyst_id])   # 🆕
    assigned_hm = db.relationship("User", foreign_keys=[assigned_hm_id])             # 🆕

    related_parties = db.relationship("RelatedParty", back_populates="loan", lazy="dynamic")
    collaterals = db.relationship("Collateral", back_populates="loan", lazy="dynamic")
    delinquency_history = db.relationship("DelinquencyHistory", back_populates="loan", lazy="dynamic")
    contact_logs = db.relationship("ContactLog", back_populates="loan", lazy="dynamic")
    actions = db.relationship("ActionTaken", back_populates="loan", lazy="dynamic")
    committee_reviews = db.relationship("CommitteeReview", back_populates="loan", lazy="dynamic")
    classification_history = db.relationship("ClassificationHistory", back_populates="loan", lazy="dynamic")
    notifications = db.relationship("Notification", back_populates="loan", lazy="dynamic")
    documents = db.relationship("Document", back_populates="loan", lazy="dynamic")
    insurance_cases = db.relationship("InsuranceCase", back_populates="loan", lazy="dynamic")
    restructures = db.relationship("Restructure", back_populates="loan", lazy="dynamic")
    transfers = db.relationship("CaseTransfer", back_populates="loan", lazy="dynamic")
    outsourcing_assignments = db.relationship("OutsourcingAssignment", back_populates="loan", lazy="dynamic")

    __table_args__ = (
        db.Index("ix_loans_borrower", "borrower_id"),
        db.Index("ix_loans_delinquency", "delinquency_days"),
        db.Index("ix_loans_status", "status"),
        db.Index("ix_loans_classification", "classification"),
        db.Index("ix_loans_branch", "branch_id"),
        db.Index("ix_loans_assigned", "assigned_to"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "borrower_id": self.borrower_id,
            "loan_number": self.loan_account_number,
            "loan_account_number": self.loan_account_number,
            "contract_number": self.contract_number,
            "product_type": self.loan_product.name if self.loan_product else None,
            "loan_product_id": self.loan_product_id,
            "amount": _to_float(self.amount_original),
            "amount_original": _to_float(self.amount_original),
            "balance": _to_float(self.amount_outstanding),
            "amount_outstanding": _to_float(self.amount_outstanding),
            "amount_overdue": _to_float(self.amount_overdue),
            "overdue_amount": _to_float(self.amount_overdue),
            "currency": self.currency,
            "interest_rate": _to_float(self.interest_rate),
            "term_months": self.term_months,
            "disbursement_date": _date_to_str(self.disbursement_date),
            "maturity_date": _date_to_str(self.maturity_date),
            "status": _enum_to_str(self.status),
            "classification": _enum_to_str(self.classification),
            "days_overdue": self.delinquency_days,
            "delinquency_days": self.delinquency_days,
            "delinquency_start_date": _date_to_str(self.delinquency_start_date),
            "current_escalation_stage": self.current_escalation_stage,
            "priority": self.priority,
            "is_insurance_eligible": self.is_insurance_eligible,
            "is_transferred_to_taug": self.is_transferred_to_taug,
            "restructure_count": self.restructure_count,
            "has_zbds_guarantee": self.has_zbds_guarantee,
            "branch": self.branch.name if self.branch else None,
            "branch_id": self.branch_id,
            "assigned_to": self.assigned_to,
            "assigned_zm_id": self.assigned_zm_id,
            "assigned_zkha_id": self.assigned_zkha_id,

            # 🆕 New staff assignments
            "assigned_analyst_id": self.assigned_analyst_id,
            "assigned_analyst_name": self.assigned_analyst.name if self.assigned_analyst else None,
            "assigned_hm_id": self.assigned_hm_id,
            "assigned_hm_name": self.assigned_hm.name if self.assigned_hm else None,

            # 🆕 Tracking dates/balances
            "theoretical_balance": _to_float(self.theoretical_balance),
            "last_payment_date": _date_to_str(self.last_payment_date),
            "review_date": _date_to_str(self.review_date),
            "gb_notes": self.gb_notes,

            # 🆕 Overdue breakdown
            "overdue_principal": _to_float(self.overdue_principal),
            "overdue_principal_days": self.overdue_principal_days,
            "overdue_interest": _to_float(self.overdue_interest),
            "overdue_interest_days": self.overdue_interest_days,
            "overdue_commission_interest": _to_float(self.overdue_commission_interest),
            "overdue_commission_days": self.overdue_commission_days,
            "overdue_penalty_interest": _to_float(self.overdue_penalty_interest),
            "overdue_penalty_days": self.overdue_penalty_days,

            # 🆕 Accrued interest
            "accrued_principal_interest": _to_float(self.accrued_principal_interest),
            "accrued_commission_interest": _to_float(self.accrued_commission_interest),
            "accrued_penalty_interest": _to_float(self.accrued_penalty_interest),

            # 🆕 Off-balance account
            "off_balance_account_number": self.off_balance_account_number,
            "off_balance_principal_interest": _to_float(self.off_balance_principal_interest),
            "off_balance_commission_interest": _to_float(self.off_balance_commission_interest),
            "off_balance_penalty_interest": _to_float(self.off_balance_penalty_interest),

            # 🆕 Model calculation
            "model_calculation_date": _date_to_str(self.model_calculation_date),
            "model_calculation_value": _to_float(self.model_calculation_value),

            "source_system": self.source_system,
            "created_at": _date_to_str(self.created_at),
            "updated_at": _date_to_str(self.updated_at),
        }

    def __repr__(self):
        return f"<Loan {self.loan_account_number} days={self.delinquency_days} status={self.status.value}>"


# ============================================================================
# MODEL — Collateral (UPDATED: 2 new fields)
# ============================================================================

class Collateral(db.Model):
    """
    Барьцаа хөрөнгө — Collateral assets tied to a loan.
    UPDATED: Added coverage_percent and is_unregistered for BPUH Excel coverage.
    """
    __tablename__ = "collaterals"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    borrower_id = db.Column(db.Integer, db.ForeignKey("borrowers.id"), nullable=False)

    collateral_type = db.Column(db.Enum(CollateralType), nullable=False)
    description = db.Column(db.Text)

    valuation_amount = db.Column(db.Numeric(18, 2))
    valuation_date = db.Column(db.Date)
    valuator = db.Column(db.String(150))
    needs_revaluation = db.Column(db.Boolean, default=False)

    # 🆕 NEW fields for BPUH coverage
    coverage_percent = db.Column(db.Numeric(5, 2))     # Барьцаа хөрөнгийн зээл нөхөлтийн хувь
    is_unregistered = db.Column(db.Boolean, default=False)  # Бүртгэгдээгүй хөрөнгө

    mpr_registration = db.Column(db.String(50))
    mpr_expiry_date = db.Column(db.Date)

    insurance_status = db.Column(db.String(50))
    insurance_expiry_date = db.Column(db.Date)

    archive_location = db.Column(db.String(50))
    original_docs_status = db.Column(db.String(50))

    status = db.Column(db.Enum(CollateralStatus), default=CollateralStatus.ACTIVE, nullable=False)
    last_inspection_date = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    loan = db.relationship("Loan", back_populates="collaterals")
    borrower = db.relationship("Borrower")

    __table_args__ = (db.Index("ix_collaterals_loan", "loan_id"),)

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "borrower_id": self.borrower_id,
            "collateral_type": _enum_to_str(self.collateral_type),
            "description": self.description,
            "valuation_amount": _to_float(self.valuation_amount),
            "valuation_date": _date_to_str(self.valuation_date),
            "status": _enum_to_str(self.status),
            "needs_revaluation": self.needs_revaluation,
            "coverage_percent": _to_float(self.coverage_percent),  # 🆕
            "is_unregistered": self.is_unregistered,                 # 🆕
            "last_inspection_date": _date_to_str(self.last_inspection_date),
            "archive_location": self.archive_location,
        }

    def __repr__(self):
        return f"<Collateral {self.collateral_type.value} loan={self.loan_id}>"


# ============================================================================
# NEW MODEL — DepositAccount
# ============================================================================

class DepositAccount(db.Model):
    """
    🆕 Депозит данс — Deposit/payment accounts owned by borrowers.

    Used by BPUH to check if borrower has money in their accounts that
    could be applied to the overdue loan. One borrower can have multiple accounts.

    Source: BPUH Excel reports — Төлбөр төлөх данс, Депозит данс
    """
    __tablename__ = "deposit_accounts"

    id = db.Column(db.Integer, primary_key=True)
    borrower_id = db.Column(db.Integer, db.ForeignKey("borrowers.id"), nullable=False, index=True)

    account_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    account_type = db.Column(db.Enum(DepositAccountType), default=DepositAccountType.PAYMENT, nullable=False)

    balance = db.Column(db.Numeric(18, 2), default=0)              # Дансны үлдэгдэл
    currency = db.Column(db.String(3), default="MNT")

    is_frozen = db.Column(db.Boolean, default=False)               # Битүүмж эсэх
    is_primary_payment = db.Column(db.Boolean, default=False)      # Анхдагч төлбөр төлөх данс эсэх

    opened_date = db.Column(db.Date)
    last_activity_date = db.Column(db.Date)

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    borrower = db.relationship("Borrower", back_populates="deposit_accounts")

    __table_args__ = (
        db.Index("ix_deposit_borrower", "borrower_id"),
        db.Index("ix_deposit_primary", "is_primary_payment"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "borrower_id": self.borrower_id,
            "account_number": self.account_number,
            "account_type": _enum_to_str(self.account_type),
            "balance": _to_float(self.balance),
            "currency": self.currency,
            "is_frozen": self.is_frozen,
            "is_primary_payment": self.is_primary_payment,
            "opened_date": _date_to_str(self.opened_date),
            "last_activity_date": _date_to_str(self.last_activity_date),
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<DepositAccount {self.account_number} balance={self.balance}>"



# ============================================================================
# MODEL — DelinquencyHistory (unchanged)
# ============================================================================

class DelinquencyHistory(db.Model):
    """
    Зөрчлийн түүх — Daily snapshots of every loan's delinquency state.
    Solves the #1 pain point from File 1 Row 3: data was never preserved.
    """
    __tablename__ = "delinquency_history"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False)

    delinquency_days = db.Column(db.Integer, nullable=False)
    amount_overdue = db.Column(db.Numeric(18, 2))
    amount_outstanding = db.Column(db.Numeric(18, 2))
    escalation_stage = db.Column(db.Integer)
    classification = db.Column(db.Enum(ClassificationLevel))

    was_contacted = db.Column(db.Boolean, default=False)
    contact_attempts = db.Column(db.Integer, default=0)

    source_report = db.Column(db.String(100))
    imported_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    loan = db.relationship("Loan", back_populates="delinquency_history")

    __table_args__ = (
        db.Index("ix_dh_loan_date", "loan_id", "snapshot_date"),
        db.Index("ix_dh_snapshot_date", "snapshot_date"),
        db.Index("ix_dh_delinquency_days", "delinquency_days"),
        db.UniqueConstraint("loan_id", "snapshot_date", name="uq_loan_snapshot"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "snapshot_date": _date_to_str(self.snapshot_date),
            "delinquency_days": self.delinquency_days,
            "amount_overdue": _to_float(self.amount_overdue),
            "amount_outstanding": _to_float(self.amount_outstanding),
            "escalation_stage": self.escalation_stage,
            "classification": _enum_to_str(self.classification),
            "was_contacted": self.was_contacted,
            "contact_attempts": self.contact_attempts,
        }

    def __repr__(self):
        return f"<DelinquencyHistory loan={self.loan_id} date={self.snapshot_date} days={self.delinquency_days}>"


# ============================================================================
# MODEL — ContactLog (unchanged)
# ============================================================================

class ContactLog(db.Model):
    """Холбогдсон бүртгэл — Every call, SMS, email, visit"""
    __tablename__ = "contact_logs"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    borrower_id = db.Column(db.Integer, db.ForeignKey("borrowers.id"), nullable=False)
    related_party_id = db.Column(db.Integer, db.ForeignKey("related_parties.id"))

    contact_type = db.Column(db.Enum(ContactType), nullable=False)
    contact_direction = db.Column(db.Enum(ContactDirection), default=ContactDirection.OUTBOUND)
    phone_number_used = db.Column(db.String(20))
    was_reached = db.Column(db.Boolean)
    attempt_number = db.Column(db.Integer)
    reason_not_reached = db.Column(db.String(200))

    delinquency_reason = db.Column(db.Text)
    promised_payment_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    visit_address = db.Column(db.String(500))
    visit_borrower_present = db.Column(db.Boolean)

    contacted_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    contact_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    loan = db.relationship("Loan", back_populates="contact_logs")
    borrower = db.relationship("Borrower", back_populates="contact_logs")
    related_party = db.relationship("RelatedParty", back_populates="contact_logs")
    contacted_by_user = db.relationship("User", foreign_keys=[contacted_by])

    __table_args__ = (
        db.Index("ix_cl_loan", "loan_id"),
        db.Index("ix_cl_borrower", "borrower_id"),
        db.Index("ix_cl_contact_date", "contact_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "borrower_id": self.borrower_id,
            "related_party_id": self.related_party_id,
            "contact_type": _enum_to_str(self.contact_type),
            "action_type": _enum_to_str(self.contact_type),  # backward compat
            "contact_direction": _enum_to_str(self.contact_direction),
            "phone_number_used": self.phone_number_used,
            "was_reached": self.was_reached,
            "attempt_number": self.attempt_number,
            "reason_not_reached": self.reason_not_reached,
            "outcome": "reached" if self.was_reached else "no_answer",
            "delinquency_reason": self.delinquency_reason,
            "promised_payment_date": _date_to_str(self.promised_payment_date),
            "notes": self.notes,
            "visit_address": self.visit_address,
            "visit_borrower_present": self.visit_borrower_present,
            "contacted_by": self.contacted_by,
            "contact_date": _date_to_str(self.contact_date),
            "created_at": _date_to_str(self.created_at),
        }

    def __repr__(self):
        return f"<ContactLog loan={self.loan_id} type={self.contact_type.value}>"


# ============================================================================
# MODEL — EscalationRule (unchanged)
# ============================================================================

class EscalationRule(db.Model):
    """Процессын дүрэм — File 1's 15-step escalation ladder"""
    __tablename__ = "escalation_rules"

    id = db.Column(db.Integer, primary_key=True)
    step_number = db.Column(db.Integer, nullable=False)
    product_scope = db.Column(db.String(200), nullable=False)
    action_category = db.Column(db.String(100))

    day_range_start = db.Column(db.Integer, nullable=False)
    day_range_end = db.Column(db.Integer, nullable=False)

    regulation_name = db.Column(db.String(200))
    regulation_clause = db.Column(db.String(30))

    instruction_text = db.Column(db.Text)
    required_action = db.Column(db.Text)

    avg_time_per_loan_min = db.Column(db.Numeric(8, 2))
    total_daily_time_min = db.Column(db.Numeric(10, 2))

    frequency = db.Column(db.Enum(EscalationFrequency))
    systems_used = db.Column(db.Text)
    responsible_role = db.Column(db.String(100))

    auto_sms = db.Column(db.Boolean, default=False)
    auto_email = db.Column(db.Boolean, default=False)
    requires_visit = db.Column(db.Boolean, default=False)
    requires_committee = db.Column(db.Boolean, default=False)
    requires_taug_transfer = db.Column(db.Boolean, default=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    actions = db.relationship("ActionTaken", back_populates="escalation_rule", lazy="dynamic")

    __table_args__ = (db.Index("ix_er_day_range", "day_range_start", "day_range_end"),)

    def to_dict(self):
        return {
            "id": self.id,
            "step_number": self.step_number,
            "product_scope": self.product_scope,
            "day_range_start": self.day_range_start,
            "day_range_end": self.day_range_end,
            "regulation_clause": self.regulation_clause,
            "required_action": self.required_action,
            "frequency": _enum_to_str(self.frequency),
            "responsible_role": self.responsible_role,
            "auto_sms": self.auto_sms,
            "auto_email": self.auto_email,
            "requires_visit": self.requires_visit,
            "requires_committee": self.requires_committee,
            "requires_taug_transfer": self.requires_taug_transfer,
        }

    def __repr__(self):
        return f"<EscalationRule step={self.step_number} days={self.day_range_start}-{self.day_range_end}>"


# ============================================================================
# MODEL — ActionTaken (unchanged)
# ============================================================================

class ActionTaken(db.Model):
    """Авсан арга хэмжээ — Every formal action taken on a loan"""
    __tablename__ = "actions_taken"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    escalation_rule_id = db.Column(db.Integer, db.ForeignKey("escalation_rules.id"))

    action_type = db.Column(db.Enum(ActionType), nullable=False)
    action_description = db.Column(db.Text)
    action_result = db.Column(db.Text)

    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"))

    performed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    performed_at = db.Column(db.DateTime, nullable=False)
    due_date = db.Column(db.DateTime)
    is_overdue = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    loan = db.relationship("Loan", back_populates="actions")
    escalation_rule = db.relationship("EscalationRule", back_populates="actions")
    document = db.relationship("Document", foreign_keys=[document_id])
    performed_by_user = db.relationship("User", foreign_keys=[performed_by])
    approved_by_user = db.relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        db.Index("ix_at_loan", "loan_id"),
        db.Index("ix_at_type", "action_type"),
        db.Index("ix_at_performed", "performed_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "action_type": _enum_to_str(self.action_type),
            "action_description": self.action_description,
            "action_result": self.action_result,
            "performed_by": self.performed_by,
            "approved_by": self.approved_by,
            "performed_at": _date_to_str(self.performed_at),
            "due_date": _date_to_str(self.due_date),
            "is_overdue": self.is_overdue,
            "created_at": _date_to_str(self.created_at),
        }

    def __repr__(self):
        return f"<ActionTaken loan={self.loan_id} type={self.action_type.value}>"


# ============================================================================
# MODEL — CommitteeReview (unchanged)
# ============================================================================

class CommitteeReview(db.Model):
    """Хорооны хэлэлцүүлэг — Committee discussions from File 2"""
    __tablename__ = "committee_reviews"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)

    committee_type = db.Column(db.Enum(CommitteeType), nullable=False)
    meeting_date = db.Column(db.Date)
    classification_scope = db.Column(db.String(100))

    current_classification = db.Column(db.Enum(ClassificationLevel))
    proposed_classification = db.Column(db.Enum(ClassificationLevel))
    risk_provision_amount = db.Column(db.Numeric(18, 2))

    explanation_notes = db.Column(db.Text)

    decision = db.Column(db.Enum(CommitteeDecisionType))
    decision_number = db.Column(db.String(50))
    decision_text = db.Column(db.Text)
    next_action = db.Column(db.String(200))
    deadline = db.Column(db.Date)

    prepared_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    consolidated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    status = db.Column(db.Enum(ReviewStatus), default=ReviewStatus.PREPARING, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    loan = db.relationship("Loan", back_populates="committee_reviews")
    prepared_by_user = db.relationship("User", foreign_keys=[prepared_by])
    consolidated_by_user = db.relationship("User", foreign_keys=[consolidated_by])
    approved_by_user = db.relationship("User", foreign_keys=[approved_by])
    classification_changes = db.relationship("ClassificationHistory", back_populates="committee_review", lazy="dynamic")

    __table_args__ = (
        db.Index("ix_cr_loan", "loan_id"),
        db.Index("ix_cr_meeting", "meeting_date"),
        db.Index("ix_cr_status", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "case_id": self.loan_id,
            "committee_type": _enum_to_str(self.committee_type),
            "meeting_date": _date_to_str(self.meeting_date),
            "decision_date": _date_to_str(self.meeting_date),
            "current_classification": _enum_to_str(self.current_classification),
            "proposed_classification": _enum_to_str(self.proposed_classification),
            "explanation_notes": self.explanation_notes,
            "decision": _enum_to_str(self.decision),
            "decision_text": self.decision_text,
            "next_action": self.next_action,
            "deadline": _date_to_str(self.deadline),
            "status": _enum_to_str(self.status),
            "prepared_by": self.prepared_by,
            "approved_by": self.approved_by,
            "created_at": _date_to_str(self.created_at),
        }

    def __repr__(self):
        return f"<CommitteeReview loan={self.loan_id} type={self.committee_type.value}>"


# ============================================================================
# MODEL — ClassificationHistory (unchanged)
# ============================================================================

class ClassificationHistory(db.Model):
    """Ангиллын түүх — Every classification change"""
    __tablename__ = "classification_history"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    committee_review_id = db.Column(db.Integer, db.ForeignKey("committee_reviews.id"))

    previous_classification = db.Column(db.Enum(ClassificationLevel), nullable=False)
    new_classification = db.Column(db.Enum(ClassificationLevel), nullable=False)
    classification_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)

    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    loan = db.relationship("Loan", back_populates="classification_history")
    committee_review = db.relationship("CommitteeReview", back_populates="classification_changes")
    approved_by_user = db.relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        db.Index("ix_ch_loan", "loan_id"),
        db.Index("ix_ch_date", "classification_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "previous_classification": _enum_to_str(self.previous_classification),
            "new_classification": _enum_to_str(self.new_classification),
            "classification_date": _date_to_str(self.classification_date),
            "reason": self.reason,
            "approved_by": self.approved_by,
        }

    def __repr__(self):
        return f"<ClassificationHistory loan={self.loan_id}>"



# ============================================================================
# MODEL — Notification (unchanged)
# ============================================================================

class Notification(db.Model):
    """Мэдэгдэл — Auto-generated alerts"""
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"))

    notification_type = db.Column(db.Enum(NotificationType), nullable=False)
    recipient_branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    channel = db.Column(db.Enum(NotificationChannel), nullable=False)

    subject = db.Column(db.String(300))
    message_content = db.Column(db.Text)

    is_auto = db.Column(db.Boolean, default=True)
    status = db.Column(db.Enum(NotificationStatus), default=NotificationStatus.PENDING, nullable=False)
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    loan = db.relationship("Loan", back_populates="notifications")
    recipient_branch = db.relationship("Branch", back_populates="notifications")
    recipient_user = db.relationship("User", foreign_keys=[recipient_user_id])

    __table_args__ = (
        db.Index("ix_notif_loan", "loan_id"),
        db.Index("ix_notif_status", "status"),
        db.Index("ix_notif_recipient_user", "recipient_user_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "notification_type": _enum_to_str(self.notification_type),
            "channel": _enum_to_str(self.channel),
            "subject": self.subject,
            "message_content": self.message_content,
            "is_auto": self.is_auto,
            "status": _enum_to_str(self.status),
            "sent_at": _date_to_str(self.sent_at),
            "read_at": _date_to_str(self.read_at),
        }

    def __repr__(self):
        return f"<Notification type={self.notification_type.value} status={self.status.value}>"


# ============================================================================
# MODEL — Document (unchanged)
# ============================================================================

class Document(db.Model):
    """Баримт бичиг — Generated documents"""
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)

    document_type = db.Column(db.Enum(DocumentType), nullable=False)
    title = db.Column(db.String(300))
    file_path = db.Column(db.String(500))
    dms_reference = db.Column(db.String(100))

    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    signed_by_borrower = db.Column(db.Boolean, default=False)

    status = db.Column(db.Enum(DocumentStatus), default=DocumentStatus.DRAFT, nullable=False)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    loan = db.relationship("Loan", back_populates="documents")
    generated_by_user = db.relationship("User", foreign_keys=[generated_by])
    approved_by_user = db.relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        db.Index("ix_doc_loan", "loan_id"),
        db.Index("ix_doc_type", "document_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "document_type": _enum_to_str(self.document_type),
            "title": self.title,
            "file_path": self.file_path,
            "dms_reference": self.dms_reference,
            "signed_by_borrower": self.signed_by_borrower,
            "status": _enum_to_str(self.status),
            "created_at": _date_to_str(self.created_at),
        }

    def __repr__(self):
        return f"<Document {self.document_type.value} loan={self.loan_id}>"


# ============================================================================
# MODEL — InsuranceCase (unchanged)
# ============================================================================

class InsuranceCase(db.Model):
    """Даатгалын тохиолдол"""
    __tablename__ = "insurance_cases"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)

    registration_date = db.Column(db.Date)
    deadline_40_days = db.Column(db.Date)
    deadline_90_days = db.Column(db.Date)
    materials_sent_date = db.Column(db.Date)

    insurance_decision = db.Column(db.Enum(InsuranceDecision), default=InsuranceDecision.PENDING)
    payout_amount = db.Column(db.Numeric(18, 2))
    status = db.Column(db.String(50))

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    loan = db.relationship("Loan", back_populates="insurance_cases")

    __table_args__ = (db.Index("ix_ins_loan", "loan_id"),)

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "registration_date": _date_to_str(self.registration_date),
            "deadline_40_days": _date_to_str(self.deadline_40_days),
            "deadline_90_days": _date_to_str(self.deadline_90_days),
            "materials_sent_date": _date_to_str(self.materials_sent_date),
            "insurance_decision": _enum_to_str(self.insurance_decision),
            "payout_amount": _to_float(self.payout_amount),
            "status": self.status,
        }

    def __repr__(self):
        return f"<InsuranceCase loan={self.loan_id}>"


# ============================================================================
# MODEL — Restructure (unchanged) - MAX 2 PER LOAN
# ============================================================================

class Restructure(db.Model):
    """Бүтцийн өөрчлөлт - Maximum 2 per loan (File 1 Row 28)"""
    __tablename__ = "restructures"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)

    restructure_number = db.Column(db.Integer, nullable=False)
    proposal_date = db.Column(db.Date, nullable=False)
    committee_review_id = db.Column(db.Integer, db.ForeignKey("committee_reviews.id"))

    old_terms = db.Column(db.Text)
    new_terms = db.Column(db.Text)

    decision = db.Column(db.Enum(RestructureDecision))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    effective_date = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    loan = db.relationship("Loan", back_populates="restructures")
    committee_review = db.relationship("CommitteeReview")
    approved_by_user = db.relationship("User", foreign_keys=[approved_by])

    __table_args__ = (db.Index("ix_restr_loan", "loan_id"),)

    def to_dict(self):
        return {
            "id": self.id,
            "loan_id": self.loan_id,
            "restructure_number": self.restructure_number,
            "proposal_date": _date_to_str(self.proposal_date),
            "old_terms": self.old_terms,
            "new_terms": self.new_terms,
            "decision": _enum_to_str(self.decision),
            "effective_date": _date_to_str(self.effective_date),
        }

    def __repr__(self):
        return f"<Restructure #{self.restructure_number} loan={self.loan_id}>"


# ============================================================================
# MODEL — CaseTransfer (unchanged)
# ============================================================================

class CaseTransfer(db.Model):
    """Хэрэг шилжүүлэг"""
    __tablename__ = "case_transfers"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    to_entity = db.Column(db.String(50), nullable=False)
    transfer_date = db.Column(db.DateTime, default=_utcnow)
    reason = db.Column(db.Text)
    materials_attached = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum(TransferStatus), default=TransferStatus.PENDING)

    loan = db.relationship("Loan", back_populates="transfers")
    from_user = db.relationship("User", foreign_keys=[from_user_id])

    __table_args__ = (db.Index("ix_ct_loan", "loan_id"),)

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.loan_id,
            "loan_id": self.loan_id,
            "from_user_id": self.from_user_id,
            "to_entity": self.to_entity,
            "transfer_date": _date_to_str(self.transfer_date),
            "reason": self.reason,
            "materials_attached": self.materials_attached,
            "status": _enum_to_str(self.status),
        }

    def __repr__(self):
        return f"<CaseTransfer loan={self.loan_id} -> {self.to_entity}>"


# ============================================================================
# MODEL — OutsourcingAssignment (unchanged)
# ============================================================================

class OutsourcingAssignment(db.Model):
    """Аутсорсинг"""
    __tablename__ = "outsourcing_assignments"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    assigned_date = db.Column(db.Date, default=date.today)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    commission_rate = db.Column(db.Float, default=0.10)
    collected_amount = db.Column(db.Float, default=0)
    expected_amount = db.Column(db.Float)
    status = db.Column(db.Enum(OutsourcingStatus), default=OutsourcingStatus.ACTIVE)
    resolution_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    loan = db.relationship("Loan", back_populates="outsourcing_assignments")
    assigned_by_user = db.relationship("User", foreign_keys=[assigned_by])

    __table_args__ = (
        db.Index("ix_oa_loan", "loan_id"),
        db.Index("ix_oa_status", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.loan_id,
            "loan_id": self.loan_id,
            "company_name": self.company_name,
            "assigned_date": _date_to_str(self.assigned_date),
            "commission_rate": self.commission_rate,
            "collected_amount": self.collected_amount,
            "expected_amount": self.expected_amount,
            "status": _enum_to_str(self.status),
            "resolution_date": _date_to_str(self.resolution_date),
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<OutsourcingAssignment loan={self.loan_id} -> {self.company_name}>"


# ============================================================================
# MODEL — AuditLog (unchanged)
# ============================================================================

class AuditLog(db.Model):
    """Аудитын бүртгэл"""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(20), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=_utcnow, nullable=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.Index("ix_audit_user", "user_id"),
        db.Index("ix_audit_entity", "entity_type", "entity_id"),
        db.Index("ix_audit_timestamp", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "ip_address": self.ip_address,
            "timestamp": _date_to_str(self.timestamp),
        }

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity_type}#{self.entity_id}>"


# ============================================================================
# TABLE SUMMARY - 26 Models Total (1 NEW: deposit_accounts)
# ============================================================================
#
# ORGANISATIONAL (6 tables):
#   1. segments
#   2. regions
#   3. branches
#   4. roles
#   5. users
#   6. permissions
#
# REFERENCE (2 tables):
#   7. loan_products
#   8. source_systems
#
# CORE ENTITIES (5 tables):
#   9. borrowers          (UPDATED: +3 fields: workplace_name, phone_home, phone_work)
#  10. related_parties
#  11. loans              (UPDATED: +22 fields: interest breakdown, off-balance,
#                          tracking dates, model calc, analyst/HM assignments)
#  12. collaterals        (UPDATED: +2 fields: coverage_percent, is_unregistered)
#  13. deposit_accounts   (NEW)  - payment/savings accounts per borrower
#
# DELINQUENCY TRACKING (3 tables):
#  14. delinquency_history
#  15. contact_logs
#  16. escalation_rules
#
# ACTIONS (1 table):
#  17. actions_taken
#
# GOVERNANCE (2 tables):
#  18. committee_reviews
#  19. classification_history
#
# SUPPORTING (6 tables):
#  20. notifications
#  21. documents
#  22. insurance_cases
#  23. restructures
#  24. case_transfers
#  25. outsourcing_assignments
#
# AUDIT (1 table):
#  26. audit_log
#
# COVERAGE:
#   Excel #1 (BPUH daily v1, 72 cols): 97% covered
#   Excel #2 (BPUH daily v2, 46 cols): 100% covered
#
# ============================================================================
