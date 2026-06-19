"""
=============================================================================
Collection System — Database Seeder (UPDATED for new fields)
=============================================================================
Populates the database with realistic test data including all 34 new fields
from BPUH Excel reports + the new DepositAccount table.

CHANGES IN THIS VERSION:
  - Borrower: workplace_name, phone_home, phone_work
  - Loan: 22 new fields (interest breakdown, off-balance, model calc, etc.)
  - Collateral: coverage_percent, is_unregistered
  - NEW: DepositAccount table — 3-5 accounts per borrower
  - Sequential counters to prevent duplicate key collisions

Usage:
  cd C:\\Users\\bers.b\\Projects.Bers\\collection-system
  python -m app.seed
=============================================================================
"""

import random
import sys
import os
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import db
from app.models import (
    Segment, Region, Branch, Role, User, Permission,
    LoanProduct, SourceSystem, Borrower, RelatedParty, Loan, Collateral,
    DepositAccount,                                                 # NEW
    DelinquencyHistory, ContactLog, EscalationRule, ActionTaken,
    CommitteeReview, ClassificationHistory, Notification, Document,
    InsuranceCase, Restructure, CaseTransfer, OutsourcingAssignment, AuditLog,
    SegmentType, PartyType, ContactType, ContactDirection, ActionType,
    CommitteeType, CommitteeDecisionType, ReviewStatus, ClassificationLevel,
    LoanStatus, CollateralType, CollateralStatus, DocumentType, DocumentStatus,
    NotificationType, NotificationChannel, NotificationStatus, PermissionType,
    InsuranceDecision, RestructureDecision, EscalationFrequency,
    TransferStatus, OutsourcingStatus,
    DepositAccountType,                                            # NEW
)


# ============================================================================
# COUNTERS & HELPERS
# ============================================================================

_loan_counter = 0
_cif_counter = 0
_account_counter = 0   # NEW for deposit accounts


def _utcnow():
    return datetime.now(timezone.utc)


def _random_date(start_year=2020, end_year=2025):
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _random_phone():
    return f"99{random.randint(100000, 999999)}"


def _random_register():
    letters = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ"
    letter1 = random.choice(letters)
    letter2 = random.choice(letters)
    num = random.randint(10000000, 99999999)
    return f"{letter1}{letter2}{num}"


def _random_cif():
    global _cif_counter
    _cif_counter += 1
    return f"CIF{_cif_counter:06d}"


def _random_loan_number():
    global _loan_counter
    _loan_counter += 1
    return f"LN{_loan_counter:07d}"


def _random_deposit_account_number():
    global _account_counter
    _account_counter += 1
    return f"DA{_account_counter:08d}"


def _random_contract():
    return f"GR-{random.randint(2020, 2025)}-{random.randint(10000, 99999)}"


def _random_off_balance_account():
    return f"OB{random.randint(10000000, 99999999)}"


# ============================================================================
# REFERENCE DATA SEEDERS (mostly unchanged)
# ============================================================================

def seed_segments():
    """Create Retail and SMB segments."""
    segments = [
        Segment(name="Иргэдийн банкны газар (ИБГ)", segment_type=SegmentType.RETAIL, department_code="ИБГ"),
        Segment(name="Жижиг дунд бизнесийн банкны газар (ЖДББГ)", segment_type=SegmentType.SMB, department_code="ЖДББГ"),
    ]
    db.session.add_all(segments)
    db.session.flush()
    print(f"  ✅ {len(segments)} segments")
    return {s.segment_type: s for s in segments}


def seed_regions(segments):
    """Create 5 regional groupings."""
    regions_data = [
        ("Төв бүс", SegmentType.RETAIL),
        ("Зүүн бүс", SegmentType.RETAIL),
        ("Баруун бүс", SegmentType.RETAIL),
        ("Хангай бүс", SegmentType.SMB),
        ("Говь бүс", SegmentType.SMB),
    ]
    regions = []
    for name, seg_type in regions_data:
        r = Region(name=name, segment_id=segments[seg_type].id)
        regions.append(r)
    db.session.add_all(regions)
    db.session.flush()
    print(f"  ✅ {len(regions)} regions")
    return regions


def seed_branches(regions):
    """Create 15 branches across regions."""
    branch_data = [
        ("Баянзүрх салбар", "BZR", 0),
        ("Сүхбаатар салбар", "SKB", 0),
        ("Чингэлтэй салбар", "CHG", 0),
        ("Хан-Уул салбар", "KHU", 0),
        ("Баянгол салбар", "BGL", 0),
        ("Сонгинохайрхан салбар", "SKH", 1),
        ("Налайх салбар", "NLK", 1),
        ("Дархан салбар", "DKH", 1),
        ("Эрдэнэт салбар", "ERD", 2),
        ("Дорнод салбар", "DRN", 2),
        ("Ховд салбар", "KHD", 2),
        ("Өвөрхангай салбар", "OKH", 3),
        ("Архангай салбар", "AKH", 3),
        ("Өмнөговь салбар", "OGV", 4),
        ("Дорноговь салбар", "DGV", 4),
    ]
    branches = []
    for name, code, reg_idx in branch_data:
        b = Branch(
            name=name, code=code,
            region_id=regions[reg_idx].id,
            email=f"{code.lower()}@bank.mn",
            phone=_random_phone(),
        )
        branches.append(b)
    db.session.add_all(branches)
    db.session.flush()
    print(f"  ✅ {len(branches)} branches")
    return branches


