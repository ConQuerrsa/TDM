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
    Expense,
    MoneyAccount,
    FinancialTransaction
)


expenses = Blueprint(
    "expenses",
    __name__,
    url_prefix="/expenses"
)


# ============================================================
# HELPERS
# ============================================================

def get_account_balance(account_id):
    """
    Calculate the true account balance from TDM's central ledger.
    """

    transactions = FinancialTransaction.query.filter(
        (FinancialTransaction.to_account_id == account_id) |
        (FinancialTransaction.from_account_id == account_id)
    ).all()

    balance = Decimal("0.00")

    for transaction in transactions:

        amount = Decimal(
            str(transaction.amount or 0)
        )

        if transaction.to_account_id == account_id:
            balance += amount

        if transaction.from_account_id == account_id:
            balance -= amount

    return balance


# ============================================================
# EXPENSES PAGE
# ============================================================

@expenses.route("/")
@login_required
def index():

    expense_records = (
        Expense.query
        .order_by(
            Expense.expense_date.desc(),
            Expense.id.desc()
        )
        .limit(50)
        .all()
    )

    money_accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name.asc())
        .all()
    )


    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    total_expenses = sum(
        (
            Decimal(str(expense.amount or 0))
            for expense in expense_records
        ),
        Decimal("0.00")
    )

    today = datetime.utcnow().date()

    today_expenses = sum(
        (
            Decimal(str(expense.amount or 0))
            for expense in expense_records
            if expense.expense_date.date() == today
        ),
        Decimal("0.00")
    )


    # --------------------------------------------------------
    # Category totals
    # --------------------------------------------------------

    category_totals = {}

    for expense in expense_records:

        category = (
            expense.category
            or "Other"
        )

        amount = Decimal(
            str(expense.amount or 0)
        )

        category_totals[category] = (
            category_totals.get(
                category,
                Decimal("0.00")
            )
            + amount
        )


    category_rows = sorted(
        category_totals.items(),
        key=lambda item: item[1],
        reverse=True
    )


    # --------------------------------------------------------
    # Money account balances
    # --------------------------------------------------------

    account_rows = []

    for account in money_accounts:

        account_rows.append({
            "account": account,
            "balance": get_account_balance(
                account.id
            )
        })


    return render_template(
        "expenses/index.html",
        expenses=expense_records,
        account_rows=account_rows,
        total_expenses=total_expenses,
        today_expenses=today_expenses,
        category_rows=category_rows
    )


# ============================================================
# RECORD EXPENSE
# ============================================================

@expenses.route("/new", methods=["POST"])
@login_required
def new_expense():

    description = request.form.get(
        "description",
        ""
    ).strip()

    category = request.form.get(
        "category",
        ""
    ).strip()

    amount_raw = request.form.get(
        "amount",
        ""
    ).strip()

    money_account_id = request.form.get(
        "money_account_id",
        type=int
    )

    notes = request.form.get(
        "notes",
        ""
    ).strip()


    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not description:
        flash(
            "Enter what TYDAL paid for.",
            "error"
        )
        return redirect(url_for("expenses.index"))


    if not category:
        flash(
            "Choose an expense category.",
            "error"
        )
        return redirect(url_for("expenses.index"))


    if not money_account_id:
        flash(
            "Choose where TYDAL paid the money from.",
            "error"
        )
        return redirect(url_for("expenses.index"))


    # --------------------------------------------------------
    # Amount
    # --------------------------------------------------------

    try:

        amount = Decimal(
            amount_raw
        ).quantize(
            Decimal("0.01")
        )

    except (InvalidOperation, ValueError):

        flash(
            "Enter a valid expense amount.",
            "error"
        )

        return redirect(
            url_for("expenses.index")
        )


    if amount <= Decimal("0.00"):

        flash(
            "Expense amount must be greater than R0.00.",
            "error"
        )

        return redirect(
            url_for("expenses.index")
        )


    # --------------------------------------------------------
    # Validate money account
    # --------------------------------------------------------

    money_account = db.session.get(
        MoneyAccount,
        money_account_id
    )


    if (
        not money_account
        or not money_account.is_active
    ):

        flash(
            "The selected money location is unavailable.",
            "error"
        )

        return redirect(
            url_for("expenses.index")
        )


    available_balance = get_account_balance(
        money_account.id
    )


    if amount > available_balance:

        flash(
            f"{money_account.name} only has "
            f"R{available_balance:.2f} available.",
            "error"
        )

        return redirect(
            url_for("expenses.index")
        )


    # --------------------------------------------------------
    # Create Expense + Ledger transaction together
    # --------------------------------------------------------

    expense_date = datetime.utcnow()


    try:

        expense = Expense(
            description=description,
            category=category,
            amount=amount,
            money_account_id=money_account.id,
            recorded_by_id=current_user.id,
            notes=notes or None,
            expense_date=expense_date,
            is_historical=False,
            is_estimate=False
        )

        db.session.add(expense)

        # We need expense.id for the ledger source.
        db.session.flush()


        ledger_transaction = FinancialTransaction(
            transaction_type="expense",
            amount=amount,
            from_account_id=money_account.id,
            to_account_id=None,
            description=description,
            reference=f"EXP-{expense.id:06d}",
            transaction_date=expense_date,
            is_historical=False,
            is_estimate=False,
            source_type="expense",
            source_id=expense.id,
            notes=notes or None,
            created_by_id=current_user.id
        )

        db.session.add(
            ledger_transaction
        )

        db.session.commit()


    except Exception:

        db.session.rollback()

        flash(
            "The expense could not be recorded. "
            "No money was changed.",
            "error"
        )

        return redirect(
            url_for("expenses.index")
        )


    flash(
        f"R{amount:.2f} expense recorded from "
        f"{money_account.name}.",
        "success"
    )

    return redirect(
        url_for("expenses.index")
    )