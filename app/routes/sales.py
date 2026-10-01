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
    Sale,
    SaleItem,
    Product,
    StockHolding,
    StockLocation,
    StockMovement,
    MoneyAccount,
    FinancialTransaction
)


sales = Blueprint(
    "sales",
    __name__,
    url_prefix="/sales"
)


# ============================================================
# HELPERS
# ============================================================

def generate_sale_number():
    """
    Generate a readable unique sale number.

    Example:
    TDM-260925-0001
    """

    today = datetime.utcnow()

    prefix = f"TDM-{today.strftime('%y%m%d')}"

    latest_sale = (
        Sale.query
        .filter(Sale.sale_number.like(f"{prefix}-%"))
        .order_by(Sale.id.desc())
        .first()
    )

    sequence = 1

    if latest_sale:
        try:
            sequence = int(
                latest_sale.sale_number.split("-")[-1]
            ) + 1
        except (ValueError, IndexError):
            sequence = latest_sale.id + 1

    return f"{prefix}-{sequence:04d}"


# ============================================================
# SALES PAGE
# ============================================================

@sales.route("/")
@login_required
def index():

    recent_sales = (
        Sale.query
        .order_by(
            Sale.sale_date.desc(),
            Sale.id.desc()
        )
        .limit(25)
        .all()
    )

    today = datetime.utcnow().date()

    today_sales = [
        sale
        for sale in recent_sales
        if sale.sale_date.date() == today
        and sale.status == "completed"
    ]

    today_revenue = sum(
        (
            Decimal(str(sale.total_amount))
            for sale in today_sales
        ),
        Decimal("0.00")
    )

    return render_template(
        "sales/index.html",
        recent_sales=recent_sales,
        today_revenue=today_revenue,
        today_sale_count=len(today_sales)
    )


# ============================================================
# NEW SALE
# ============================================================

@sales.route("/new", methods=["GET", "POST"])
@login_required
def new_sale():

    products = (
        Product.query
        .filter(
            Product.is_active.is_(True),
            Product.quantity > 0
        )
        .order_by(Product.name.asc())
        .all()
    )

    money_accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name.asc())
        .all()
    )

    stock_locations = (
        StockLocation.query
        .filter_by(is_active=True)
        .order_by(StockLocation.name.asc())
        .all()
    )


    # --------------------------------------------------------
    # Display form
    # --------------------------------------------------------

    if request.method == "GET":

        holdings = (
            StockHolding.query
            .filter(StockHolding.quantity > 0)
            .all()
        )

        return render_template(
            "sales/new.html",
            products=products,
            money_accounts=money_accounts,
            stock_locations=stock_locations,
            holdings=holdings
        )


    # --------------------------------------------------------
    # Read submitted sale
    # --------------------------------------------------------

    product_id = request.form.get(
        "product_id",
        type=int
    )

    stock_location_id = request.form.get(
        "stock_location_id",
        type=int
    )

    money_account_id = request.form.get(
        "money_account_id",
        type=int
    )

    quantity = request.form.get(
        "quantity",
        type=int
    )

    payment_method = request.form.get(
        "payment_method",
        ""
    ).strip()

    unit_price_raw = request.form.get(
        "unit_price",
        ""
    ).strip()

    notes = request.form.get(
        "notes",
        ""
    ).strip()


    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not all([
        product_id,
        stock_location_id,
        money_account_id,
        quantity,
        payment_method
    ]):
        flash(
            "Complete all required sale information.",
            "error"
        )
        return redirect(url_for("sales.new_sale"))

    if quantity <= 0:
        flash(
            "Sale quantity must be at least 1.",
            "error"
        )
        return redirect(url_for("sales.new_sale"))


    product = db.session.get(
        Product,
        product_id
    )

    stock_location = db.session.get(
        StockLocation,
        stock_location_id
    )

    money_account = db.session.get(
        MoneyAccount,
        money_account_id
    )


    if not product or not product.is_active:
        flash(
            "The selected product is unavailable.",
            "error"
        )
        return redirect(url_for("sales.new_sale"))

    if not stock_location or not stock_location.is_active:
        flash(
            "The selected stock location is unavailable.",
            "error"
        )
        return redirect(url_for("sales.new_sale"))

    if not money_account or not money_account.is_active:
        flash(
            "The selected money location is unavailable.",
            "error"
        )
        return redirect(url_for("sales.new_sale"))


    # --------------------------------------------------------
    # Check stock at the physical location
    # --------------------------------------------------------

    holding = StockHolding.query.filter_by(
        product_id=product.id,
        stock_location_id=stock_location.id
    ).first()

    if not holding or holding.quantity < quantity:

        available = (
            holding.quantity
            if holding
            else 0
        )

        flash(
            f"Only {available} × {product.name} available "
            f"at {stock_location.name}.",
            "error"
        )

        return redirect(url_for("sales.new_sale"))


    # --------------------------------------------------------
    # Sale price
    # --------------------------------------------------------

    if unit_price_raw:

        try:
            unit_price = Decimal(
                unit_price_raw
            ).quantize(
                Decimal("0.01")
            )

        except (InvalidOperation, ValueError):

            flash(
                "Enter a valid selling price.",
                "error"
            )

            return redirect(url_for("sales.new_sale"))

    else:

        unit_price = Decimal(
            str(product.selling_price)
        )


    if unit_price <= Decimal("0.00"):

        flash(
            "Selling price must be greater than R0.00.",
            "error"
        )

        return redirect(url_for("sales.new_sale"))


    cost_price = Decimal(
        str(product.cost_price)
    )

    line_total = (
        unit_price * quantity
    ).quantize(
        Decimal("0.01")
    )


    # --------------------------------------------------------
    # Create everything as ONE database transaction
    # --------------------------------------------------------

    try:

        sale = Sale(
            sale_number=generate_sale_number(),
            total_amount=line_total,
            payment_method=payment_method,
            money_account_id=money_account.id,
            sold_by_id=current_user.id,
            status="completed",
            notes=notes or None,
            sale_date=datetime.utcnow()
        )

        db.session.add(sale)

        db.session.flush()


        # ----------------------------------------------------
        # Sale item
        # ----------------------------------------------------

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=unit_price,
            cost_price=cost_price,
            line_total=line_total,
            stock_location_id=stock_location.id
        )

        db.session.add(sale_item)


        # ----------------------------------------------------
        # Reduce physical stock
        # ----------------------------------------------------

        holding.quantity -= quantity

        product.quantity -= quantity


        # ----------------------------------------------------
        # Permanent stock history
        # ----------------------------------------------------

        stock_movement = StockMovement(
            product_id=product.id,
            movement_type="sale",
            quantity=quantity,
            unit_cost=cost_price,
            from_location_id=stock_location.id,
            to_location_id=None,
            reference=sale.sale_number,
            notes=f"Sold by {current_user.name}",
            movement_date=sale.sale_date,
            created_by_id=current_user.id
        )

        db.session.add(stock_movement)


        # ----------------------------------------------------
        # Financial ledger
        # ----------------------------------------------------

        financial_transaction = FinancialTransaction(
            transaction_type="sale",
            amount=line_total,
            from_account_id=None,
            to_account_id=money_account.id,
            description=(
                f"Sale {sale.sale_number} — "
                f"{quantity} × {product.name}"
            ),
            reference=sale.sale_number,
            transaction_date=sale.sale_date,
            source_type="sale",
            source_id=sale.id,
            notes=notes or None,
            created_by_id=current_user.id
        )

        db.session.add(financial_transaction)


        # ----------------------------------------------------
        # Commit EVERYTHING together
        # ----------------------------------------------------

        db.session.commit()


    except Exception:

        db.session.rollback()

        flash(
            "The sale could not be recorded. "
            "No stock or money was changed.",
            "error"
        )

        return redirect(
            url_for("sales.new_sale")
        )


    flash(
        f"Sale {sale.sale_number} recorded — "
        f"R{line_total:.2f}.",
        "success"
    )

    return redirect(
        url_for("sales.index")
    )


