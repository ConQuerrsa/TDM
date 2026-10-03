from decimal import Decimal
from datetime import datetime

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
    """Inventory grouped as product families with size/colour variants.

    v1.0 stored every size/colour row as a separate Product.  We keep those
    records intact because sales, stock movements and holdings already point
    to them, but present rows with the same name/brand/category as one product
    family.  This gives TYDAL the correct retail view without rewriting live
    history or breaking foreign keys.
    """

    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.name.asc(), Product.id.asc())
        .all()
    )

    locations = (
        StockLocation.query
        .filter_by(is_active=True)
        .order_by(StockLocation.name.asc())
        .all()
    )

    def clean(value):
        return (value or "").strip()

    def family_key(product):
        return (
            clean(product.name).casefold(),
            clean(product.brand).casefold(),
            clean(product.category).casefold(),
        )

    families = {}
    move_options = []

    total_units = 0
    total_cost_value = Decimal("0.00")
    total_retail_value = Decimal("0.00")

    for product in products:
        holdings = (
            StockHolding.query
            .filter_by(product_id=product.id)
            .filter(StockHolding.quantity > 0)
            .all()
        )

        holding_rows = [
            {"holding": holding, "location": holding.stock_location}
            for holding in holdings
        ]
        holding_total = sum(holding.quantity for holding in holdings)
        quantity = int(product.quantity or 0)
        cost_price = Decimal(str(product.cost_price or 0))
        selling_price = Decimal(str(product.selling_price or 0))
        cost_value = (cost_price * quantity).quantize(Decimal("0.01"))
        retail_value = (selling_price * quantity).quantize(Decimal("0.01"))

        first_in = (
            StockMovement.query
            .filter(
                StockMovement.product_id == product.id,
                StockMovement.to_location_id.isnot(None),
            )
            .order_by(StockMovement.movement_date.asc(), StockMovement.id.asc())
            .first()
        )
        stocked_at = first_in.movement_date if first_in else product.created_at
        age_days = max(0, (datetime.utcnow() - stocked_at).days) if stocked_at else 0

        variant = {
            "product": product,
            "size": clean(product.size),
            "color": clean(product.color),
            "quantity": quantity,
            "cost_price": cost_price,
            "selling_price": selling_price,
            "cost_value": cost_value,
            "retail_value": retail_value,
            "holdings": holding_rows,
            "holding_total": holding_total,
            "stock_mismatch": holding_total != quantity,
            "age_days": age_days,
            "stocked_at": stocked_at,
        }

        key = family_key(product)
        family = families.setdefault(key, {
            "name": clean(product.name),
            "brand": clean(product.brand),
            "category": clean(product.category),
            "variants": [],
            "quantity": 0,
            "cost_value": Decimal("0.00"),
            "retail_value": Decimal("0.00"),
            "low_stock_level": int(product.low_stock_level or 0),
            "oldest_age_days": 0,
        })
        family["variants"].append(variant)
        family["quantity"] += quantity
        family["cost_value"] += cost_value
        family["retail_value"] += retail_value
        family["low_stock_level"] = max(
            family["low_stock_level"], int(product.low_stock_level or 0)
        )
        family["oldest_age_days"] = max(family["oldest_age_days"], age_days)

        total_units += quantity
        total_cost_value += cost_value
        total_retail_value += retail_value

        if quantity > 0:
            label_bits = [clean(product.name)]
            details = [x for x in (clean(product.size), clean(product.color)) if x]
            if details:
                label_bits.append(" · ".join(details))
            move_options.append({
                "product": product,
                "label": " — ".join(label_bits),
                "quantity": quantity,
            })

    product_rows = []
    low_stock_count = 0
    sold_out_count = 0

    for family in families.values():
        family["variants"].sort(
            key=lambda v: (v["size"].casefold(), v["color"].casefold(), v["product"].id)
        )
        if family["quantity"] == 0:
            family["stock_status"] = "sold_out"
            sold_out_count += 1
        elif family["quantity"] <= family["low_stock_level"]:
            family["stock_status"] = "low"
            low_stock_count += 1
        else:
            family["stock_status"] = "healthy"
        product_rows.append(family)

    product_rows.sort(key=lambda row: (row["name"].casefold(), row["brand"].casefold()))
    stock_attention_count = low_stock_count + sold_out_count

    recent_movements = (
        StockMovement.query
        .order_by(StockMovement.movement_date.desc(), StockMovement.id.desc())
        .limit(15)
        .all()
    )

    return render_template(
        "inventory/index.html",
        product_rows=product_rows,
        move_options=move_options,
        locations=locations,
        total_units=total_units,
        total_cost_value=total_cost_value,
        total_retail_value=total_retail_value,
        low_stock_count=low_stock_count,
        sold_out_count=sold_out_count,
        stock_attention_count=stock_attention_count,
        recent_movements=recent_movements,
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