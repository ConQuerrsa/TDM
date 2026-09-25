from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    User,
    MoneyAccount,
    StockLocation,
    BusinessSettings,
    Product,
    StockHolding,
    StockMovement,
    PartnerTransaction,
    FinancialTransaction,
)


setup = Blueprint("setup", __name__, url_prefix="/setup")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def historical_datetime(value):
    """
    Convert an optional HTML date field into a datetime.

    If no date is supplied, use today.
    """
    if not value:
        return datetime.utcnow()

    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return datetime.utcnow()


def redirect_setup():
    return redirect(url_for("setup.index"))


# ---------------------------------------------------------
# Setup dashboard
# ---------------------------------------------------------

@setup.route("/")
@login_required
def index():

    partners = (
        User.query
        .order_by(User.name)
        .all()
    )

    money_accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name)
        .all()
    )

    stock_locations = (
        StockLocation.query
        .filter_by(is_active=True)
        .order_by(StockLocation.name)
        .all()
    )

    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.name)
        .all()
    )

    return render_template(
        "setup/index.html",
        partners=partners,
        money_accounts=money_accounts,
        stock_locations=stock_locations,
        products=products,
    )


# ---------------------------------------------------------
# Add partner
# ---------------------------------------------------------

@setup.route("/partner", methods=["POST"])
@login_required
def add_partner():

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    role = request.form.get("role", "partner").strip() or "partner"

    if not name or not phone:
        flash("Partner name and phone number are required.", "error")
        return redirect_setup()

    if User.query.filter_by(phone=phone).first():
        flash("A user with that phone number already exists.", "error")
        return redirect_setup()

    # Temporary generated password.
    # We will build proper password setup/reset later.
    temporary_password = "TDM-" + phone[-4:]

    user = User(
        name=name,
        phone=phone,
        password_hash=generate_password_hash(temporary_password),
        role=role,
        is_active=True,
    )

    db.session.add(user)
    db.session.commit()

    flash(
        f"{name} was added. Temporary password: {temporary_password}",
        "success"
    )

    return redirect_setup()


# ---------------------------------------------------------
# Add money location
# ---------------------------------------------------------

@setup.route("/money-account", methods=["POST"])
@login_required
def add_money_account():

    name = request.form.get("name", "").strip()
    account_type = request.form.get("account_type", "").strip()
    owner_id = request.form.get("owner_user_id") or None

    opening_balance = money(
        request.form.get("opening_balance")
    )

    transaction_date = historical_datetime(
        request.form.get("transaction_date")
    )

    is_estimate = (
        request.form.get("is_estimate") == "on"
    )

    notes = request.form.get("notes", "").strip() or None

    if not name or not account_type:
        flash(
            "Money location name and type are required.",
            "error"
        )
        return redirect_setup()

    try:
        owner_id = int(owner_id) if owner_id else None
    except ValueError:
        owner_id = None

    account = MoneyAccount(
        name=name,
        account_type=account_type,
        owner_user_id=owner_id,
        opening_balance=Decimal("0.00"),
    )

    db.session.add(account)
    db.session.flush()

    # Opening money is represented by the ledger.
    if opening_balance > 0:

        ledger = FinancialTransaction(
            transaction_type="opening_balance",
            amount=opening_balance,
            to_account_id=account.id,
            description=f"Opening balance — {name}",
            transaction_date=transaction_date,
            is_historical=True,
            is_estimate=is_estimate,
            source_type="opening_balance",
            source_id=account.id,
            notes=notes,
            created_by_id=current_user.id,
        )

        db.session.add(ledger)

    db.session.commit()

    flash(
        f"{name} was added to TYDAL.",
        "success"
    )

    return redirect_setup()


# ---------------------------------------------------------
# Add stock location
# ---------------------------------------------------------

@setup.route("/stock-location", methods=["POST"])
@login_required
def add_stock_location():

    name = request.form.get("name", "").strip()
    location_type = (
        request.form.get("location_type", "partner").strip()
        or "partner"
    )

    owner_id = request.form.get("owner_user_id") or None

    if not name:
        flash(
            "Stock location name is required.",
            "error"
        )
        return redirect_setup()

    try:
        owner_id = int(owner_id) if owner_id else None
    except ValueError:
        owner_id = None

    location = StockLocation(
        name=name,
        location_type=location_type,
        owner_user_id=owner_id,
    )

    db.session.add(location)
    db.session.commit()

    flash(
        f"{name} was added as a stock location.",
        "success"
    )

    return redirect_setup()


# ---------------------------------------------------------
# Add opening product / stock
# ---------------------------------------------------------

