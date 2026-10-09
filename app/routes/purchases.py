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
from flask_wtf import FlaskForm
from app.services.supplier_orders import (lock_order, reverse_cost, receive_order,
    partner_matches, SupplierError)

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

    return amount if amount.is_finite() else None


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

    total_spent = sum(
        (
            money(purchase.total_amount)
            for purchase in purchases_list
            if purchase.status == "completed" and purchase.supplier_receipt is None
        ),
        Decimal("0.00")
    )

    total_orders = len(purchases_list)

    total_units = sum(
        item.quantity
        for purchase in purchases_list
        for item in purchase.items
        if purchase.status == "completed"
    )

    return render_template(
        "purchases/index.html",
        purchases=purchases_list,
        supplier_orders=supplier_orders,
        total_spent=total_spent,
        total_orders=total_orders,
        total_units=total_units
    )


# ============================================================
# NEW RECEIVED PURCHASE
# ============================================================

@purchases.route("/new", methods=["GET", "POST"])
@login_required
def new():

    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.name.asc())
        .all()
    )

    accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name.asc())
        .all()
    )

    locations = (
        StockLocation.query
        .filter_by(is_active=True)
        .order_by(StockLocation.name.asc())
        .all()
    )

    account_rows = [
        {
            "account": account,
            "balance": get_account_balance(account.id)
        }
        for account in accounts
    ]

    if request.method == "POST":

        supplier = request.form.get(
            "supplier",
            ""
        ).strip()

        money_account_id = request.form.get(
            "money_account_id"
        )

        stock_location_id = request.form.get(
            "stock_location_id"
        )

        notes = request.form.get(
            "notes",
            ""
        ).strip()

        # ----------------------------------------------------
        # BASIC VALIDATION
        # ----------------------------------------------------

        if not supplier:
            flash("Supplier is required.", "error")
            return redirect(url_for("purchases.new"))

        try:
            money_account_id = int(money_account_id)
            stock_location_id = int(stock_location_id)

        except (TypeError, ValueError):

            flash(
                "Choose a valid payment account and stock location.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        account = db.session.get(
            MoneyAccount,
            money_account_id
        )

        location = db.session.get(
            StockLocation,
            stock_location_id
        )

        if not account or not account.is_active:

            flash(
                "The selected money location is not available.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        if not location or not location.is_active:

            flash(
                "The selected stock location is not available.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        # ----------------------------------------------------
        # READ PURCHASE ITEMS
        # ----------------------------------------------------

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        unit_costs = request.form.getlist("unit_cost[]")

        new_product_names = request.form.getlist(
            "new_product_name[]"
        )

        new_product_brands = request.form.getlist(
            "new_product_brand[]"
        )

        new_product_categories = request.form.getlist(
            "new_product_category[]"
        )

        new_product_sizes = request.form.getlist(
            "new_product_size[]"
        )

        new_product_colors = request.form.getlist(
            "new_product_color[]"
        )

        new_product_selling_prices = request.form.getlist(
            "new_product_selling_price[]"
        )

        if not product_ids:

            flash(
                "Add at least one product to the purchase.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        if not (
            len(product_ids)
            == len(quantities)
            == len(unit_costs)
        ):

            flash(
                "Purchase item data is incomplete.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        prepared_items = []
        total_amount = Decimal("0.00")

        # ----------------------------------------------------
        # VALIDATE EACH ITEM
        # ----------------------------------------------------

        for index, (product_id, quantity_raw, cost_raw) in enumerate(
            zip(product_ids, quantities, unit_costs)
        ):
            try:
                quantity = int(quantity_raw)
                unit_cost = Decimal(str(cost_raw)).quantize(
                    Decimal("0.01")
                )
            except (TypeError, ValueError, InvalidOperation):
                flash(
                    "One of the purchase items contains invalid values.",
                    "error"
                )
                return redirect(url_for("purchases.new"))

            if quantity <= 0:
                flash(
                    "Purchase quantity must be greater than zero.",
                    "error"
                )
                return redirect(url_for("purchases.new"))

            if unit_cost < 0:
                flash(
                    "Unit cost cannot be negative.",
                    "error"
                )
                return redirect(url_for("purchases.new"))

            if product_id == "__new__":
                try:
                    product_name = new_product_names[index].strip()
                    brand = new_product_brands[index].strip()
                    category = new_product_categories[index].strip()
                    size = new_product_sizes[index].strip()
                    color = new_product_colors[index].strip()
                    selling_price_raw = (
                        new_product_selling_prices[index]
                    )
                except IndexError:
                    flash(
                        "New product information is incomplete.",
                        "error"
                    )
                    return redirect(url_for("purchases.new"))

                if not product_name:
                    flash(
                        "Enter a name for the new product.",
                        "error"
                    )
                    return redirect(url_for("purchases.new"))

                try:
                    selling_price = Decimal(
                        str(selling_price_raw)
                    ).quantize(Decimal("0.01"))
                except (
                    InvalidOperation,
                    TypeError,
                    ValueError
                ):
                    flash(
                        f"Enter a valid selling price for {product_name}.",
                        "error"
                    )
                    return redirect(url_for("purchases.new"))

                if selling_price < 0:
                    flash(
                        "Selling price cannot be negative.",
                        "error"
                    )
                    return redirect(url_for("purchases.new"))

                product = Product(
                    name=product_name,
                    brand=brand or None,
                    category=category or None,
                    size=size or None,
                    color=color or None,
                    cost_price=unit_cost,
                    selling_price=selling_price,
                    quantity=0,
                    supplier=supplier,
                    is_active=True
                )

                db.session.add(product)
                db.session.flush()

            else:
                try:
                    existing_product_id = int(product_id)
                except (TypeError, ValueError):
                    flash(
                        "Choose a valid product.",
                        "error"
                    )
                    return redirect(url_for("purchases.new"))

                product = db.session.get(
                    Product,
                    existing_product_id
                )

                if not product or not product.is_active:
                    flash(
                        "One of the selected products is unavailable.",
                        "error"
                    )
                    return redirect(url_for("purchases.new"))

            line_total = (
                unit_cost * quantity
            ).quantize(Decimal("0.01"))

            total_amount += line_total

            prepared_items.append({
                "product": product,
                "quantity": quantity,
                "unit_cost": unit_cost,
                "line_total": line_total
            })

        total_amount = total_amount.quantize(
            Decimal("0.01")
        )

        if total_amount <= 0:

            flash(
                "Purchase total must be greater than zero.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        # ----------------------------------------------------
        # CHECK TYDAL MONEY
        # ----------------------------------------------------

        available_balance = get_account_balance(
            account.id
        )

        if total_amount > available_balance:

            flash(
                f"Not enough money in {account.name}. "
                f"Available: R{available_balance:.2f}.",
                "error"
            )

            return redirect(url_for("purchases.new"))

        # ----------------------------------------------------
        # SAVE EVERYTHING ATOMICALLY
        # ----------------------------------------------------

        try:

            purchase_date = datetime.utcnow()

            purchase = Purchase(
                purchase_number=generate_purchase_number(),
                supplier=supplier,
                total_amount=total_amount,
                money_account_id=account.id,
                purchased_by_id=current_user.id,
                status="completed",
                purchase_date=purchase_date,
                is_historical=False,
                is_estimate=False,
                notes=notes or None
            )

            db.session.add(purchase)
            db.session.flush()

            # ------------------------------------------------
            # PURCHASE ITEMS + INVENTORY
            # ------------------------------------------------

            for item in prepared_items:

                product = item["product"]
                quantity = item["quantity"]
                unit_cost = item["unit_cost"]
                line_total = item["line_total"]

                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    line_total=line_total
                )

                db.session.add(purchase_item)

                holding = (
                    StockHolding.query
                    .filter_by(
                        product_id=product.id,
                        stock_location_id=location.id
                    )
                    .first()
                )

                if not holding:

                    holding = StockHolding(
                        product_id=product.id,
                        stock_location_id=location.id,
                        quantity=0
                    )

                    db.session.add(holding)

                holding.quantity += quantity
                product.quantity += quantity

                stock_movement = StockMovement(
                    product_id=product.id,
                    movement_type="purchase",
                    quantity=quantity,
                    unit_cost=unit_cost,
                    from_location_id=None,
                    to_location_id=location.id,
                    reference=purchase.purchase_number,
                    notes=f"Purchased from {supplier}",
                    movement_date=purchase_date,
                    is_historical=False,
                    is_estimate=False,
                    created_by_id=current_user.id
                )

                db.session.add(stock_movement)

            # ------------------------------------------------
            # MONEY OUT OF TYDAL
            # ------------------------------------------------

            ledger_transaction = FinancialTransaction(
                transaction_type="purchase",
                amount=total_amount,
                from_account_id=account.id,
                to_account_id=None,
                description=f"Stock purchase from {supplier}",
                reference=purchase.purchase_number,
                transaction_date=purchase_date,
                is_historical=False,
                is_estimate=False,
                source_type="purchase",
                source_id=purchase.id,
                notes=notes or None,
                created_by_id=current_user.id
            )

            db.session.add(ledger_transaction)
            db.session.commit()

        except Exception:

            db.session.rollback()

            flash(
                "Purchase could not be saved. "
                "No money or stock was changed.",
                "error"
            )

            return redirect(
                url_for("purchases.new")
            )

        flash(
            f"{purchase.purchase_number} recorded successfully. "
            f"R{total_amount:.2f} paid to {supplier}.",
            "success"
        )

        return redirect(
            url_for("purchases.index")
        )

    return render_template(
        "purchases/new.html",
        products=products,
        accounts=accounts,
        account_rows=account_rows,
        locations=locations
    )


# ============================================================
# NEW IN-TRANSIT SUPPLIER ORDER
# ============================================================

@purchases.route("/orders/new", methods=["GET", "POST"])
@login_required
def new_supplier_order():

    if request.method == "POST":

        supplier = request.form.get(
            "supplier",
            ""
        ).strip()

        goods_cost = parse_amount(
            request.form.get("goods_cost")
        )

        order_date = parse_datetime_local(
            request.form.get("order_date")
        )

        is_historical = (
            request.form.get("is_historical") == "on"
        )

        notes = request.form.get(
            "notes",
            ""
        ).strip()

        if not supplier:
            flash("Supplier is required.", "error")
            return redirect(
                url_for("purchases.new_supplier_order")
            )

        if goods_cost is None or goods_cost <= 0:
            flash(
                "Enter a valid goods cost greater than zero.",
                "error"
            )
            return redirect(
                url_for("purchases.new_supplier_order")
            )

        if order_date is None:
            flash(
                "Enter a valid order date.",
                "error"
            )
            return redirect(
                url_for("purchases.new_supplier_order")
            )

        try:

            supplier_order = SupplierOrder(
                order_number=generate_supplier_order_number(),
                supplier=supplier,
                goods_cost=goods_cost,
                status="in_transit",
                order_date=order_date,
                is_historical=is_historical,
                notes=notes or None,
                created_by_id=current_user.id
            )

            db.session.add(supplier_order)
            db.session.commit()

        except Exception:

            db.session.rollback()

            flash(
                "Supplier order could not be saved. "
                "No money or inventory was changed.",
                "error"
            )

            return redirect(
                url_for("purchases.new_supplier_order")
            )

        flash(
            f"{supplier_order.order_number} created. "
            "No available stock or current TYDAL money was changed.",
            "success"
        )

        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=supplier_order.id
            )
        )

    return render_template(
        "purchases/order_new.html"
    )


# ============================================================
# SUPPLIER ORDER DETAIL
# ============================================================

@purchases.route("/orders/<int:order_id>")
@login_required
def supplier_order_detail(order_id):

    supplier_order = db.get_or_404(
        SupplierOrder,
        order_id
    )

    accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name.asc())
        .all()
    )

    account_rows = [
        {
            "account": account,
            "balance": get_account_balance(account.id)
        }
        for account in accounts
    ]

    partners = (
        User.query
        .filter_by(is_active=True)
        .order_by(User.name.asc())
        .all()
    )

    return render_template(
        "purchases/order_detail.html",
        supplier_order=supplier_order,
        account_rows=account_rows,
        partners=partners,
        supplier_form=FlaskForm()
    )