def seed_roles():
    """Create all 28 roles with dashboard routing."""
    roles_data = [
        ("retail_hm", "Retail харилцааны менежер", "Retail Relationship Manager", "zm"),
        ("smb_hm", "SMB харилцааны менежер", "SMB Relationship Manager", "zm"),
        ("zm_research", "Зээлийн мэргэжилтэн (судалгаа)", "Loan Specialist (Research)", "zm"),
        ("zm_control", "Зээлийн мэргэжилтэн (хяналт)", "Loan Specialist (Control)", "zm"),
        ("senior_specialist", "Ахлах мэргэжилтэн (АМ)", "Senior Specialist", "zm"),
        ("admin_officer", "Админ ажилтан", "Admin Officer", "zm"),
        ("branch_director", "Салбарын захирал", "Branch Director", "zm"),
        ("regional_director", "Бүсийн захирал", "Regional Director", "zm"),
        ("segment_office", "Сегментийн газар", "Segment Office", "jdbbg"),
        ("segment_specialist", "Сегментийн ажилтан", "Segment Specialist", "jdbbg"),
        ("property_valuator", "Хөрөнгийн үнэлгээний шинжээч (ХҮШ)", "Property Valuation Analyst", "senior"),
        ("risk_analyst", "Зээлийн эрсдэлийн шинжээч (ЗЭШ)", "Loan Risk Analyst", "senior"),
        ("aml_analyst", "БОНЭШ", "AML Analyst", "senior"),
        ("senior_analyst", "Ахлах шинжээч", "Senior Analyst", "senior"),
        ("risk_dept_director", "ЗЭГ-ын захирал", "Risk Department Director", "senior"),
        ("lawyer", "Хуульч", "Lawyer", "taug"),
        ("compliance", "Комплайнсын мэргэжилтэн", "Compliance Specialist", "senior"),
        ("committee_secretary", "Хороодын НБД", "Committee Secretary", "committee"),
        ("cust_service", "Харилцагчийн үйлчилгээний ажилтан (ХҮА)", "Customer Service Officer", "zm"),
        ("senior_cust_service", "Ахлах ХҮА", "Senior Customer Service", "zm"),
        ("finance_control", "Санхүүгийн бүртгэл, хяналтын ажилтан (СБХА)", "Finance Control Officer", "senior"),
        ("loan_admin", "ЗХБХ-ийн мэргэжилтэн", "Loan Admin Specialist", "zm"),
        ("senior_loan_admin", "ЗХБХ-ахлах мэргэжилтэн", "Senior Loan Admin", "zm"),
        ("process_control", "БПҮХ-ийн хяналтын мэргэжилтэн", "Process Control Specialist", "bpuh"),
        ("taug_specialist", "ТАУГ мэргэжилтэн", "NPL Department Specialist", "taug"),
        ("insurance_specialist", "Даатгалын мэргэжилтэн", "Insurance Specialist", "taug"),
        ("outsourcing_agent", "Аутсорсинг компани", "External Collection Agency", "outsourcing"),
        ("executive", "Удирдлага", "Executive Management", "mgmt"),
    ]
    roles = []
    for code, name_mn, name_en, dash in roles_data:
        r = Role(code=code, name_mn=name_mn, name_en=name_en, dashboard_code=dash)
        roles.append(r)
    db.session.add_all(roles)
    db.session.flush()
    print(f"  ✅ {len(roles)} roles")
    return {r.code: r for r in roles}


def seed_users(roles, branches):
    """Create test users."""
    users_data = [
        ("Б. Батбаяр", "process_control", 0, "batbayar"),
        ("О. Оюунчимэг", "process_control", 1, "oyuunchimeg"),
        ("Г. Ганбат", "zm_control", 0, "ganbat"),
        ("А. Алтанцэцэг", "zm_control", 5, "altantsetseg"),
        ("Б. Болд", "zm_research", 0, "bold"),
        ("С. Сарангэрэл", "retail_hm", 0, "sarangerel"),
        ("Э. Энхбаяр", "smb_hm", 2, "enkhbayar"),
        ("М. Мөнхзул", "senior_specialist", 0, "munkhzul"),
        ("Д. Дэлгэрмаа", "branch_director", 0, "delgermaa"),
        ("Х. Хүрэлбаатар", "regional_director", 0, "khurelbaatar"),
        ("Н. Нарангэрэл", "segment_office", 0, "narangerel"),
        ("Ц. Цолмон", "segment_specialist", 0, "tsolmon"),
        ("Ж. Жаргал", "taug_specialist", 0, "jargal"),
        ("П. Пүрэвдорж", "risk_analyst", 0, "purevdorj"),
        ("Т. Тамир", "senior_analyst", 0, "tamir"),
        ("Р. Ринчин", "risk_dept_director", 0, "rinchin"),
        ("Г. Ганзориг", "lawyer", 0, "ganzorig"),
        ("Г. Галмандах", "committee_secretary", 0, "galmandakh"),
        ("Б. Баярмаа", "outsourcing_agent", None, "bayarmaa_os"),
        ("Ц. Цэцэгмаа", "executive", 0, "tsetsegmaa"),
        ("Н. Нямаа", "process_control", 2, "nyamaa"),
        ("О. Отгонбаяр", "zm_control", 8, "otgonbayar"),
        ("Э. Эрдэнэ", "zm_control", 3, "erdene"),
        ("М. Мягмар", "retail_hm", 4, "myagmar"),
        ("Л. Лхагва", "insurance_specialist", 0, "lkhagva"),
    ]
    users = []
    for name, role_code, branch_idx, username in users_data:
        u = User(
            name=name,
            username=username,
            employee_id=f"EMP{random.randint(1000, 9999)}",
            email=f"{username}@bank.mn",
            role_id=roles[role_code].id,
            branch_id=branches[branch_idx].id if branch_idx is not None else None,
            region_id=branches[branch_idx].region_id if branch_idx is not None else None,
            is_active=True,
        )
        users.append(u)
    db.session.add_all(users)
    db.session.flush()
    print(f"  ✅ {len(users)} users")
    return users