@setup.route("/product", methods=["POST"])
@login_required
def add_product():

    name = request.form.get("name", "").strip()
    brand = request.form.get("brand", "").strip() or None
    category = request.form.get("category", "").strip() or None
    size = request.form.get("size", "").strip() or None
    color = request.form.get("color", "").strip() or None

    cost_price = money(
        request.form.get("cost_price")
    )

    selling_price = money(
        request.form.get("selling_price")
    )

    try:
        quantity = int(
            request.form.get("quantity") or 0
        )
    except ValueError:
        quantity = 0

    try:
        low_stock_level = int(
            request.form.get("low_stock_level") or 2
        )
    except ValueError:
        low_stock_level = 2

    supplier = (
        request.form.get("supplier", "").strip()
        or None
    )

    location_id = request.form.get(
        "stock_location_id"
    )

    transaction_date = historical_datetime(
        request.form.get("transaction_date")
    )

    is_estimate = (
        request.form.get("is_estimate") == "on"
    )

    notes = (
        request.form.get("notes", "").strip()
        or "Opening stock entered during TYDAL setup."
    )

    if not name:
        flash(
            "Product name is required.",
            "error"
        )
        return redirect_setup()

    if quantity < 0:
        flash(
            "Stock quantity cannot be negative.",
            "error"
        )
        return redirect_setup()

    if cost_price < 0 or selling_price < 0:
        flash(
            "Prices cannot be negative.",
            "error"
        )
        return redirect_setup()

    if quantity > 0 and not location_id:
        flash(
            "Choose where the opening stock is physically located.",
            "error"
        )
        return redirect_setup()

    if location_id:

        try:
            location_id = int(location_id)
        except ValueError:
            flash(
                "Invalid stock location.",
                "error"
            )
            return redirect_setup()

        location = db.session.get(
            StockLocation,
            location_id
        )

        if not location:
            flash(
                "The selected stock location does not exist.",
                "error"
            )
            return redirect_setup()

    product = Product(
        name=name,
        brand=brand,
        category=category,
        size=size,
        color=color,
        cost_price=cost_price,
        selling_price=selling_price,
        quantity=quantity,
        low_stock_level=low_stock_level,
        supplier=supplier,
    )

    db.session.add(product)
    db.session.flush()

    if quantity > 0:

        holding = StockHolding(
            product_id=product.id,
            stock_location_id=location_id,
            quantity=quantity,
        )

        movement = StockMovement(
            product_id=product.id,
            movement_type="opening",
            quantity=quantity,
            unit_cost=cost_price,
            to_location_id=location_id,
            reference="OPENING",
            notes=notes,
            movement_date=transaction_date,
            is_historical=True,
            is_estimate=is_estimate,
            created_by_id=current_user.id,
        )

        db.session.add(holding)
        db.session.add(movement)

    db.session.commit()

    flash(
        f"{name} was added to TYDAL inventory.",
        "success"
    )

    return redirect_setup()

@setup.route("/complete", methods=["POST"])
@login_required
def complete_setup():
    # Only admins should be able to finalize TYDAL's opening setup.
    if current_user.role != "admin":
        flash("Only an administrator can complete business setup.", "error")
        return redirect(url_for("setup.index"))

    settings = BusinessSettings.query.first()

    if settings is None:
        settings = BusinessSettings(
            business_name="TYDAL"
        )
        db.session.add(settings)

    if settings.setup_completed:
        flash("TYDAL business setup has already been completed.", "info")
        return redirect(url_for("main.home"))

    settings.setup_completed = True
    settings.setup_completed_at = datetime.utcnow()
    settings.setup_completed_by_id = current_user.id

    db.session.commit()

    flash(
        "TYDAL business setup has been completed successfully.",
        "success"
    )

    return redirect(url_for("main.home"))


# ---------------------------------------------------------
# Partner transaction
# ---------------------------------------------------------

