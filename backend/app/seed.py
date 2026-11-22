"""Fictional demo data. Run: python -m app.seed  (safe to rerun)."""
import uuid

from sqlalchemy.orm import Session

from app.catalog import change_stock
from app.db import SessionLocal
from app.models import Membership, Organization, Product, StaffGrant, User


def _id(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"bolmava-seed:{name}")


ORGS = [
    dict(id=_id("org:sri-lakshmi"), name="Sri Lakshmi Switchgear (Fictional)", city="Vijayawada", state="Andhra Pradesh",
         can_sell=True, can_buy=False, verification_status="simulated_verified"),
    dict(id=_id("org:godavari"), name="Godavari Electricals Distributors (Fictional)", city="Guntur", state="Andhra Pradesh",
         can_sell=True, can_buy=True, verification_status="simulated_verified"),
    dict(id=_id("org:vizag-home"), name="Vizag Home Electric Store (Fictional)", city="Visakhapatnam", state="Andhra Pradesh",
         can_sell=False, can_buy=True),
]

# (email, display name, language, org key, role)
USERS = [
    ("ravi.seller@example.test", "Ravi (Fictional)", "te", "org:sri-lakshmi", "admin"),
    ("anitha.catalog@example.test", "Anitha (Fictional)", "te", "org:sri-lakshmi", "catalog_manager"),
    ("suresh.buyer@example.test", "Suresh (Fictional)", "te", "org:godavari", "purchaser"),
    ("lakshmi.admin@example.test", "Lakshmi (Fictional)", "en", "org:godavari", "admin"),
    ("meena.viewer@example.test", "Meena (Fictional)", "en", "org:godavari", "viewer"),
    ("kiran.retail@example.test", "Kiran (Fictional)", "en", "org:vizag-home", "admin"),
]

CITIES = ["Vijayawada", "Guntur", "Visakhapatnam"]
# (org key, sku, name, name_te, amps, ways, unit, pack, moq, price paise, stock, lead days)
PRODUCTS = [
    ("org:sri-lakshmi", "SL-6A-1W-10", "6A one-way modular switch, box of 10", "6A వన్-వే స్విచ్, 10 బాక్స్", 6, 1, "box", 10, 5, 45000, 500, 3),
    ("org:sri-lakshmi", "SL-16A-1W-10", "16A one-way power switch, box of 10", "16A పవర్ స్విచ్, 10 బాక్స్", 16, 1, "box", 10, 5, 95000, 200, 5),
    ("org:sri-lakshmi", "SL-6A-2W-10", "6A two-way modular switch, box of 10", "6A టూ-వే స్విచ్, 10 బాక్స్", 6, 2, "box", 10, 5, 62000, 150, 3),
    ("org:sri-lakshmi", "SL-BELL-1", "6A bell push switch", "బెల్ పుష్ స్విచ్", 6, 1, "piece", 1, 50, 5500, 1000, 2),
    ("org:godavari", "GD-6A-1W-10", "6A one-way modular switch, box of 10 (resale)", None, 6, 1, "box", 10, 1, 52000, 40, 1),
]


# Platform staff belong to no organization; grants exist only here or through direct operator setup.
STAFF = [
    ("farah.finance@example.test", "Farah (Fictional finance)", "en", "finance"),
    ("arjun.finance@example.test", "Arjun (Fictional finance)", "en", "finance"),  # second person for reversal approvals
    ("sanjay.support@example.test", "Sanjay (Fictional support)", "te", "support"),
    ("vani.support@example.test", "Vani (Fictional support)", "en", "support"),
]


def seed_staff(db: Session) -> bool:
    changed = False
    for email, name, lang, role in STAFF:
        user_id = _id(f"user:{email}")
        if db.get(User, user_id) is None:
            db.add(User(id=user_id, email=email, display_name=name, preferred_language=lang))
            db.flush()
            db.add(StaffGrant(user_id=user_id, role=role, note="fictional seed staff"))
            changed = True
    db.commit()
    return changed


def seed(db: Session) -> bool:
    staff_changed = seed_staff(db)
    if db.get(Organization, ORGS[0]["id"]):
        return staff_changed
    for org in ORGS:
        db.add(Organization(**org))
    for email, name, lang, org_key, role in USERS:
        user = User(id=_id(f"user:{email}"), email=email, display_name=name, preferred_language=lang)
        db.add(user)
        db.flush()
        db.add(Membership(org_id=_id(org_key), user_id=user.id, role=role))
    for org_key, sku, name, name_te, amps, ways, unit, pack, moq, price, stock, lead in PRODUCTS:
        product = Product(
            id=_id(f"product:{sku}"), org_id=_id(org_key), sku=sku, name=name, name_te=name_te,
            brand="Kanaka (Fictional)", model=sku, rating_amps=amps, voltage_v=240, ways=ways, unit=unit,
            pack_size=pack, moq=moq, price_paise=price, lead_time_days=lead, delivery_cities=CITIES,
        )
        db.add(product)
        db.flush()
        change_stock(db, product.org_id, product.id, stock, "restock", "Seed stock", None, f"seed:{sku}")
    db.commit()
    return True


if __name__ == "__main__":
    with SessionLocal() as session:
        print("Seeded fictional demo data." if seed(session) else "Seed data already present; nothing changed.")
