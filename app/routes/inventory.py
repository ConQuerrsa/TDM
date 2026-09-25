from decimal import Decimal

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
    Product,
    StockHolding,
    StockLocation,
    StockMovement
)


inventory = Blueprint(
    "inventory",
    __name__,
    url_prefix="/inventory"
)


# ============================================================
# INVENTORY DASHBOARD
# ============================================================

@inventory.route("/")
@login_required
def index():

    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.name.asc())
        .all()
    )

    locations = (
        StockLocation.query
        .filter_by(is_active=True)
        .order_by(StockLocation.name.asc())
        .all()
    )

    product_rows = []

    total_units = 0
    total_cost_value = Decimal("0.00")
    total_retail_value = Decimal("0.00")
    low_stock_count = 0

    for product in products:

        holdings = (
            StockHolding.query
            .filter_by(product_id=product.id)
            .filter(StockHolding.quantity > 0)
            .all()
        )

        holding_rows = []

        holding_total = 0

        for holding in holdings:

            holding_total += holding.quantity

            holding_rows.append({
                "holding": holding,
                "location": holding.stock_location
            })

        quantity = int(product.quantity or 0)

        cost_price = Decimal(
            str(product.cost_price or 0)
        )

        selling_price = Decimal(
            str(product.selling_price or 0)
        )

        cost_value = (
            cost_price * quantity
        ).quantize(
            Decimal("0.01")
        )

        retail_value = (
            selling_price * quantity
        ).quantize(
            Decimal("0.01")
        )

        low_stock = (
            quantity <= product.low_stock_level
        )

        if low_stock:
            low_stock_count += 1

        total_units += quantity
        total_cost_value += cost_value
        total_retail_value += retail_value

        product_rows.append({
            "product": product,
            "holdings": holding_rows,
            "holding_total": holding_total,
            "cost_value": cost_value,
            "retail_value": retail_value,
            "low_stock": low_stock,
            "stock_mismatch": holding_total != quantity
        })


    recent_movements = (
        StockMovement.query
        .order_by(
            StockMovement.movement_date.desc(),
            StockMovement.id.desc()
        )
        .limit(15)
        .all()
    )


    return render_template(
        "inventory/index.html",
        product_rows=product_rows,
        locations=locations,
        total_units=total_units,
        total_cost_value=total_cost_value,
        total_retail_value=total_retail_value,
        low_stock_count=low_stock_count,
        recent_movements=recent_movements
    )


# ============================================================
# MOVE STOCK
# ============================================================

@inventory.route("/move", methods=["POST"])
@login_required
def move_stock():

    product_id = request.form.get(
        "product_id",
        type=int
    )

    from_location_id = request.form.get(
        "from_location_id",
        type=int
    )

    to_location_id = request.form.get(
        "to_location_id",
        type=int
    )

    quantity = request.form.get(
        "quantity",
        type=int
    )

    notes = request.form.get(
        "notes",
        ""
    ).strip()


    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not all([
        product_id,
        from_location_id,
        to_location_id,
        quantity
    ]):
        flash(
            "Complete all stock transfer information.",
            "error"
        )
        return redirect(url_for("inventory.index"))


    if quantity <= 0:
        flash(
            "Stock transfer quantity must be at least 1.",
            "error"
        )
        return redirect(url_for("inventory.index"))


    if from_location_id == to_location_id:
        flash(
            "Stock cannot be moved to the same location.",
            "error"
        )
        return redirect(url_for("inventory.index"))


    # --------------------------------------------------------
    # Load records
    # --------------------------------------------------------

    product = db.session.get(
        Product,
        product_id
    )

    from_location = db.session.get(
        StockLocation,
        from_location_id
    )

    to_location = db.session.get(
        StockLocation,
        to_location_id
    )


    if not product or not product.is_active:
        flash(
            "The selected product is unavailable.",
            "error"
        )
        return redirect(url_for("inventory.index"))


    if (
        not from_location
        or not from_location.is_active
        or not to_location
        or not to_location.is_active
    ):
        flash(
            "One of the selected stock locations is unavailable.",
            "error"
        )
        return redirect(url_for("inventory.index"))


    # --------------------------------------------------------
    # Find source stock
    # --------------------------------------------------------

    source_holding = (
        StockHolding.query
        .filter_by(
            product_id=product.id,
            stock_location_id=from_location.id
        )
        .first()
    )


    if (
        not source_holding
        or source_holding.quantity < quantity
    ):

        available = (
            source_holding.quantity
            if source_holding
            else 0
        )

        flash(
            f"{from_location.name} only has "
            f"{available} × {product.name}.",
            "error"
        )

        return redirect(url_for("inventory.index"))


    # --------------------------------------------------------
    # Find/create destination holding
    # --------------------------------------------------------

    destination_holding = (
        StockHolding.query
        .filter_by(
            product_id=product.id,
            stock_location_id=to_location.id
        )
        .first()
    )


    try:

        source_holding.quantity -= quantity


        if destination_holding:

            destination_holding.quantity += quantity

        else:

            destination_holding = StockHolding(
                product_id=product.id,
                stock_location_id=to_location.id,
                quantity=quantity
            )

            db.session.add(
                destination_holding
            )


        # ----------------------------------------------------
        # IMPORTANT:
        # Product.quantity DOES NOT change.
        #
        # This is internal stock movement only.
        # ----------------------------------------------------


        movement = StockMovement(
            product_id=product.id,
            movement_type="transfer",
            quantity=quantity,
            unit_cost=product.cost_price,
            from_location_id=from_location.id,
            to_location_id=to_location.id,
            reference=None,
            notes=notes or (
                f"Stock moved from "
                f"{from_location.name} to "
                f"{to_location.name}"
            ),
            created_by_id=current_user.id
        )

        db.session.add(movement)

        db.session.commit()


    except Exception:

        db.session.rollback()

        flash(
            "The stock transfer could not be recorded. "
            "No inventory was changed.",
            "error"
        )

        return redirect(
            url_for("inventory.index")
        )


    flash(
        f"{quantity} × {product.name} moved from "
        f"{from_location.name} to {to_location.name}.",
        "success"
    )

    return redirect(
        url_for("inventory.index")
    )