@setup.route("/partner-transaction", methods=["POST"])
@login_required
def add_partner_transaction():

    partner_id = request.form.get("partner_id")
    transaction_type = (
        request.form.get("transaction_type", "")
        .strip()
    )

    amount = money(
        request.form.get("amount")
    )

    money_account_id = request.form.get(
        "money_account_id"
    )

    description = (
        request.form.get("description", "").strip()
        or None
    )

    transaction_date = historical_datetime(
        request.form.get("transaction_date")
    )

    is_estimate = (
        request.form.get("is_estimate") == "on"
    )

    notes = (
        request.form.get("notes", "").strip()
        or None
    )

    if not partner_id:
        flash(
            "Choose a partner.",
            "error"
        )
        return redirect_setup()

    if amount <= 0:
        flash(
            "Enter a valid amount greater than zero.",
            "error"
        )
        return redirect_setup()

    allowed_types = {
        "contribution",
        "advance",
        "withdrawal",
        "personal_expense",
        "repayment",
    }

    if transaction_type not in allowed_types:
        flash(
            "Invalid partner transaction type.",
            "error"
        )
        return redirect_setup()

    try:
        partner_id = int(partner_id)
    except ValueError:
        flash(
            "Invalid partner.",
            "error"
        )
        return redirect_setup()

    partner = db.session.get(
        User,
        partner_id
    )

    if not partner:
        flash(
            "Partner not found.",
            "error"
        )
        return redirect_setup()

    if money_account_id:

        try:
            money_account_id = int(
                money_account_id
            )
        except ValueError:
            money_account_id = None

    # A real money movement requires a location.
    # Personal expense is different: the partner paid
    # personally, so TYDAL cash does not move.
    if (
        transaction_type in {
            "contribution",
            "advance",
            "withdrawal",
            "repayment",
        }
        and not money_account_id
    ):
        flash(
            "Choose the TYDAL money location involved.",
            "error"
        )
        return redirect_setup()

    repayment_expected = (
        transaction_type in {
            "advance",
            "withdrawal",
        }
    )

    partner_transaction = PartnerTransaction(
        partner_id=partner_id,
        transaction_type=transaction_type,
        amount=amount,
        money_account_id=money_account_id,
        description=description,
        repayment_expected=repayment_expected,
        transaction_date=transaction_date,
        is_historical=True,
        is_estimate=is_estimate,
        notes=notes,
    )

    db.session.add(partner_transaction)
    db.session.flush()

    # -----------------------------------------------------
    # Contribution
    # Partner helps TYDAL. No repayment expected.
    # -----------------------------------------------------

    if transaction_type == "contribution":

        ledger = FinancialTransaction(
            transaction_type="partner_contribution",
            amount=amount,
            to_account_id=money_account_id,
            description=(
                description
                or f"Contribution from {partner.name}"
            ),
            transaction_date=transaction_date,
            is_historical=True,
            is_estimate=is_estimate,
            source_type="partner_transaction",
            source_id=partner_transaction.id,
            notes=notes,
            created_by_id=current_user.id,
        )

        db.session.add(ledger)

    # -----------------------------------------------------
    # Advance
    # Partner gives TYDAL money which TYDAL owes back.
    # -----------------------------------------------------

    elif transaction_type == "advance":

        ledger = FinancialTransaction(
            transaction_type="partner_advance",
            amount=amount,
            to_account_id=money_account_id,
            description=(
                description
                or f"Advance from {partner.name}"
            ),
            transaction_date=transaction_date,
            is_historical=True,
            is_estimate=is_estimate,
            source_type="partner_transaction",
            source_id=partner_transaction.id,
            notes=notes,
            created_by_id=current_user.id,
        )

        db.session.add(ledger)

    # -----------------------------------------------------
    # Withdrawal
    # Partner takes TYDAL money.
    # -----------------------------------------------------

    elif transaction_type == "withdrawal":

        ledger = FinancialTransaction(
            transaction_type="partner_withdrawal",
            amount=amount,
            from_account_id=money_account_id,
            description=(
                description
                or f"Withdrawal by {partner.name}"
            ),
            transaction_date=transaction_date,
            is_historical=True,
            is_estimate=is_estimate,
            source_type="partner_transaction",
            source_id=partner_transaction.id,
            notes=notes,
            created_by_id=current_user.id,
        )

        db.session.add(ledger)

    # -----------------------------------------------------
    # Repayment
    # Partner returns money to TYDAL.
    # -----------------------------------------------------

    elif transaction_type == "repayment":

        ledger = FinancialTransaction(
            transaction_type="partner_repayment",
            amount=amount,
            to_account_id=money_account_id,
            description=(
                description
                or f"Repayment from {partner.name}"
            ),
            transaction_date=transaction_date,
            is_historical=True,
            is_estimate=is_estimate,
            source_type="partner_transaction",
            source_id=partner_transaction.id,
            notes=notes,
            created_by_id=current_user.id,
        )

        db.session.add(ledger)

    # -----------------------------------------------------
    # Personal business expense
    #
    # Partner paid a legitimate TYDAL expense personally.
    # TYDAL cash does NOT increase or decrease here.
    # The partner transaction itself records the amount.
    # -----------------------------------------------------

    elif transaction_type == "personal_expense":

        # No financial account movement.
        # The expense module will later connect these
        # records to proper expense categories.
        pass

    db.session.commit()

    flash(
        f"Partner transaction for {partner.name} recorded.",
        "success"
    )

    return redirect_setup()