# ============================================================
# ADD LANDED COST TO IN-TRANSIT ORDER
# ============================================================

@purchases.route(
    "/orders/<int:order_id>/cost",
    methods=["POST"]
)
@login_required
def add_supplier_order_cost(order_id):

    if not FlaskForm().validate_on_submit():
        return "Invalid or expired form. Reload the order.", 400

    supplier_order = db.get_or_404(
        SupplierOrder,
        order_id
    )

    if supplier_order.status == "received":
        flash(
            "This order has already been received. "
            "Its landed costs are locked.",
            "error"
        )
        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    cost_type = request.form.get(
        "cost_type",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    amount = parse_amount(
        request.form.get("amount")
    )

    funding_type = request.form.get(
        "funding_type",
        ""
    ).strip()

    cost_date = parse_datetime_local(
        request.form.get("cost_date")
    )

    notes = request.form.get(
        "notes",
        ""
    ).strip()

    if not cost_type:
        flash("Choose a cost type.", "error")
        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    if not description:
        flash(
            "Enter a description for this landed cost.",
            "error"
        )
        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    if amount is None or amount <= 0:
        flash(
            "Enter a valid cost amount greater than zero.",
            "error"
        )
        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    if cost_date is None:
        flash("Enter a valid cost date.", "error")
        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    if funding_type not in {
        "tydal_money",
        "partner_personal"
    }:
        flash(
            "Choose how this cost was funded.",
            "error"
        )
        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    money_account = None
    partner = None

    # --------------------------------------------------------
    # TYDAL MONEY FUNDING
    # --------------------------------------------------------

    if funding_type == "tydal_money":

        try:
            money_account_id = int(
                request.form.get("money_account_id")
            )
        except (TypeError, ValueError):
            flash(
                "Choose the TYDAL money location used.",
                "error"
            )
            return redirect(
                url_for(
                    "purchases.supplier_order_detail",
                    order_id=order_id
                )
            )

        money_account = db.session.get(
            MoneyAccount,
            money_account_id
        )

        if not money_account or not money_account.is_active:
            flash(
                "The selected money location is unavailable.",
                "error"
            )
            return redirect(
                url_for(
                    "purchases.supplier_order_detail",
                    order_id=order_id
                )
            )

        available_balance = get_account_balance(
            money_account.id
        )

        if amount > available_balance:
            flash(
                f"Not enough money in {money_account.name}. "
                f"Available: R{available_balance:.2f}.",
                "error"
            )
            return redirect(
                url_for(
                    "purchases.supplier_order_detail",
                    order_id=order_id
                )
            )

    # --------------------------------------------------------
    # PARTNER PERSONAL FUNDING
    # --------------------------------------------------------

    if funding_type == "partner_personal":

        try:
            partner_id = int(
                request.form.get("partner_id")
            )
        except (TypeError, ValueError):
            flash(
                "Choose the partner who paid personally.",
                "error"
            )
            return redirect(
                url_for(
                    "purchases.supplier_order_detail",
                    order_id=order_id
                )
            )

        partner = db.session.get(
            User,
            partner_id
        )

        if not partner or not partner.is_active:
            flash(
                "The selected partner is unavailable.",
                "error"
            )
            return redirect(
                url_for(
                    "purchases.supplier_order_detail",
                    order_id=order_id
                )
            )

    # --------------------------------------------------------
    # SAVE LANDED COST + ACCOUNTING ENTRY
    # --------------------------------------------------------

    try:

        supplier_order = lock_order(order_id)
        if funding_type == "tydal_money" and amount > get_account_balance(money_account.id):
            raise SupplierError("The money balance changed. Reload before adding this cost.")

        order_cost = SupplierOrderCost(
            supplier_order_id=supplier_order.id,
            cost_type=cost_type,
            description=description,
            amount=amount,
            funding_type=funding_type,
            money_account_id=(
                money_account.id
                if money_account
                else None
            ),
            partner_id=(
                partner.id
                if partner
                else None
            ),
            cost_date=cost_date,
            notes=notes or None,
            created_by_id=current_user.id
        )

        db.session.add(order_cost)
        db.session.flush()

        # ----------------------------------------------------
        # COST PAID USING TYDAL MONEY
        # ----------------------------------------------------

        if funding_type == "tydal_money":

            ledger_transaction = FinancialTransaction(
                transaction_type="supplier_order_cost",
                amount=amount,
                from_account_id=money_account.id,
                to_account_id=None,
                description=(
                    f"{description} - "
                    f"{supplier_order.order_number}"
                ),
                reference=supplier_order.order_number,
                transaction_date=cost_date,
                is_historical=False,
                is_estimate=False,
                source_type="supplier_order_cost",
                source_id=order_cost.id,
                notes=notes or None,
                created_by_id=current_user.id
            )

            db.session.add(
                ledger_transaction
            )

        # ----------------------------------------------------
        # COST PAID PERSONALLY BY PARTNER
        # ----------------------------------------------------

        else:

            partner_transaction = PartnerTransaction(
                partner_id=partner.id,
                transaction_type="personal_expense",
                amount=amount,
                money_account_id=None,
                description=(
                    f"{description} - "
                    f"{supplier_order.order_number}"
                ),
                repayment_expected=True,
                transaction_date=cost_date,
                is_historical=False,
                is_estimate=False,
                notes=notes or None,
                created_by_id=current_user.id
            )

            db.session.add(
                partner_transaction
            )

        if funding_type == "partner_personal":
            db.session.flush()
            order_cost.partner_transaction_id = partner_transaction.id

        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "Landed cost could not be saved. "
            "No money or partner balance was changed.",
            "error"
        )

        return redirect(
            url_for(
                "purchases.supplier_order_detail",
                order_id=order_id
            )
        )

    if funding_type == "tydal_money":

        flash(
            f"R{amount:.2f} added to the landed cost. "
            f"TYDAL money was reduced from {money_account.name}.",
            "success"
        )

    else:

        flash(
            f"R{amount:.2f} added to the landed cost. "
            f"TYDAL now recognises {partner.name}'s "
            "personal funding.",
            "success"
        )

    return redirect(
        url_for(
            "purchases.supplier_order_detail",
            order_id=order_id
        )
    )


