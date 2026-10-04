from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from flask_login import login_required, current_user

from app import db
from app.models import (
    Purchase,
    PurchaseItem,
    Product,
    StockLocation,
    StockHolding,
    StockMovement,
    MoneyAccount,
    FinancialTransaction,
    PartnerTransaction,
    SupplierOrder,
    SupplierOrderCost,
    User
)


purchases = Blueprint(
    "purchases",
    __name__,
    url_prefix="/purchases"
)


# ============================================================
# HELPERS
# ============================================================

def money(value):
    return Decimal(str(value or 0))


def parse_amount(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None

    return amount


def parse_datetime_local(value):
    if not value:
        return datetime.utcnow()

    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def get_account_balance(account_id):

    transactions = FinancialTransaction.query.filter(
        (FinancialTransaction.to_account_id == account_id) |
        (FinancialTransaction.from_account_id == account_id)
    ).all()

    balance = Decimal("0.00")

    for transaction in transactions:

        amount = money(transaction.amount)

        if transaction.to_account_id == account_id:
            balance += amount

        if transaction.from_account_id == account_id:
            balance -= amount

    return balance


def generate_purchase_number():

    today = datetime.now().strftime("%y%m%d")
    prefix = f"PUR-{today}-"

    latest = (
        Purchase.query
        .filter(Purchase.purchase_number.like(f"{prefix}%"))
        .order_by(Purchase.id.desc())
        .first()
    )

    if not latest:
        sequence = 1
    else:
        try:
            sequence = int(
                latest.purchase_number.split("-")[-1]
            ) + 1
        except (ValueError, IndexError):
            sequence = latest.id + 1

    return f"{prefix}{sequence:04d}"


def generate_supplier_order_number():

    today = datetime.now().strftime("%y%m%d")
    prefix = f"ORD-{today}-"

    latest = (
        SupplierOrder.query
        .filter(SupplierOrder.order_number.like(f"{prefix}%"))
        .order_by(SupplierOrder.id.desc())
        .first()
    )

    if not latest:
        sequence = 1
    else:
        try:
            sequence = int(
                latest.order_number.split("-")[-1]
            ) + 1
        except (ValueError, IndexError):
            sequence = latest.id + 1

    return f"{prefix}{sequence:04d}"


# ============================================================
# PURCHASES PAGE
# ============================================================

@purchases.route("/")
@login_required
def index():

    purchases_list = (
        Purchase.query
        .order_by(
            Purchase.purchase_date.desc(),
            Purchase.id.desc()
        )
        .limit(50)
        .all()
    )

    supplier_orders = (
        SupplierOrder.query
        .order_by(
            SupplierOrder.order_date.desc(),
            SupplierOrder.id.desc()
        )
        .limit(50)
        .all()
    )from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from flask_login import login_required, current_user

from app import db
from app.models import (
    Purchase,
    PurchaseItem,
    Product,
    StockLocation,
    StockHolding,
    StockMovement,
    MoneyAccount,
    FinancialTransaction,
    PartnerTransaction,
    SupplierOrder,
    SupplierOrderCost,
    User
)


purchases = Blueprint(
    "purchases",
    __name__,
    url_prefix="/purchases"
)


# ============================================================
# HELPERS
# ============================================================

def money(value):
    return Decimal(str(value or 0))


def parse_amount(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None

    return amount


def parse_datetime_local(value):
    if not value:
        return datetime.utcnow()

    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def get_account_balance(account_id):

    transactions = FinancialTransaction.query.filter(
        (FinancialTransaction.to_account_id == account_id) |
        (FinancialTransaction.from_account_id == account_id)
    ).all()

    balance = Decimal("0.00")

    for transaction in transactions:

        amount = money(transaction.amount)

        if transaction.to_account_id == account_id:
            balance += amount

        if transaction.from_account_id == account_id:
            balance -= amount

    return balance


def generate_purchase_number():

    today = datetime.now().strftime("%y%m%d")
    prefix = f"PUR-{today}-"

    latest = (
        Purchase.query
        .filter(Purchase.purchase_number.like(f"{prefix}%"))
        .order_by(Purchase.id.desc())
        .first()
    )

    if not latest:
        sequence = 1
    else:
        try:
            sequence = int(
                latest.purchase_number.split("-")[-1]
            ) + 1
        except (ValueError, IndexError):
            sequence = latest.id + 1

    return f"{prefix}{sequence:04d}"


def generate_supplier_order_number():

    today = datetime.now().strftime("%y%m%d")
    prefix = f"ORD-{today}-"

    latest = (
        SupplierOrder.query
        .filter(SupplierOrder.order_number.like(f"{prefix}%"))
        .order_by(SupplierOrder.id.desc())
        .first()
    )

    if not latest:
        sequence = 1
    else:
        try:
            sequence = int(
                latest.order_number.split("-")[-1]
            ) + 1
        except (ValueError, IndexError):
            sequence = latest.id + 1

    return f"{prefix}{sequence:04d}"


# ============================================================
# PURCHASES PAGE
# ============================================================

@purchases.route("/")
@login_required
def index():

    purchases_list = (
        Purchase.query
        .order_by(
            Purchase.purchase_date.desc(),
            Purchase.id.desc()
        )
        .limit(50)
        .all()
    )

    supplier_orders = (
        SupplierOrder.query
        .order_by(
            SupplierOrder.order_date.desc(),
            SupplierOrder.id.desc()
        )
        .limit(50)
        .all()
    )