def seed_loan_products(segments):
    """Create 12 loan products."""
    products_data = [
        ("Цалингийн зээл", "Хэрэглээ", SegmentType.RETAIL, False, None),
        ("Тэтгэврийн зээл", "Хэрэглээ", SegmentType.RETAIL, False, None),
        ("Хэрэглээний зээл", "Хэрэглээ", SegmentType.RETAIL, False, None),
        ("Цахим зээл (Shoppy.mn)", "Хэрэглээ", SegmentType.RETAIL, True, 5),
        ("Цахим зээл (Sain)", "Хэрэглээ", SegmentType.RETAIL, True, 5),
        ("Автомашины зээл", "Хэрэглээ", SegmentType.RETAIL, False, None),
        ("Ипотекийн зээл", "Хэрэглээ", SegmentType.RETAIL, False, None),
        ("ХБЗ", "Хэрэглээ", SegmentType.RETAIL, False, None),
        ("Бизнесийн зээл", "Бизнес", SegmentType.SMB, False, None),
        ("Кредит карт", "Карт", SegmentType.RETAIL, False, None),
        ("Зээлийн эрх", "Бизнес", SegmentType.SMB, False, None),
        ("Жижиг дунд бизнесийн зээл", "Бизнес", SegmentType.SMB, False, None),
    ]
    products = []
    for name, cat, seg_type, is_dig, sms_day in products_data:
        p = LoanProduct(
            name=name, category=cat,
            segment_id=segments[seg_type].id,
            is_digital=is_dig, auto_sms_day=sms_day,
        )
        products.append(p)
    db.session.add_all(products)
    db.session.flush()
    print(f"  ✅ {len(products)} loan products")
    return products


def seed_source_systems():
    """Create 12 source systems."""
    systems_data = [
        ("grapebank_delinquency", "GrapeBank: Өр үүссэн зээлийн мэдээ - Шинэ"),
        ("grapebank_repayment", "Грэйпбанк: Эргэн төлөлтийн мэдээ"),
        ("grapebank_progress", "Грэйпбанк: Явцын тайлан"),
        ("allweb_delinquency", "Allweb-GB: Өр үүссэн зээлийн мэдээ"),
        ("allweb_creditcard", "Allweb: Кредит картын тайлан"),
        ("zkhbh_card", "ЗХБХ: Картын зээл - Депозит картын зээл"),
        ("gb_credit_balance", "GB: Кредит дансны үлдэгдлийн тайлан"),
        ("citizen_loan_prog", "Иргэдийн зээл программ"),
        ("loan_committee_prog", "Зээлийн хороо программ"),
        ("zkhbh_balance", "ЗХБХ: Үлдэгдэл"),
        ("gb_ipo_sold", "GrapeBank: Ипотект худалдагдсан"),
        ("excel_consolidation", "Excel нэгтгэл"),
    ]
    systems = []
    for code, name in systems_data:
        s = SourceSystem(code=code, name=name)
        systems.append(s)
    db.session.add_all(systems)
    db.session.flush()
    print(f"  ✅ {len(systems)} source systems")
    return systems


def seed_escalation_rules():
    """Load the 15-step escalation ladder from File 1."""
    rules_data = [
        (1, "Бүх хэрэглээний зээл", 1, 20, "4.3",
         "Зээлдэгчтэй холбогдож, шалтгаан тодруулж, зөрчил арилгах. Тайлан татаж хадгалах.",
         EscalationFrequency.DAILY, "БПҮХ", False, False, False, False, False),
        (2, "Бүх хэрэглээний зээл", 4, 5, "4.3",
         "Холбогдож чадаагүй зээлдэгчид SMS илгээх.",
         EscalationFrequency.DAILY, "БПҮХ", True, False, False, False, False),
        (3, "Цахим зээл (Shoppy, Sain)", 5, 5, "4.3",
         "Банкны автомат мессеж илгээх.",
         EscalationFrequency.DAILY, "БПҮХ", True, False, False, False, False),
        (4, "Бүх хэрэглээний зээл", 1, 20, "4.3",
         "Зөрчилтэй ХБЗ, тэтгэврийн зээлийг салбарт мэдэгдэх. Холбоо барих мэдээлэлгүй зээлдэгчийг мэдэгдэх.",
         EscalationFrequency.DAILY, "БПҮХ", False, True, False, False, False),
        (5, "Бизнесийн зээл, Кредит карт, Зээлийн эрх", 1, 20, "4.3",
         "Зээлдэгч, хамтран зээлдэгчтэй холбогдож шалтгаан тодруулах. Тайлбар хөтлөх.",
         EscalationFrequency.DAILY, "ЗМ/ЗХА", False, False, False, False, False),
        (6, "Бизнесийн зээл, Кредит карт", 1, 20, "4.3",
         "Холбогдож чадаагүй зээлдэгчид автомат мессеж, цахим шуудан илгээх.",
         EscalationFrequency.DAILY, "ЗМ/ЗХА", True, True, False, False, False),
        (7, "Бүх зээл", 21, 30, "4.3",
         "Зээлдэгчтэй биечлэн уулзах. Баталгаажуулах бичиг бичүүлж авах.",
         EscalationFrequency.DAILY, "ЗМ/ЗХА", False, False, True, False, False),
        (8, "Бүх зээл", 31, 90, "13.3",
         "Даатгал зуучлалын хэлтэст шилжүүлэх. 40 хоногт LP программд бүртгэх.",
         EscalationFrequency.AS_NEEDED, "ЗМ/ЗХА", False, False, False, False, False),
        (9, "Бүх зээл", 31, 90, "4.3",
         "Шаардлагатай тохиолдолд бүтцийн өөрчлөлт хийх. Хороонд танилцуулах.",
         EscalationFrequency.AS_NEEDED, "ЗМ/ЗХА", False, False, False, True, False),
        (10, "Бүх зээл", 31, 60, "4.3",
         "Банкны албан мэдэгдэл хүргүүлэх.",
         EscalationFrequency.DAILY, "ЗМ/ЗХА", False, False, False, False, False),
        (11, "Автомашины зээл", 61, 90, "4.3",
         "Чанаргүй активтай ажиллах газар, хэлтэст шилжүүлэх.",
         EscalationFrequency.DAILY, "ЗМ/ЗХА", False, False, False, False, True),
        (12, "Бүх зээл", 91, 120, "4.3",
         "Зээлдэгчийн төлөх чадамж, эрмэлзлийг үнэлэх. ТАУГ-т шилжүүлэх санал бэлтгэх. ЗБДС нэхэмжлэх.",
         EscalationFrequency.AS_NEEDED, "ЗМ/ЗХА", False, False, False, True, True),
        (13, "Бүх зээл", 121, 180, "4.3",
         "Барьцаа хөрөнгөтэй танилцах, үнэлгээ шинэчлэх. Албан мэдэгдэл хүргүүлэх.",
         EscalationFrequency.AS_NEEDED, "ЗМ/ЗХА", False, False, True, False, False),
        (14, "Бүх зээл", 61, 9999, "13.1",
         "ТАУГ-т шилжүүлэх нөхцөл хангасан зээлийг шилжүүлэх. Материал хүлээлцэх.",
         EscalationFrequency.AS_NEEDED, "ТАУГ", False, False, False, False, True),
        (15, "Бүх зээл", 180, 9999, "4.3",
         "Даатгалын нөхөн олговор авах. Чанаргүй актив шилжүүлэх санал.",
         EscalationFrequency.AS_NEEDED, "ТАУГ", False, False, False, True, True),
    ]
    rules = []
    for (step, scope, ds, de, clause, action, freq, resp,
         sms, email, visit, committee, taug) in rules_data:
        r = EscalationRule(
            step_number=step, product_scope=scope,
            action_category="Авах арга хэмжээ",
            day_range_start=ds, day_range_end=de,
            regulation_name="Олгосон зээлийн хяналтад баримтлах түр стандарт",
            regulation_clause=clause,
            required_action=action,
            frequency=freq,
            responsible_role=resp,
            auto_sms=sms, auto_email=email,
            requires_visit=visit,
            requires_committee=committee,
            requires_taug_transfer=taug,
            is_active=True,
        )
        rules.append(r)
    db.session.add_all(rules)
    db.session.flush()
    print(f"  ✅ {len(rules)} escalation rules")
    return rules