@purchases.route('/orders/<int:order_id>/cost/<int:cost_id>/reverse', methods=['GET', 'POST'])
@login_required
def reverse_supplier_cost(order_id, cost_id):
    cost = db.get_or_404(SupplierOrderCost, cost_id)
    if cost.supplier_order_id != order_id:
        return 'Cost does not belong to this order.', 404
    form = FlaskForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            return 'Invalid or expired form. Reload the correction.', 400
        try:
            reverse_cost(order_id, cost_id, current_user.id, request.form.get('reason'),
                request.form.get('transaction_id'))
            db.session.commit()
            flash('Cost reversed. Original records and the correction remain in history.', 'success')
        except SupplierError as exc:
            db.session.rollback()
            flash(str(exc), 'error')
        except Exception:
            db.session.rollback()
            flash('Correction failed. No balances were changed.', 'error')
        return redirect(url_for('purchases.supplier_order_detail', order_id=order_id))
    if cost.funding_type == 'partner_personal':
        matches = partner_matches(cost)
    else:
        matches = FinancialTransaction.query.filter_by(source_type='supplier_order_cost',
            source_id=cost.id, amount=cost.amount, from_account_id=cost.money_account_id,
            to_account_id=None, reversal_of_id=None).all()
    return render_template('purchases/cost_reverse.html', cost=cost, matches=matches, form=form)


