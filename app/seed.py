"""
Database seeder — populates the DB with realistic Mongolian sample data.
Run with: python run.py seed
"""
from datetime import datetime, date, timedelta
import random

from app.models import (
    User, Borrower, Loan, CollectionCase,
    CaseAction, CaseTransfer, OutsourcingAssignment, CommitteeDecision,
)


def seed_database(db):
    """Drop all tables and re-create with sample data."""
    print("🗑️  Dropping existing tables...")
    db.drop_all()
    db.create_all()

    print("👤 Creating users...")
    users = [
        User(name="Мөнхөө Б.", role="bpuh", branch="Баянзүрх", email="munkhuu@bank.mn"),
        User(name="Оюунаа Д.", role="bpuh", branch="Сүхбаатар", email="oyunaa@bank.mn"),
        User(name="Баярмаа С.", role="zm", branch="Баянзүрх", email="bayarmaa@bank.mn"),
        User(name="Ариунаа Т.", role="zm", branch="Сүхбаатар", email="ariunaa@bank.mn"),
        User(name="Энхжин Г.", role="jdbbg", branch="Корпоратив", email="enkhjin@bank.mn"),
        User(name="Болд Н.", role="taug", branch="Хууль зүй", email="bold@bank.mn"),
        User(name="Мөнхтуяа Д.", role="taug", branch="Хууль зүй", email="munkhtuya@bank.mn"),
        User(name="Агент-1", role="outsourcing", branch="Кредит Солюшн", email="agent1@creditsolution.mn"),
        User(name="Сарантуяа М.", role="senior", branch="ЗЭГ", email="sarantuya@bank.mn"),
        User(name="Ганзориг Д.", role="mgmt", branch="Удирдлага", email="ganzorig@bank.mn"),
    ]
    db.session.add_all(users)
    db.session.flush()

    print("🏦 Creating borrowers...")
    consumer_names = [
        ("Батболд Д.", "БЗ89010112", "99112233", "Баянзүрх дүүрэг"),
        ("Сарангэрэл О.", "СБ92051534", "88223344", "Сүхбаатар дүүрэг"),
        ("Энхжаргал Б.", "ХУ87032156", "99334455", "Хан-Уул дүүрэг"),
        ("Мөнхбат Т.", "ЧЭ90111278", "88445566", "Чингэлтэй дүүрэг"),
        ("Оюунчимэг Н.", "БГ85060390", "99556677", "Баянгол дүүрэг"),
        ("Ганбаатар С.", "БЗ91080412", "88667788", "Баянзүрх дүүрэг"),
        ("Нарантуяа Ц.", "СБ88120534", "99778899", "Сүхбаатар дүүрэг"),
        ("Дэлгэрмаа Б.", "НХ93020656", "88889900", "Налайх дүүрэг"),
        ("Түмэнжаргал Г.", "ХУ86090778", "99001122", "Хан-Уул дүүрэг"),
        ("Алтанцэцэг Д.", "ЧЭ94030890", "88112233", "Чингэлтэй дүүрэг"),
        ("Баярсайхан Б.", "БГ89071012", "99223344", "Баянгол дүүрэг"),
        ("Цогтбаатар О.", "БЗ91041134", "88334455", "Баянзүрх дүүрэг"),
        ("Мөнхзул Э.", "СБ87121256", "99445566", "Сүхбаатар дүүрэг"),
        ("Эрдэнэбат Д.", "ХУ90051378", "88556677", "Хан-Уул дүүрэг"),
        ("Цэрэнханд М.", "ЧЭ88081490", "99667788", "Чингэлтэй дүүрэг"),
        ("Содбаатар Ж.", "НХ92101512", "88778899", "Налайх дүүрэг"),
        ("Болормаа Н.", "БЗ86031634", "99889900", "Баянзүрх дүүрэг"),
        ("Ундрах Г.", "СБ93071756", "88990011", "Сүхбаатар дүүрэг"),
        ("Тэмүүлэн С.", "БГ89111878", "99001133", "Баянгол дүүрэг"),
        ("Золзаяа Б.", "ХУ91021990", "88112244", "Хан-Уул дүүрэг"),
    ]

    borrowers = []
    for name, reg, phone, addr in consumer_names:
        b = Borrower(name=name, register_no=reg, phone=phone,
                     email=f"{name.split()[0].lower()}@email.mn",
                     address=addr, segment="consumer")
        borrowers.append(b)

    corp_data = [
        ("Монгол Алт ХХК", "МА-2019001", "77110011", "БЗД, 1-р хороо"),
        ("Эрдэнэт Трейд ХХК", "ЭТ-2018002", "77220022", "СБД, 3-р хороо"),
        ("УБ Констракшн ХХК", "УК-2017003", "77330033", "ХУД, 5-р хороо"),
        ("Говь Трэйд ХХК", "ГТ-2020004", "77440044", "ЧД, 2-р хороо"),
        ("Номин Импэкс ХХК", "НИ-2016005", "77550055", "БГД, 8-р хороо"),
    ]
    for name, reg, phone, addr in corp_data:
        b = Borrower(name=name, register_no=reg, phone=phone,
                     email=f"info@{name.split()[0].lower()}.mn",
                     address=addr, segment="corporate")
        borrowers.append(b)

    db.session.add_all(borrowers)
    db.session.flush()

    print("💰 Creating loans...")
    branches = ["Баянзүрх", "Сүхбаатар", "Хан-Уул", "Чингэлтэй", "Баянгол", "Налайх"]
    consumer_products = ["consumer", "mortgage", "credit_card", "auto"]
    corp_products = ["sme", "corporate", "trade_finance"]

    loans = []
    for i, b in enumerate(borrowers):
        is_corp = b.segment == "corporate"
        prod = random.choice(corp_products if is_corp else consumer_products)
        if is_corp:
            amt = random.choice([500_000_000, 1_200_000_000, 2_800_000_000, 4_200_000_000, 800_000_000])
        else:
            amt = random.choice([5_000_000, 8_500_000, 12_000_000, 15_000_000, 22_000_000,
                                 35_000_000, 45_000_000, 7_600_000, 9_800_000, 18_200_000])
        balance = round(amt * random.uniform(0.3, 1.0))
        loan = Loan(
            borrower_id=b.id,
            loan_number=f"L-2024-{1000 + i}",
            product_type=prod,
            amount=amt,
            balance=balance,
            disbursement_date=date(2023, random.randint(1, 12), random.randint(1, 28)),
            maturity_date=date(2026, random.randint(1, 12), random.randint(1, 28)),
            interest_rate=round(random.uniform(12.0, 24.0), 1),
            status="active",
            branch=random.choice(branches),
        )
        loans.append(loan)

    # Add extra loans for some borrowers (multiple loans per borrower)
    for i in range(5):
        b = borrowers[i]
        amt = random.choice([3_000_000, 6_000_000, 10_000_000])
        loan = Loan(
            borrower_id=b.id,
            loan_number=f"L-2024-{2000 + i}",
            product_type="consumer",
            amount=amt,
            balance=round(amt * random.uniform(0.5, 0.9)),
            disbursement_date=date(2024, random.randint(1, 6), random.randint(1, 28)),
            maturity_date=date(2027, random.randint(1, 12), random.randint(1, 28)),
            interest_rate=round(random.uniform(14.0, 20.0), 1),
            status="active",
            branch=random.choice(branches),
        )
        loans.append(loan)

    db.session.add_all(loans)
    db.session.flush()

    print("📋 Creating collection cases...")
    statuses = ["new", "contacted", "promise", "no_answer", "transferred",
                "legal", "court", "outsourced", "resolved"]
    priorities = ["high", "medium", "low"]
    queues = ["retail_early", "retail_late", "corporate", "legal", "outsource"]

    cases = []
    collector_users = [u for u in users if u.role in ("bpuh", "zm", "jdbbg", "taug")]

    for i, loan in enumerate(loans[:30]):
        status = random.choice(statuses)
        days = random.randint(5, 180)
        overdue = round(loan.balance * random.uniform(0.05, 0.3))

        # Assign to appropriate user based on segment
        if loan.borrower.segment == "corporate":
            assigned = next((u for u in users if u.role == "jdbbg"), users[0])
        elif status in ("legal", "court", "transferred"):
            assigned = next((u for u in users if u.role == "taug"), users[0])
        else:
            assigned = random.choice([u for u in users if u.role in ("bpuh", "zm")])

        case = CollectionCase(
            loan_id=loan.id,
            assigned_to=assigned.id,
            days_overdue=days,
            overdue_amount=overdue,
            priority=random.choice(priorities),
            status=status,
            queue=random.choice(queues),
            created_at=datetime.utcnow() - timedelta(days=days),
            updated_at=datetime.utcnow() - timedelta(days=random.randint(0, 5)),
        )
        cases.append(case)

    # 10 more cases for variety
    for i in range(10):
        loan = loans[i]
        case = CollectionCase(
            loan_id=loan.id,
            assigned_to=random.choice(collector_users).id,
            days_overdue=random.randint(1, 30),
            overdue_amount=round(loan.balance * 0.02),
            priority="low",
            status="new",
            queue="retail_early",
            created_at=datetime.utcnow() - timedelta(days=random.randint(1, 10)),
        )
        cases.append(case)

    db.session.add_all(cases)
    db.session.flush()

    print("📞 Creating case actions...")
    action_types = ["phone_call", "official_letter", "meeting",
                    "promise_letter", "note", "collateral_check", "transfer"]
    outcomes = ["promise_made", "no_answer", "payment_made",
                "callback", "transfer_to_taug", "transfer_to_outsourcing"]
    note_templates = [
        "Утсаар холбогдож, төлбөрийн талаар мэдэгдсэн.",
        "Зээлдэгч 7 хоногийн дотор төлнө гэж амласан.",
        "Утас авсангүй, дахин залгах шаардлагатай.",
        "Албан бичиг бэлтгэж хаягаар илгээсэн.",
        "Зээлдэгчтэй уулзалт хийсэн, нөхцөл байдлыг тодруулсан.",
        "Барьцаа хөрөнгийн байдалтай танилцсан.",
        "Төлбөр хэсэгчлэн хийсэн.",
        "Амлалт бичиг бичүүлж авсан.",
        "ТАУГ-т шилжүүлэх шаардлагатай гэж дүгнэсэн.",
        "Гэр бүлийн гишүүнтэй холбогдсон.",
    ]

    actions = []
    for case in cases:
        num_actions = random.randint(1, 4)
        for j in range(num_actions):
            action = CaseAction(
                case_id=case.id,
                user_id=case.assigned_to,
                action_type=random.choice(action_types[:5]),  # Most common types
                outcome=random.choice(outcomes[:4]),
                notes=random.choice(note_templates),
                scheduled_follow_up=(
                    datetime.utcnow() + timedelta(days=random.randint(1, 14))
                    if random.random() > 0.5 else None
                ),
                created_at=case.created_at + timedelta(days=j * random.randint(1, 7)),
            )
            actions.append(action)

    db.session.add_all(actions)
    db.session.flush()

    print("➡️  Creating case transfers...")
    transferred_cases = [c for c in cases if c.status in ("transferred", "legal", "court")]
    zm_users = [u for u in users if u.role in ("zm", "bpuh")]
    transfers = []
    for i, case in enumerate(transferred_cases[:8]):
        transfer = CaseTransfer(
            case_id=case.id,
            from_user_id=random.choice(zm_users).id,
            to_entity="taug" if case.status != "court" else "court",
            transfer_date=datetime.utcnow() - timedelta(days=random.randint(5, 30)),
            reason=random.choice([
                "Бүх арга хэмжээ авсан боловч үр дүнгүй",
                "90 хоногоос дээш хугацаа хэтэрсэн",
                "Зээлдэгч холбоо барихаас зайлсхийж байна",
                "Хуулийн арга хэмжээ шаардлагатай",
            ]),
            materials_attached=random.choice([True, False]),
            status=random.choice(["pending", "accepted", "completed"]),
        )
        transfers.append(transfer)

    db.session.add_all(transfers)
    db.session.flush()

    print("🏢 Creating outsourcing assignments...")
    outsourcing_companies = ["Кредит Солюшн ХХК", "МН Коллект ХХК", "Файнанс Рикавери ХХК"]
    outsourced_cases = [c for c in cases if c.status == "outsourced"]
    os_assignments = []
    for i, case in enumerate(outsourced_cases[:5]):
        oa = OutsourcingAssignment(
            case_id=case.id,
            company_name=random.choice(outsourcing_companies),
            assigned_date=date.today() - timedelta(days=random.randint(10, 60)),
            commission_rate=random.choice([0.08, 0.10, 0.12]),
            collected_amount=round(case.overdue_amount * random.uniform(0, 0.5)),
            status=random.choice(["active", "completed"]),
        )
        os_assignments.append(oa)

    # Ensure at least 5
    while len(os_assignments) < 5:
        case = random.choice(cases)
        oa = OutsourcingAssignment(
            case_id=case.id,
            company_name=random.choice(outsourcing_companies),
            assigned_date=date.today() - timedelta(days=random.randint(10, 60)),
            commission_rate=0.10,
            collected_amount=round(case.overdue_amount * random.uniform(0, 0.3)),
            status="active",
        )
        os_assignments.append(oa)

    db.session.add_all(os_assignments)
    db.session.flush()

    print("🏛️  Creating committee decisions...")
    decisions = []
    for i in range(6):
        case = cases[i * 5]  # Spread across cases
        dec = CommitteeDecision(
            case_id=case.id,
            decision_date=date.today() - timedelta(days=random.randint(5, 45)),
            decision_text=random.choice([
                "Зээлийн нөхцөлийг өөрчилж, хугацааг 6 сараар сунгах",
                "ТАУГ-т шилжүүлж, хууль зүйн арга хэмжээ авах",
                "Outsourcing компанид шилжүүлэх",
                "3 сарын хугацаанд төлбөрийн хуваарь гаргах",
                "Барьцаа хөрөнгийг борлуулж, зээлийг хаах",
                "Зээлдэгчтэй эвлэрлийн гэрээ байгуулах",
            ]),
            next_action=random.choice([
                "Салбар хариуцна",
                "ТАУГ ажилтан хуваарилах",
                "Outsourcing гэрээ хийх",
                "Зээлдэгчид мэдэгдэх",
            ]),
            deadline=date.today() + timedelta(days=random.randint(7, 60)),
            status=random.choice(["pending", "completed", "overdue"]),
        )
        decisions.append(dec)

    db.session.add_all(decisions)
    db.session.commit()

    # Print summary
    print(f"\n📊 Seed Summary:")
    print(f"   Users:         {User.query.count()}")
    print(f"   Borrowers:     {Borrower.query.count()}")
    print(f"   Loans:         {Loan.query.count()}")
    print(f"   Cases:         {CollectionCase.query.count()}")
    print(f"   Actions:       {CaseAction.query.count()}")
    print(f"   Transfers:     {CaseTransfer.query.count()}")
    print(f"   Outsourcing:   {OutsourcingAssignment.query.count()}")
    print(f"   Decisions:     {CommitteeDecision.query.count()}")