# ============================================================================
# DATA POOLS
# ============================================================================

LAST_NAMES = [
    "Батсүх", "Дорж", "Ганбаатар", "Оюун", "Мөнх", "Энх", "Нар", "Цэрэн",
    "Бат", "Сүх", "Хүрэл", "Болд", "Тамир", "Сар", "Ган", "Дамдин",
    "Чулуун", "Баяр", "Жамьян", "Лхам", "Пүрэв", "Магнай", "Эрдэнэ", "Амар",
]
FIRST_NAMES = [
    "Батбаяр", "Оюунчимэг", "Ганбат", "Алтанцэцэг", "Болд", "Сарангэрэл",
    "Энхбаяр", "Мөнхзул", "Дэлгэрмаа", "Хүрэлбаатар", "Нарангэрэл", "Цолмон",
    "Жаргал", "Пүрэвдорж", "Тамир", "Ринчин", "Ганзориг", "Галмандах",
    "Баярмаа", "Цэцэгмаа", "Нямаа", "Отгонбаяр", "Эрдэнэ", "Мягмар",
    "Лхагва", "Должин", "Ундрах", "Одгэрэл", "Ариунаа", "Номин",
    "Тэмүүлэн", "Анужин", "Золбоо", "Мөнхбат", "Очирбат", "Содном",
    "Ганболд", "Баатар", "Туяа", "Цэнгэл",
]
ADDRESSES = [
    "УБ, Баянзүрх дүүрэг, 3-р хороо",
    "УБ, Сүхбаатар дүүрэг, 1-р хороо",
    "УБ, Чингэлтэй дүүрэг, 5-р хороо",
    "УБ, Хан-Уул дүүрэг, 11-р хороо",
    "УБ, Баянгол дүүрэг, 20-р хороо",
    "УБ, Сонгинохайрхан дүүрэг, 7-р хороо",
    "Дархан-Уул аймаг, Дархан сум",
    "Орхон аймаг, Баян-Өндөр сум",
    "Дорнод аймаг, Хэрлэн сум",
    "Ховд аймаг, Жаргалант сум",
    "Өвөрхангай аймаг, Арвайхээр сум",
    "Өмнөговь аймаг, Даланзадгад сум",
]

# 🆕 Workplace names pool
WORKPLACES = [
    "Голомт банк", "Хан банк", "Капитрон банк", "ХААН банк", "Төрийн банк",
    "Эрчим хүчний компани", "МКС холдинг", "Тавантолгой ХК",
    "Эрдэнэт уулын баяжуулах үйлдвэр", "Цахилгаан холбоо", "Монгол шуудан ХХК",
    "АНУ ХХК", "Бодь интернэшнл", "Мобиком корпораци", "Юнител",
    "Гэгээ цемент", "Шинэ толь", "Тэнгэр компани",
    "Дархан төмөрлөгийн үйлдвэр", "Уламжлал ХХК", "Алтан хайчин",
    "Их сургууль", "Эмнэлэг", "Засгийн газрын байгууллага",
    "Жижиг дунд бизнес эрхлэгч", "Гэр бүлийн бизнес", "Тэтгэвэрт", "Хувиараа ажилладаг",
]

# 🆕 GrapeBank notes pool
GB_NOTES = [
    "Зээлдэгч төлбөрийн чадваргүй болсон",
    "Цалин хоцорсон",
    "Шилжүүлгийн алдаа гарсан",
    "Хүүхэд төрсний амралттай",
    "Эрүүл мэндийн асуудалтай",
    "Гэр бүлийн нөхцөл байдал хүндэрсэн",
    "Бизнес зогссон",
    "Гадаадад явсан",
    "Уулзалт товлогдсон",
    "ТАУГ-т шилжүүлэх материал бэлтгэгдэж байна",
    "Албан мэдэгдэл хүргүүлсэн",
    "Зээлдэгчтэй холбогдох боломжгүй",
    "Барьцаа хөрөнгөтэй танилцсан",
    "Цалингийн өдрөөр төлнө гэсэн",
    None, None, None,  # some have no notes
]


# ============================================================================
# BORROWERS, LOANS, COLLATERAL (UPDATED with new fields)
# ============================================================================