@purchases.route('/orders/<int:order_id>/receive', methods=['GET', 'POST'])
@login_required
def receive_supplier_order(order_id):
    order = db.get_or_404(SupplierOrder, order_id)
    form = FlaskForm()
    if request.method == 'POST':
        if not form.validate_on_submit():
            return 'Invalid or expired form. Reload the receipt.', 400
        fields = ['product_id', 'quantity', 'location_id', 'goods_total',
            'name', 'brand', 'category', 'size', 'color', 'selling_price']
        values = {field: request.form.getlist(field) for field in fields}
        count = len(values['product_id'])
        try:
            if not count or any(len(items) != count for items in values.values()):
                raise SupplierError('Received product information is incomplete.')
            lines = [{field: values[field][i] for field in fields} for i in range(count)]
            receive_order(order_id, current_user.id, lines)
            db.session.commit()
            flash('Order received into inventory. Existing payments were unchanged.', 'success')
            return redirect(url_for('purchases.supplier_order_detail', order_id=order_id))
        except SupplierError as exc:
            db.session.rollback()
            flash(str(exc), 'error')
        except Exception:
            db.session.rollback()
            flash('Receipt failed. No stock or balances were changed.', 'error')
        return render_template('purchases/order_receive.html', supplier_order=order, form=form,
            products=Product.query.filter_by(is_active=True).order_by(Product.name).all(),
            locations=StockLocation.query.filter_by(is_active=True).order_by(StockLocation.name).all(),
            submitted_lines=[{field: values[field][i] if i < len(values[field]) else '' for field in fields}
                for i in range(min(count, 200))]), 400
    if order.status != 'in_transit':
        flash('Only an in-transit order can be received.', 'error')
        return redirect(url_for('purchases.supplier_order_detail', order_id=order_id))
    return render_template('purchases/order_receive.html', supplier_order=order, form=form,
        products=Product.query.filter_by(is_active=True).order_by(Product.name).all(),
        locations=StockLocation.query.filter_by(is_active=True).order_by(StockLocation.name).all())