# ============================================================
# TEMPORARY DEMO SALE CLEANUP
# ============================================================

@sales.route("/cleanup-demo-sale", methods=["POST"])
@login_required
def cleanup_demo_sale():
    """
    TEMPORARY commissioning tool.

    Removes the known R350 demo sale made before TYDAL went live
    and restores the stock that the demo sale deducted.

    Remove this route after it has been used successfully.
    """

    if current_user.role != "admin":
        flash(
            "Only an administrator can perform setup cleanup.",
            "error"
        )
        return redirect(url_for("sales.index"))


    # --------------------------------------------------------
    # Find candidate R350 completed sales.
    #
    # We deliberately refuse to continue unless EXACTLY ONE
    # exists. This prevents us from accidentally deleting a
    # genuine R350 sale.
    # --------------------------------------------------------

    demo_sales = (
        Sale.query
        .filter(
            Sale.status == "completed",
            Sale.total_amount == Decimal("350.00")
        )
        .all()
    )


    if len(demo_sales) == 0:
        flash(
            "No R350 demo sale was found. Nothing was changed.",
            "error"
        )
        return redirect(url_for("sales.index"))


    if len(demo_sales) > 1:
        flash(
            "More than one R350 sale exists. Cleanup stopped "
            "to protect real business data.",
            "error"
        )
        return redirect(url_for("sales.index"))


    sale = demo_sales[0]


    try:

        sale_items = (
            SaleItem.query
            .filter_by(sale_id=sale.id)
            .all()
        )


        # ----------------------------------------------------
        # Restore stock deducted by the demo sale
        # ----------------------------------------------------

        for item in sale_items:

            product = db.session.get(
                Product,
                item.product_id
            )

            holding = StockHolding.query.filter_by(
                product_id=item.product_id,
                stock_location_id=item.stock_location_id
            ).first()


            if not product or not holding:
                raise RuntimeError(
                    "Could not safely restore the demo stock."
                )


            product.quantity += item.quantity
            holding.quantity += item.quantity


        # ----------------------------------------------------
        # Delete ledger entry created by this sale
        # ----------------------------------------------------

        FinancialTransaction.query.filter_by(
            source_type="sale",
            source_id=sale.id
        ).delete(
            synchronize_session=False
        )


        # ----------------------------------------------------
        # Delete stock movement created by this sale
        # ----------------------------------------------------

        StockMovement.query.filter_by(
            movement_type="sale",
            reference=sale.sale_number
        ).delete(
            synchronize_session=False
        )


        # ----------------------------------------------------
        # Delete sale items
        # ----------------------------------------------------

        SaleItem.query.filter_by(
            sale_id=sale.id
        ).delete(
            synchronize_session=False
        )


        # ----------------------------------------------------
        # Finally delete sale itself
        # ----------------------------------------------------

        db.session.delete(sale)


        db.session.commit()


    except Exception:

        db.session.rollback()

        flash(
            "Demo cleanup stopped. No changes were committed.",
            "error"
        )

        return redirect(url_for("sales.index"))


    flash(
        "Demo R350 sale removed successfully. "
        "Its stock and money effects were restored.",
        "success"
    )

    return redirect(url_for("sales.index"))