def seed_borrowers_and_loans(branches, products, users, segments):
    """Create 200 borrowers with 300+ loans, INCLUDING all 25 new fields."""
    print("  📝 Creating borrowers and loans with new fields...")

    retail_products = [p for p in products if p.segment_id == segments[SegmentType.RETAIL].id]
    smb_products = [p for p in products if p.segment_id == segments[SegmentType.SMB].id]

    assignable_users = [u for u in users if u.role.code in (
        "process_control", "zm_control", "zm_research", "retail_hm", "smb_hm"
    )]
    # 🆕 Pools for new staff fields
    analyst_users = [u for u in users if u.role.code in ("zm_research", "risk_analyst", "senior_analyst")]
    hm_users = [u for u in users if u.role.code in ("retail_hm", "smb_hm", "cust_service")]

    all_borrowers = []
    all_loans = []
    all_collaterals = []
    all_related = []

    today = date.today()

    for i in range(200):
        is_retail = random.random() < 0.70
        seg_type = SegmentType.RETAIL if is_retail else SegmentType.SMB
        branch = random.choice(branches)

        borrower = Borrower(
            cif_number=_random_cif(),
            last_name=random.choice(LAST_NAMES),
            first_name=random.choice(FIRST_NAMES),
            register_number=_random_register(),
            phone_primary=_random_phone(),
            phone_secondary=_random_phone() if random.random() < 0.4 else None,
            phone_verified=random.random() < 0.7,
            email=f"user{i+1}@example.mn" if random.random() < 0.5 else None,
            address_residential=random.choice(ADDRESSES),
            address_work=random.choice(ADDRESSES) if random.random() < 0.3 else None,
            address_verified=random.random() < 0.6,
            employment_status=random.choice(["Ажилтай", "Ажилгүй", "Тэтгэвэрт", "Оюутан", "Бизнес эрхлэгч"]),
            income_source=random.choice(["Цалин", "Тэтгэвэр", "Бизнес", "Бусад"]),
            is_deceased=random.random() < 0.01,
            segment=seg_type,
            branch_id=branch.id,
            # 🆕 NEW FIELDS
            workplace_name=random.choice(WORKPLACES) if random.random() < 0.6 else None,
            phone_home=_random_phone() if random.random() < 0.5 else None,
            phone_work=_random_phone() if random.random() < 0.4 else None,
        )
        all_borrowers.append(borrower)

        # Related parties (unchanged)
        if random.random() < 0.3:
            rp = RelatedParty(
                borrower_id=0,
                party_type=random.choice(list(PartyType)),
                name=f"{random.choice(LAST_NAMES)} {random.choice(FIRST_NAMES)}",
                register_number=_random_register(),
                phone_primary=_random_phone(),
                phone_verified=random.random() < 0.5,
                relationship=random.choice(["Эхнэр", "Нөхөр", "Аав", "Ээж", "Ах", "Эгч", "Найз"]),
            )
            all_related.append((i, rp))

    db.session.add_all(all_borrowers)
    db.session.flush()

    for borr_idx, rp in all_related:
        rp.borrower_id = all_borrowers[borr_idx].id
    if all_related:
        db.session.add_all([rp for _, rp in all_related])
        db.session.flush()

    # Create loans with ALL new fields
    for borrower in all_borrowers:
        is_retail = borrower.segment == SegmentType.RETAIL
        prods = retail_products if is_retail else smb_products
        num_loans = random.choices([1, 2, 3], weights=[60, 30, 10])[0]

        for _ in range(num_loans):
            product = random.choice(prods)

            # Amount based on product
            if product.category == "Бизнес":
                amount = Decimal(random.randint(50_000_000, 500_000_000))
            elif product.name in ("Ипотекийн зээл",):
                amount = Decimal(random.randint(50_000_000, 300_000_000))
            elif product.name in ("Автомашины зээл",):
                amount = Decimal(random.randint(10_000_000, 80_000_000))
            elif product.name in ("Кредит карт",):
                amount = Decimal(random.randint(500_000, 10_000_000))
            else:
                amount = Decimal(random.randint(1_000_000, 50_000_000))

            # Delinquency distribution
            rand = random.random()
            if rand < 0.40:
                days = 0
                loan_status = LoanStatus.ACTIVE
                classification = ClassificationLevel.NORMAL
            elif rand < 0.65:
                days = random.randint(1, 30)
                loan_status = LoanStatus.DELINQUENT
                classification = random.choice([ClassificationLevel.NORMAL, ClassificationLevel.WATCH])
            elif rand < 0.85:
                days = random.randint(31, 90)
                loan_status = LoanStatus.DELINQUENT
                classification = random.choice([ClassificationLevel.WATCH, ClassificationLevel.SUBSTANDARD])
            elif rand < 0.95:
                days = random.randint(91, 180)
                loan_status = random.choice([LoanStatus.DELINQUENT, LoanStatus.TRANSFERRED_TAUG])
                classification = random.choice([ClassificationLevel.SUBSTANDARD, ClassificationLevel.DOUBTFUL])
            else:
                days = random.randint(181, 400)
                loan_status = random.choice([LoanStatus.TRANSFERRED_TAUG, LoanStatus.LEGAL, LoanStatus.COURT])
                classification = ClassificationLevel.LOSS

            overdue = Decimal(int(amount * Decimal(str(random.uniform(0.01, 0.15))))) if days > 0 else Decimal(0)
            outstanding = amount - Decimal(int(amount * Decimal(str(random.uniform(0, 0.6)))))
            disbursement = _random_date(2021, 2024)

            escalation_stage = 0
            if days >= 180: escalation_stage = 15
            elif days >= 121: escalation_stage = 13
            elif days >= 91: escalation_stage = 12
            elif days >= 61: escalation_stage = 11
            elif days >= 31: escalation_stage = 8
            elif days >= 21: escalation_stage = 7
            elif days >= 1: escalation_stage = 1

            if days >= 91: priority = "high"
            elif days >= 21: priority = "medium"
            else: priority = "low"

            assigned_user = random.choice(assignable_users)

            # 🆕 NEW FIELD VALUES

            # Group A: staff assignments
            assigned_analyst = random.choice(analyst_users) if analyst_users else None
            assigned_hm = random.choice(hm_users) if hm_users else None

            # Group B: tracking dates
            theoretical_bal = outstanding * Decimal("1.05") if outstanding else None
            last_pay_date = (today - timedelta(days=days)) if days > 0 else today - timedelta(days=random.randint(0, 30))
            review_dt = today + timedelta(days=random.randint(7, 60))
            gb_n = random.choice(GB_NOTES) if days > 0 else None

            # Group C: overdue breakdown (only if delinquent)
            if days > 0 and overdue > 0:
                over_principal = Decimal(int(overdue * Decimal("0.70")))
                over_interest = Decimal(int(overdue * Decimal("0.15")))
                over_commission = Decimal(int(overdue * Decimal("0.05")))
                over_penalty = Decimal(int(overdue * Decimal("0.10")))
            else:
                over_principal = over_interest = over_commission = over_penalty = None

            # Group D: accrued interest
            if days > 0 and outstanding:
                accrued_principal = outstanding * Decimal("0.001") * Decimal(days)
                accrued_commission = outstanding * Decimal("0.0003") * Decimal(days)
                accrued_penalty = outstanding * Decimal("0.0002") * Decimal(days)
            else:
                accrued_principal = accrued_commission = accrued_penalty = None

            # Group E: off-balance (only for 90+ day cases)
            if days >= 90:
                off_bal_account = _random_off_balance_account()
                off_bal_principal = accrued_principal / 2 if accrued_principal else None
                off_bal_commission = accrued_commission / 2 if accrued_commission else None
                off_bal_penalty = accrued_penalty / 2 if accrued_penalty else None
            else:
                off_bal_account = None
                off_bal_principal = off_bal_commission = off_bal_penalty = None

            # Group F: model calculation
            model_date = today - timedelta(days=random.randint(0, 30))
            model_value = Decimal(str(round(random.uniform(20, 95), 2)))

            loan = Loan(
                borrower_id=borrower.id,
                loan_product_id=product.id,
                loan_account_number=_random_loan_number(),
                contract_number=_random_contract(),
                amount_original=amount,
                amount_outstanding=outstanding,
                amount_overdue=overdue,
                currency="MNT",
                interest_rate=Decimal(str(round(random.uniform(8.0, 24.0), 2))),
                term_months=random.choice([6, 12, 24, 36, 48, 60, 120]),
                disbursement_date=disbursement,
                maturity_date=disbursement + timedelta(days=random.choice([365, 730, 1095, 1825])),
                status=loan_status,
                classification=classification,
                delinquency_days=days,
                delinquency_start_date=(today - timedelta(days=days)) if days > 0 else None,
                current_escalation_stage=escalation_stage,
                priority=priority,
                is_transferred_to_taug=loan_status in (LoanStatus.TRANSFERRED_TAUG, LoanStatus.LEGAL, LoanStatus.COURT),
                taug_transfer_date=(today - timedelta(days=max(0, days-90))) if loan_status == LoanStatus.TRANSFERRED_TAUG else None,
                has_zbds_guarantee=random.random() < 0.15,
                is_insurance_eligible=random.random() < 0.3,
                restructure_count=random.choices([0, 1, 2], weights=[80, 15, 5])[0],
                branch_id=borrower.branch_id,
                assigned_to=assigned_user.id,
                assigned_zm_id=assigned_user.id,
                source_system="grapebank_delinquency",
                # 🆕 NEW FIELDS
                assigned_analyst_id=assigned_analyst.id if assigned_analyst else None,
                assigned_hm_id=assigned_hm.id if assigned_hm else None,
                theoretical_balance=theoretical_bal,
                last_payment_date=last_pay_date,
                review_date=review_dt,
                gb_notes=gb_n,
                overdue_principal=over_principal,
                overdue_principal_days=days if days > 0 else None,
                overdue_interest=over_interest,
                overdue_interest_days=days if days > 0 else None,
                overdue_commission_interest=over_commission,
                overdue_commission_days=days if days > 0 else None,
                overdue_penalty_interest=over_penalty,
                overdue_penalty_days=days if days > 0 else None,
                accrued_principal_interest=accrued_principal,
                accrued_commission_interest=accrued_commission,
                accrued_penalty_interest=accrued_penalty,
                off_balance_account_number=off_bal_account,
                off_balance_principal_interest=off_bal_principal,
                off_balance_commission_interest=off_bal_commission,
                off_balance_penalty_interest=off_bal_penalty,
                model_calculation_date=model_date,
                model_calculation_value=model_value,
            )
            all_loans.append(loan)

            # Collateral with new fields
            if product.name in ("Ипотекийн зээл", "Автомашины зээл", "Бизнесийн зээл") or random.random() < 0.15:
                ctype = {
                    "Ипотекийн зээл": CollateralType.REAL_ESTATE,
                    "Автомашины зээл": CollateralType.VEHICLE,
                    "Бизнесийн зээл": random.choice([CollateralType.REAL_ESTATE, CollateralType.MOVABLE_PROPERTY]),
                }.get(product.name, random.choice(list(CollateralType)))

                coll = Collateral(
                    loan_id=0,
                    borrower_id=borrower.id,
                    collateral_type=ctype,
                    description=f"{ctype.value} барьцаа",
                    valuation_amount=amount * Decimal(str(round(random.uniform(0.8, 1.5), 2))),
                    valuation_date=_random_date(2022, 2025),
                    status=CollateralStatus.ACTIVE,
                    needs_revaluation=days > 120,
                    # 🆕 NEW FIELDS
                    coverage_percent=Decimal(str(round(random.uniform(80, 150), 2))),
                    is_unregistered=random.random() < 0.05,
                )
                all_collaterals.append((len(all_loans) - 1, coll))

    db.session.add_all(all_loans)
    db.session.flush()

    for loan_idx, coll in all_collaterals:
        coll.loan_id = all_loans[loan_idx].id
    if all_collaterals:
        db.session.add_all([c for _, c in all_collaterals])
        db.session.flush()

    print(f"  ✅ {len(all_borrowers)} borrowers created (with workplace/phones)")
    print(f"  ✅ {len(all_loans)} loans created (with all 22 new fields)")
    print(f"  ✅ {len(all_collaterals)} collaterals created (with coverage_percent)")
    print(f"  ✅ {len(all_related)} related parties created")
    return all_borrowers, all_loans


