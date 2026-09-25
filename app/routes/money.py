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
from app.models import MoneyAccount, FinancialTransaction


money = Blueprint(
    "money",
    __name__,
    url_prefix="/money"
)


# ============================================================
# HELPERS
# ============================================================

def get_account_balance(account_id):
    """
    Calculate a money account balance directly from the
    FinancialTransaction ledger.

    Money entering the account increases the balance.
    Money leaving the account decreases the balance.
    """

    transactions = FinancialTransaction.query.filter(
        (FinancialTransaction.to_account_id == account_id) |
        (FinancialTransaction.from_account_id == account_id)
    ).all()

    balance = Decimal("0.00")

    for transaction in transactions:
        amount = Decimal(str(transaction.amount or 0))

        if transaction.to_account_id == account_id:
            balance += amount

        if transaction.from_account_id == account_id:
            balance -= amount

    return balance


# ============================================================
# MONEY DASHBOARD
# ============================================================

@money.route("/")
@login_required
def index():

    accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name.asc())
        .all()
    )

    account_rows = []
    total_business_money = Decimal("0.00")

    for account in accounts:

        balance = get_account_balance(account.id)

        total_business_money += balance

        account_rows.append({
            "account": account,
            "balance": balance
        })

    recent_transactions = (
        FinancialTransaction.query
        .order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc()
        )
        .limit(15)
        .all()
    )

    return render_template(
        "money/index.html",
        account_rows=account_rows,
        accounts=accounts,
        total_business_money=total_business_money,
        recent_transactions=recent_transactions
    )


# ============================================================
# TRANSFER MONEY
# ============================================================

@money.route("/transfer", methods=["POST"])
@login_required
def transfer():

    from_account_id = request.form.get(
        "from_account_id",
        type=int
    )

    to_account_id = request.form.get(
        "to_account_id",
        type=int
    )

    amount_raw = request.form.get(
        "amount",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    notes = request.form.get(
        "notes",
        ""
    ).strip()


    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not from_account_id or not to_account_id:
        flash(
            "Choose where the money is coming from and where it is going.",
            "error"
        )
        return redirect(url_for("money.index"))

    if from_account_id == to_account_id:
        flash(
            "Money cannot be transferred to the same location.",
            "error"
        )
        return redirect(url_for("money.index"))


    # --------------------------------------------------------
    # Validate amount
    # --------------------------------------------------------

    try:
        amount = Decimal(amount_raw).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, ValueError):
        flash(
            "Enter a valid transfer amount.",
            "error"
        )
        return redirect(url_for("money.index"))

    if amount <= Decimal("0.00"):
        flash(
            "Transfer amount must be greater than R0.00.",
            "error"
        )
        return redirect(url_for("money.index"))


    # --------------------------------------------------------
    # Validate accounts
    # --------------------------------------------------------

    from_account = db.session.get(
        MoneyAccount,
        from_account_id
    )

    to_account = db.session.get(
        MoneyAccount,
        to_account_id
    )

    if not from_account or not to_account:
        flash(
            "One of the selected money locations does not exist.",
            "error"
        )
        return redirect(url_for("money.index"))

    if not from_account.is_active or not to_account.is_active:
        flash(
            "Transfers can only use active money locations.",
            "error"
        )
        return redirect(url_for("money.index"))


    # --------------------------------------------------------
    # Check available money
    # --------------------------------------------------------

    available_balance = get_account_balance(
        from_account.id
    )

    if amount > available_balance:
        flash(
            f"{from_account.name} only has "
            f"R{available_balance:.2f} available.",
            "error"
        )
        return redirect(url_for("money.index"))


    # --------------------------------------------------------
    # Create ledger transfer
    # --------------------------------------------------------

    if not description:
        description = (
            f"Transfer from {from_account.name} "
            f"to {to_account.name}"
        )

    transaction = FinancialTransaction(
        transaction_type="transfer",
        amount=amount,
        from_account_id=from_account.id,
        to_account_id=to_account.id,
        description=description,
        source_type="transfer",
        notes=notes or None,
        created_by_id=current_user.id
    )

    db.session.add(transaction)

    try:
        db.session.commit()

    except Exception:
        db.session.rollback()

        flash(
            "The transfer could not be recorded. No money was changed.",
            "error"
        )

        return redirect(url_for("money.index"))


    flash(
        f"R{amount:.2f} moved from "
        f"{from_account.name} to {to_account.name}.",
        "success"
    )

    return redirect(url_for("money.index"))