from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request
from flask_login import login_required

from app.models import (
    Sale,
    Expense,
    Purchase,
    Product,
    PartnerTransaction,
)


reports = Blueprint("reports", __name__, url_prefix="/reports")


def to_decimal(value):
    return Decimal(str(value or 0))


def parse_date(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        return fallback


@reports.route("/")
@login_required
def index():
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    default_start = today.replace(day=1)
    default_end = today

    start_date = parse_date(request.args.get("start"), default_start)
    end_date = parse_date(request.args.get("end"), default_end)

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    end_exclusive = end_date + timedelta(days=1)

    sales = Sale.query.filter(
        Sale.status == "completed",
        Sale.sale_date >= start_date,
        Sale.sale_date < end_exclusive
    ).order_by(Sale.sale_date.desc()).all()

    expenses = Expense.query.filter(
        Expense.expense_date >= start_date,
        Expense.expense_date < end_exclusive
    ).order_by(Expense.expense_date.desc()).all()

    purchases = Purchase.query.filter(
        Purchase.status == "completed",
        Purchase.purchase_date >= start_date,
        Purchase.purchase_date < end_exclusive
    ).order_by(Purchase.purchase_date.desc()).all()

    revenue = sum(
        (to_decimal(sale.total_amount) for sale in sales),
        Decimal("0.00")
    )

    operating_expenses = sum(
        (to_decimal(expense.amount) for expense in expenses),
        Decimal("0.00")
    )

    purchase_spend = sum(
        (to_decimal(purchase.total_amount) for purchase in purchases if purchase.supplier_receipt is None),
        Decimal("0.00")
    )

    cost_of_goods_sold = Decimal("0.00")
    units_sold = 0

    product_sales = {}

    for sale in sales:
        for item in sale.items:
            quantity = item.quantity or 0
            item_cost = to_decimal(item.cost_price) * quantity

            cost_of_goods_sold += item_cost
            units_sold += quantity

            product_name = (
                item.product.name
                if item.product
                else "Unknown product"
            )

            if product_name not in product_sales:
                product_sales[product_name] = {
                    "name": product_name,
                    "units": 0,
                    "revenue": Decimal("0.00"),
                }

            product_sales[product_name]["units"] += quantity
            product_sales[product_name]["revenue"] += to_decimal(
                item.line_total
            )

    gross_profit = revenue - cost_of_goods_sold
    operating_result = gross_profit - operating_expenses

    gross_margin = (
        float((gross_profit / revenue) * 100)
        if revenue > 0
        else 0
    )

    products = Product.query.filter_by(is_active=True).all()

    stock_units = sum(
        product.quantity or 0
        for product in products
    )

    stock_value = sum(
        (
            to_decimal(product.cost_price) *
            (product.quantity or 0)
            for product in products
        ),
        Decimal("0.00")
    )

    payment_totals = {}

    for sale in sales:
        label = (
            sale.payment_method or "Other"
        ).replace("_", " ").title()

        payment_totals[label] = (
            payment_totals.get(label, Decimal("0.00"))
            + to_decimal(sale.total_amount)
        )

    payment_breakdown = []

    for label, value in sorted(
        payment_totals.items(),
        key=lambda row: row[1],
        reverse=True
    ):
        payment_breakdown.append({
            "label": label,
            "value": value,
            "percent": (
                float((value / revenue) * 100)
                if revenue > 0
                else 0
            )
        })

    expense_totals = {}

    for expense in expenses:
        label = expense.category or "Other"
        expense_totals[label] = (
            expense_totals.get(label, Decimal("0.00"))
            + to_decimal(expense.amount)
        )

    expense_breakdown = []

    for label, value in sorted(
        expense_totals.items(),
        key=lambda row: row[1],
        reverse=True
    ):
        expense_breakdown.append({
            "label": label,
            "value": value,
            "percent": (
                float((value / operating_expenses) * 100)
                if operating_expenses > 0
                else 0
            )
        })

    top_products = sorted(
        product_sales.values(),
        key=lambda row: (
            row["revenue"],
            row["units"]
        ),
        reverse=True
    )[:8]

    partner_totals = {
        "advance": Decimal("0.00"),
        "personal_expense": Decimal("0.00"),
        "repayment": Decimal("0.00"),
        "withdrawal": Decimal("0.00"),
        "settlement": Decimal("0.00"),
    }

    for transaction in PartnerTransaction.query.all():
        if transaction.transaction_type in partner_totals:
            partner_totals[transaction.transaction_type] += (
                to_decimal(transaction.amount)
            )

    partner_net = (
        partner_totals["advance"]
        + partner_totals["personal_expense"]
        + partner_totals["repayment"]
        - partner_totals["withdrawal"]
        - partner_totals["settlement"]
    )

    if partner_net > 0:
        partner_label = "TYDAL owes partners"
        partner_amount = partner_net
    elif partner_net < 0:
        partner_label = "Partners owe TYDAL"
        partner_amount = abs(partner_net)
    else:
        partner_label = "Partner accounts clear"
        partner_amount = Decimal("0.00")

    return render_template(
        "reports/index.html",
        start_date=start_date,
        end_date=end_date,
        revenue=revenue,
        sale_count=len(sales),
        units_sold=units_sold,
        operating_expenses=operating_expenses,
        purchase_spend=purchase_spend,
        cost_of_goods_sold=cost_of_goods_sold,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        operating_result=operating_result,
        stock_units=stock_units,
        stock_value=stock_value,
        payment_breakdown=payment_breakdown,
        expense_breakdown=expense_breakdown,
        top_products=top_products,
        partner_label=partner_label,
        partner_amount=partner_amount,
    )