# ============================================================================
# 🆕 NEW: DEPOSIT ACCOUNTS
# ============================================================================

def seed_deposit_accounts(borrowers):
    """Create 1-4 deposit accounts per borrower (primary payment + savings/current)."""
    print("  📝 Creating deposit accounts...")
    today = date.today()
    all_accounts = []

    for borrower in borrowers:
        # Every borrower gets 1 primary payment account
        primary = DepositAccount(
            borrower_id=borrower.id,
            account_number=_random_deposit_account_number(),
            account_type=DepositAccountType.PAYMENT,
            balance=Decimal(random.randint(0, 5_000_000)),
            currency=random.choices(["MNT", "USD", "EUR"], weights=[90, 8, 2])[0],
            is_frozen=random.random() < 0.03,
            is_primary_payment=True,
            opened_date=_random_date(2018, 2024),
            last_activity_date=today - timedelta(days=random.randint(0, 60)),
        )
        all_accounts.append(primary)

        # 0-2 savings accounts
        for _ in range(random.choices([0, 1, 2], weights=[40, 40, 20])[0]):
            savings = DepositAccount(
                borrower_id=borrower.id,
                account_number=_random_deposit_account_number(),
                account_type=DepositAccountType.SAVINGS,
                balance=Decimal(random.randint(0, 50_000_000)),
                currency=random.choices(["MNT", "USD"], weights=[85, 15])[0],
                is_frozen=random.random() < 0.02,
                is_primary_payment=False,
                opened_date=_random_date(2018, 2024),
                last_activity_date=today - timedelta(days=random.randint(0, 180)),
            )
            all_accounts.append(savings)

        # 0-1 current account
        if random.random() < 0.3:
            current = DepositAccount(
                borrower_id=borrower.id,
                account_number=_random_deposit_account_number(),
                account_type=DepositAccountType.CURRENT,
                balance=Decimal(random.randint(0, 10_000_000)),
                currency="MNT",
                is_frozen=False,
                is_primary_payment=False,
                opened_date=_random_date(2018, 2024),
                last_activity_date=today - timedelta(days=random.randint(0, 30)),
            )
            all_accounts.append(current)

    db.session.add_all(all_accounts)
    db.session.flush()
    print(f"  ✅ {len(all_accounts)} deposit accounts created")
    return all_accounts


