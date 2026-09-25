from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

from app.models import Sale, Product, MoneyAccount, FinancialTransaction, PartnerTransaction, Purchase

main = Blueprint("main", __name__)


def to_decimal(value):
    return Decimal(str(value or 0))


def get_account_balance(account_id):
    transactions = FinancialTransaction.query.filter(
        (FinancialTransaction.to_account_id == account_id) |
        (FinancialTransaction.from_account_id == account_id)
    ).all()

    balance = Decimal("0.00")
    for transaction in transactions:
        amount = to_decimal(transaction.amount)
        if transaction.to_account_id == account_id:
            balance += amount
        if transaction.from_account_id == account_id:
            balance -= amount
    return balance


@main.route("/")
@login_required
def home():
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    week_start = today_start - timedelta(days=today_start.weekday())

    today_sales = Sale.query.filter(
        Sale.status == "completed",
        Sale.sale_date >= today_start,
        Sale.sale_date < tomorrow_start
    ).all()

    today_sales_total = sum(
        (to_decimal(sale.total_amount) for sale in today_sales),
        Decimal("0.00")
    )
    today_sales_count = len(today_sales)

    weekly_sales = Sale.query.filter(
        Sale.status == "completed",
        Sale.sale_date >= week_start,
        Sale.sale_date < tomorrow_start
    ).all()

    weekly_revenue = sum(
        (to_decimal(sale.total_amount) for sale in weekly_sales),
        Decimal("0.00")
    )

    # 7-day sales chart
    seven_day_start = today_start - timedelta(days=6)
    seven_day_sales = Sale.query.filter(
        Sale.status == "completed",
        Sale.sale_date >= seven_day_start,
        Sale.sale_date < tomorrow_start
    ).all()

    sales_by_date = {}
    for sale in seven_day_sales:
        key = sale.sale_date.date()
        sales_by_date[key] = sales_by_date.get(key, Decimal("0.00")) + to_decimal(sale.total_amount)

    seven_day_chart = []
    for offset in range(7):
        day = (seven_day_start + timedelta(days=offset)).date()
        seven_day_chart.append({
            "label": day.strftime("%a"),
            "date": day.strftime("%d %b"),
            "value": sales_by_date.get(day, Decimal("0.00"))
        })

    max_sales = max((row["value"] for row in seven_day_chart), default=Decimal("0.00"))
    for row in seven_day_chart:
        row["percent"] = float((row["value"] / max_sales) * 100) if max_sales > 0 else 0

    # Payment-method chart
    payment_totals = {}
    for sale in seven_day_sales:
        method = (sale.payment_method or "Other").replace("_", " ").title()
        payment_totals[method] = payment_totals.get(method, Decimal("0.00")) + to_decimal(sale.total_amount)

    payment_total = sum(payment_totals.values(), Decimal("0.00"))
    payment_chart = []
    for label, value in sorted(payment_totals.items(), key=lambda x: x[1], reverse=True):
        payment_chart.append({
            "label": label,
            "value": value,
            "percent": float((value / payment_total) * 100) if payment_total > 0 else 0
        })

    # Money
    accounts = MoneyAccount.query.filter_by(is_active=True).order_by(MoneyAccount.name.asc()).all()
    account_rows = []
    total_business_money = Decimal("0.00")
    for account in accounts:
        balance = get_account_balance(account.id)
        account_rows.append({"account": account, "balance": balance})
        total_business_money += balance

    # Inventory
    products = Product.query.filter_by(is_active=True).order_by(Product.name.asc()).all()
    total_stock_units = sum(product.quantity or 0 for product in products)
    stock_value = sum(
        (to_decimal(product.cost_price) * (product.quantity or 0) for product in products),
        Decimal("0.00")
    )

    stock_groups = {}
    for product in products:
        label = (product.brand or "").strip() or (product.category or "").strip() or "Other"
        stock_groups[label] = stock_groups.get(label, 0) + (product.quantity or 0)

    stock_chart = []
    for label, units in sorted(stock_groups.items(), key=lambda x: x[1], reverse=True)[:6]:
        stock_chart.append({
            "label": label,
            "units": units,
            "percent": (units / total_stock_units * 100) if total_stock_units > 0 else 0
        })

    low_stock_products = sorted(
        [p for p in products if (p.quantity or 0) <= (p.low_stock_level or 0)],
        key=lambda p: p.quantity or 0
    )[:6]

    # Partner position
    totals = {
        "advance": Decimal("0.00"),
        "personal_expense": Decimal("0.00"),
        "repayment": Decimal("0.00"),
        "withdrawal": Decimal("0.00"),
        "settlement": Decimal("0.00")
    }

    for transaction in PartnerTransaction.query.all():
        if transaction.transaction_type in totals:
            totals[transaction.transaction_type] += to_decimal(transaction.amount)

    partner_net_position = (
        totals["advance"] + totals["personal_expense"] + totals["repayment"]
        - totals["withdrawal"] - totals["settlement"]
    )

    if partner_net_position > 0:
        partner_position_label = "TYDAL owes partners"
        partner_position_amount = partner_net_position
    elif partner_net_position < 0:
        partner_position_label = "Partners owe TYDAL"
        partner_position_amount = abs(partner_net_position)
    else:
        partner_position_label = "Partner accounts clear"
        partner_position_amount = Decimal("0.00")

    recent_sales = Sale.query.filter_by(status="completed").order_by(
        Sale.sale_date.desc(), Sale.id.desc()
    ).limit(5).all()

    recent_purchases = Purchase.query.filter_by(status="completed").order_by(
        Purchase.purchase_date.desc(), Purchase.id.desc()
    ).limit(5).all()

    recent_transactions = FinancialTransaction.query.order_by(
        FinancialTransaction.transaction_date.desc(),
        FinancialTransaction.id.desc()
    ).limit(8).all()

    return render_template(
        "dashboard.html",
        today_sales_total=today_sales_total,
        today_sales_count=today_sales_count,
        weekly_revenue=weekly_revenue,
        total_business_money=total_business_money,
        account_rows=account_rows,
        stock_value=stock_value,
        total_stock_units=total_stock_units,
        low_stock_products=low_stock_products,
        partner_position_amount=partner_position_amount,
        partner_position_label=partner_position_label,
        partner_net_position=partner_net_position,
        recent_sales=recent_sales,
        recent_purchases=recent_purchases,
        recent_transactions=recent_transactions,
        seven_day_chart=seven_day_chart,
        payment_chart=payment_chart,
        stock_chart=stock_chart
    )


@main.route("/setup")
@login_required
def setup_redirect():
    return redirect(url_for("setup.index"))