# ============================================================================
# CONTACT LOGS, HISTORY, ACTIONS (unchanged)
# ============================================================================

def seed_contact_logs(loans, users):
    """Create contact log entries for delinquent loans."""
    print("  📝 Creating contact logs...")
    contact_users = [u for u in users if u.role.code in ("process_control", "zm_control")]
    delinquent = [l for l in loans if l.delinquency_days > 0]

    logs = []
    for loan in delinquent:
        num_contacts = random.randint(1, min(5, max(1, loan.delinquency_days // 5)))
        for attempt in range(num_contacts):
            days_ago = random.randint(0, min(30, loan.delinquency_days))
            contact_dt = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(0, 8))
            was_reached = random.random() < 0.6

            log = ContactLog(
                loan_id=loan.id,
                borrower_id=loan.borrower_id,
                contact_type=random.choice([ContactType.PHONE_CALL, ContactType.SMS, ContactType.EMAIL]),
                contact_direction=ContactDirection.OUTBOUND,
                phone_number_used=_random_phone(),
                was_reached=was_reached,
                attempt_number=attempt + 1,
                reason_not_reached=random.choice([
                    "Утас авсангүй", "Дугаар буруу", "Унтраасан", None
                ]) if not was_reached else None,
                delinquency_reason=random.choice([
                    "Цалин хоцорсон", "Өвчтэй байсан", "Мартсан", "Санхүүгийн бэрхшээл", None
                ]) if was_reached else None,
                promised_payment_date=(
                    date.today() + timedelta(days=random.randint(1, 14))
                ) if was_reached and random.random() < 0.4 else None,
                notes=random.choice([
                    "Утсаар холбогдож мэдэгдсэн.",
                    "SMS илгээсэн.",
                    "Дахин залгах шаардлагатай.",
                    "Төлнө гэж амласан.",
                    "Утас авсангүй, 2 удаа залгасан.",
                    "Цахим шуудан илгээсэн.",
                    None,
                ]),
                contacted_by=random.choice(contact_users).id,
                contact_date=contact_dt,
            )
            logs.append(log)

    db.session.add_all(logs)
    db.session.flush()
    print(f"  ✅ {len(logs)} contact logs created")
    return logs


def seed_delinquency_history(loans):
    """Create daily snapshots for past 30 days for delinquent loans."""
    print("  📝 Creating delinquency history...")
    delinquent = [l for l in loans if l.delinquency_days > 0]
    today = date.today()

    snapshots = []
    for loan in delinquent:
        history_days = min(30, loan.delinquency_days)
        for d in range(history_days):
            snap_date = today - timedelta(days=d)
            snap = DelinquencyHistory(
                loan_id=loan.id,
                snapshot_date=snap_date,
                delinquency_days=loan.delinquency_days - d,
                amount_overdue=loan.amount_overdue,
                amount_outstanding=loan.amount_outstanding,
                escalation_stage=loan.current_escalation_stage,
                classification=loan.classification,
                was_contacted=random.random() < 0.3,
                contact_attempts=random.randint(0, 2),
                source_report="grapebank_delinquency",
            )
            snapshots.append(snap)

    db.session.add_all(snapshots)
    db.session.flush()
    print(f"  ✅ {len(snapshots)} delinquency history snapshots created")
    return snapshots


def seed_actions_and_extras(loans, users):
    """Create ActionTaken, transfers, outsourcing, committee reviews."""
    print("  📝 Creating actions, transfers, committee reviews...")
    delinquent = [l for l in loans if l.delinquency_days > 0]
    staff = [u for u in users if u.role.code in ("process_control", "zm_control", "taug_specialist")]
    today = date.today()

    actions = []
    transfers = []
    outsourcings = []
    reviews = []

    for loan in delinquent:
        num_actions = random.randint(1, min(3, max(1, loan.delinquency_days // 10)))
        for _ in range(num_actions):
            a = ActionTaken(
                loan_id=loan.id,
                action_type=random.choice([
                    ActionType.CALL_MADE, ActionType.SMS_SENT, ActionType.EMAIL_SENT,
                    ActionType.REPORT_PULLED, ActionType.BRANCH_NOTIFIED,
                ]),
                action_description="Зааврын дагуу арга хэмжээ авсан.",
                performed_by=random.choice(staff).id,
                performed_at=datetime.now(timezone.utc) - timedelta(
                    days=random.randint(0, min(30, loan.delinquency_days))
                ),
            )
            actions.append(a)

        if loan.delinquency_days >= 60 and random.random() < 0.5:
            t = CaseTransfer(
                loan_id=loan.id,
                from_user_id=random.choice(staff).id,
                to_entity=random.choice(["ТАУГ", "ЧАХ", "ЗДХ"]),
                reason="Төлбөрийн зөрчил удаан хугацаатай.",
                materials_attached=random.random() < 0.6,
                status=TransferStatus.COMPLETED if random.random() < 0.7 else TransferStatus.PENDING,
            )
            transfers.append(t)

        if loan.delinquency_days >= 180 and random.random() < 0.3:
            o = OutsourcingAssignment(
                loan_id=loan.id,
                company_name=random.choice(["Итгэл Цуглуулалт ХХК", "Авлага Барагдуулах ХХК", "Голомт Коллекшн ХХК"]),
                assigned_date=today - timedelta(days=random.randint(0, 60)),
                commission_rate=round(random.uniform(0.05, 0.15), 2),
                collected_amount=float(loan.amount_overdue) * random.uniform(0, 0.3) if random.random() < 0.4 else 0,
                status=random.choice([OutsourcingStatus.ACTIVE, OutsourcingStatus.COMPLETED]),
            )
            outsourcings.append(o)

        if loan.delinquency_days >= 30 and random.random() < 0.4:
            r = CommitteeReview(
                loan_id=loan.id,
                committee_type=random.choice([CommitteeType.ZDKH, CommitteeType.CHAKH, CommitteeType.ZKH]),
                meeting_date=today - timedelta(days=random.randint(0, 30)),
                current_classification=loan.classification,
                proposed_classification=loan.classification,
                explanation_notes="Зээлдэгчийн нөхцөл байдал хэлэлцсэн.",
                decision=random.choice([CommitteeDecisionType.MAINTAIN, CommitteeDecisionType.DOWNGRADE, CommitteeDecisionType.RESTRUCTURE]),
                decision_text="Хорооны хурлын шийдвэрийн дагуу.",
                next_action="Дараагийн сарын хуралд дахин танилцуулах.",
                deadline=today + timedelta(days=30),
                status=random.choice([ReviewStatus.DECIDED, ReviewStatus.FINALIZED]),
            )
            reviews.append(r)

    db.session.add_all(actions)
    db.session.add_all(transfers)
    db.session.add_all(outsourcings)
    db.session.add_all(reviews)
    db.session.flush()

    print(f"  ✅ {len(actions)} actions created")
    print(f"  ✅ {len(transfers)} case transfers created")
    print(f"  ✅ {len(outsourcings)} outsourcing assignments created")
    print(f"  ✅ {len(reviews)} committee reviews created")


# ============================================================================
# MAIN SEED
# ============================================================================

def seed():
    """Run all seeders in order."""
    print("\n" + "=" * 60)
    print("🌱 SEEDING DATABASE (UPDATED with new fields)")
    print("=" * 60)

    print("\n📦 Reference data...")
    segments = seed_segments()
    regions = seed_regions(segments)
    branches = seed_branches(regions)
    roles = seed_roles()
    users = seed_users(roles, branches)
    products = seed_loan_products(segments)
    seed_source_systems()
    seed_escalation_rules()

    print("\n📦 Core data...")
    borrowers, loans = seed_borrowers_and_loans(branches, products, users, segments)

    print("\n📦 Deposit accounts (NEW)...")
    seed_deposit_accounts(borrowers)

    print("\n📦 Activity data...")
    seed_contact_logs(loans, users)
    seed_delinquency_history(loans)
    seed_actions_and_extras(loans, users)

    db.session.commit()

    print("\n" + "=" * 60)
    print("✅ DATABASE SEEDED SUCCESSFULLY!")
    print("=" * 60)

    print(f"\n📊 Summary:")
    print(f"   Segments:        {Segment.query.count()}")
    print(f"   Regions:         {Region.query.count()}")
    print(f"   Branches:        {Branch.query.count()}")
    print(f"   Roles:           {Role.query.count()}")
    print(f"   Users:           {User.query.count()}")
    print(f"   Loan Products:   {LoanProduct.query.count()}")
    print(f"   Source Systems:  {SourceSystem.query.count()}")
    print(f"   Esc. Rules:      {EscalationRule.query.count()}")
    print(f"   Borrowers:       {Borrower.query.count()}")
    print(f"   Loans:           {Loan.query.count()}")
    print(f"   Collaterals:     {Collateral.query.count()}")
    print(f"   Deposit Accts:   {DepositAccount.query.count()}  🆕")
    print(f"   Contact Logs:    {ContactLog.query.count()}")
    print(f"   History Snaps:   {DelinquencyHistory.query.count()}")
    print(f"   Actions:         {ActionTaken.query.count()}")
    print(f"   Transfers:       {CaseTransfer.query.count()}")
    print(f"   Outsourcing:     {OutsourcingAssignment.query.count()}")
    print(f"   Committee:       {CommitteeReview.query.count()}")
    print(f"   ─────────────────────────")
    total = sum([
        Segment.query.count(), Region.query.count(), Branch.query.count(),
        Role.query.count(), User.query.count(), LoanProduct.query.count(),
        SourceSystem.query.count(), EscalationRule.query.count(),
        Borrower.query.count(), Loan.query.count(), Collateral.query.count(),
        DepositAccount.query.count(),
        ContactLog.query.count(), DelinquencyHistory.query.count(),
        ActionTaken.query.count(), CaseTransfer.query.count(),
        OutsourcingAssignment.query.count(), CommitteeReview.query.count(),
    ])
    print(f"   Total records:   {total}")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        print("🗑️  Dropping all tables...")
        db.drop_all()
        print("🏗️  Creating all tables...")
        db.create_all()
        print("✅ Tables ready!\n")
        seed()
