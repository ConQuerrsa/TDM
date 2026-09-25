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
    User,
    MoneyAccount,
    PartnerTransaction,
    FinancialTransaction
)


partners = Blueprint(
    "partners",
    __name__,
    url_prefix="/partners"
)


# ============================================================
# HELPERS
# ============================================================

def get_account_balance(account_id):
    """
    Derive the true balance from TDM's financial ledger.
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


def money(value):
    return Decimal(str(value or 0))


# ============================================================
# PARTNERS PAGE
# ============================================================

@partners.route("/")
@login_required
def index():

    # --------------------------------------------------------
    # Active partners/users
    # --------------------------------------------------------

    partners_list = (
        User.query
        .filter(
            User.is_active.is_(True),
            User.role.in_(["partner", "admin"])
        )
        .order_by(User.name.asc())
        .all()
    )


    # --------------------------------------------------------
    # Active TYDAL money locations
    # --------------------------------------------------------

    accounts = (
        MoneyAccount.query
        .filter_by(is_active=True)
        .order_by(MoneyAccount.name.asc())
        .all()
    )


    # --------------------------------------------------------
    # Recent partner money history
    # --------------------------------------------------------

    transactions = (
        PartnerTransaction.query
        .order_by(
            PartnerTransaction.transaction_date.desc(),
            PartnerTransaction.id.desc()
        )
        .limit(50)
        .all()
    )


    # --------------------------------------------------------
    # Partner positions
    # --------------------------------------------------------

    partner_rows = []

    total_contributions = Decimal("0.00")
    total_advances = Decimal("0.00")
    total_withdrawals = Decimal("0.00")
    total_personal_expenses = Decimal("0.00")
    total_repayments = Decimal("0.00")
    total_settlements = Decimal("0.00")


    for partner in partners_list:

        partner_transactions = (
            PartnerTransaction.query
            .filter_by(partner_id=partner.id)
            .all()
        )

        contributions = Decimal("0.00")
        advances = Decimal("0.00")
        withdrawals = Decimal("0.00")
        personal_expenses = Decimal("0.00")
        repayments = Decimal("0.00")
        settlements = Decimal("0.00")


        # ----------------------------------------------------
        # Add up this partner's transaction history
        # ----------------------------------------------------

        for transaction in partner_transactions:

            amount = money(transaction.amount)

            if transaction.transaction_type == "contribution":
                contributions += amount

            elif transaction.transaction_type == "advance":
                advances += amount

            elif transaction.transaction_type == "withdrawal":
                withdrawals += amount

            elif transaction.transaction_type == "personal_expense":
                personal_expenses += amount

            elif transaction.transaction_type == "repayment":
                repayments += amount

            elif transaction.transaction_type == "settlement":
                settlements += amount


        # ----------------------------------------------------
        # CURRENT PARTNER POSITION
        #
        # Positive:
        # TYDAL owes the partner
        #
        # Negative:
        # Partner owes TYDAL
        #
        # Contribution is excluded because it is not debt.
        # ----------------------------------------------------

        net_position = (
            advances
            + personal_expenses
            + repayments
            - withdrawals
            - settlements
        )


        if net_position > 0:

            position_type = "business_owes_partner"
            position_amount = net_position


        elif net_position < 0:

            position_type = "partner_owes_business"
            position_amount = abs(net_position)


        else:

            position_type = "clear"
            position_amount = Decimal("0.00")


        # ----------------------------------------------------
        # Add this partner to the UI
        # ----------------------------------------------------

        partner_rows.append({
            "partner": partner,
            "contributions": contributions,
            "advances": advances,
            "withdrawals": withdrawals,
            "personal_expenses": personal_expenses,
            "repayments": repayments,
            "settlements": settlements,
            "net_position": net_position,
            "position_type": position_type,
            "position_amount": position_amount
        })


        # ----------------------------------------------------
        # Business-wide totals
        # ----------------------------------------------------

        total_contributions += contributions
        total_advances += advances
        total_withdrawals += withdrawals
        total_personal_expenses += personal_expenses
        total_repayments += repayments
        total_settlements += settlements


    # --------------------------------------------------------
    # Current balance of each TYDAL money location
    # --------------------------------------------------------

    account_rows = []

    for account in accounts:

        account_rows.append({
            "account": account,
            "balance": get_account_balance(account.id)
        })


    # --------------------------------------------------------
    # Render page
    # --------------------------------------------------------

    return render_template(
        "partners/index.html",
        partners=partners_list,
        partner_rows=partner_rows,
        transactions=transactions,
        account_rows=account_rows,
        total_contributions=total_contributions,
        total_advances=total_advances,
        total_withdrawals=total_withdrawals,
        total_personal_expenses=total_personal_expenses,
        total_repayments=total_repayments,
        total_settlements=total_settlements
    )

# ============================================================
# RECORD PARTNER TRANSACTION
# ============================================================

@partners.route("/transaction", methods=["POST"])
@login_required
def record_transaction():

    partner_id = request.form.get(
        "partner_id",
        type=int
    )

    transaction_type = request.form.get(
        "transaction_type",
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

    description = request.form.get(
        "description",
        ""
    ).strip()

    notes = request.form.get(
        "notes",
        ""
    ).strip()


    allowed_types = {
    "contribution",
    "advance",
    "withdrawal",
    "personal_expense",
    "repayment",
    "settlement"
}


    if not partner_id:
        flash(
            "Choose the partner involved.",
            "error"
        )
        return redirect(url_for("partners.index"))


    if transaction_type not in allowed_types:
        flash(
            "Choose a valid partner transaction type.",
            "error"
        )
        return redirect(url_for("partners.index"))


    try:

        amount = Decimal(
            amount_raw
        ).quantize(
            Decimal("0.01")
        )

    except (InvalidOperation, ValueError):

        flash(
            "Enter a valid amount.",
            "error"
        )

        return redirect(url_for("partners.index"))


    if amount <= Decimal("0.00"):

        flash(
            "Amount must be greater than R0.00.",
            "error"
        )

        return redirect(url_for("partners.index"))


    partner = db.session.get(
        User,
        partner_id
    )


    if (
        not partner
        or not partner.is_active
        or partner.role not in ["partner", "admin"]
    ):

        flash(
            "The selected partner is unavailable.",
            "error"
        )

        return redirect(url_for("partners.index"))


    # --------------------------------------------------------
    # Personal expense is different.
    #
    # Partner used THEIR OWN money.
    # Therefore no TYDAL MoneyAccount is involved.
    # --------------------------------------------------------

    account = None

    if transaction_type != "personal_expense":

        if not money_account_id:

            flash(
                "Choose where the TYDAL money is located.",
                "error"
            )

            return redirect(url_for("partners.index"))


        account = db.session.get(
            MoneyAccount,
            money_account_id
        )


        if not account or not account.is_active:

            flash(
                "The selected money location is unavailable.",
                "error"
            )

            return redirect(url_for("partners.index"))


    # --------------------------------------------------------
    # Money leaving TYDAL:
    #
    # withdrawal
    #
    # Must not exceed actual account balance.
    # --------------------------------------------------------

    if transaction_type in ["withdrawal", "settlement"]:

        available_balance = get_account_balance(
            account.id
        )

        if amount > available_balance:

            flash(
                f"{account.name} only has "
                f"R{available_balance:.2f} available.",
                "error"
            )

            return redirect(url_for("partners.index"))


    # --------------------------------------------------------
    # Default descriptions
    # --------------------------------------------------------

    default_descriptions = {
        "contribution":
            f"{partner.name} contributed money to TYDAL",

        "advance":
            f"{partner.name} advanced money to TYDAL",

        "withdrawal":
            f"{partner.name} withdrew TYDAL money",

        "personal_expense":
            f"{partner.name} paid a TYDAL expense personally",

        "repayment":
            f"{partner.name} repaid money to TYDAL",    

        "settlement":
            f"TYDAL settled money owed to {partner.name}"
    }


    final_description = (
        description
        or default_descriptions[transaction_type]
    )

    transaction_date = datetime.utcnow()


    try:

        partner_transaction = PartnerTransaction(
            partner_id=partner.id,
            transaction_type=transaction_type,
            amount=amount,

            money_account_id=(
                account.id
                if account
                else None
            ),

            description=final_description,

            repayment_expected=(
                transaction_type == "advance"
            ),

            transaction_date=transaction_date,
            is_historical=False,
            is_estimate=False,
            notes=notes or None,
            created_by_id=current_user.id
        )

        db.session.add(
            partner_transaction
        )

        db.session.flush()


        # ----------------------------------------------------
        # CENTRAL LEDGER
        # ----------------------------------------------------
        #
        # contribution:
        #     partner money enters TYDAL
        #
        # advance:
        #     partner money enters TYDAL
        #
        # withdrawal:
        #     TYDAL money leaves business
        #
        # repayment:
        #     money returns to TYDAL
        #
        # personal_expense:
        #     NO ledger movement because TYDAL's own
        #     cash/bank never moved.
        # ----------------------------------------------------

        if transaction_type in [
            "contribution",
            "advance",
            "repayment"
        ]:

            ledger_transaction = FinancialTransaction(
                transaction_type=f"partner_{transaction_type}",
                amount=amount,
                from_account_id=None,
                to_account_id=account.id,
                description=final_description,
                reference=f"PT-{partner_transaction.id:06d}",
                transaction_date=transaction_date,
                is_historical=False,
                is_estimate=False,
                source_type="partner_transaction",
                source_id=partner_transaction.id,
                notes=notes or None,
                created_by_id=current_user.id
            )

            db.session.add(
                ledger_transaction
            )


        elif transaction_type in ["withdrawal", "settlement"]:

            ledger_transaction = FinancialTransaction(
                transaction_type=f"partner_{transaction_type}",
                amount=amount,
                from_account_id=account.id,
                to_account_id=None,
                description=final_description,
                reference=f"PT-{partner_transaction.id:06d}",
                transaction_date=transaction_date,
                is_historical=False,
                is_estimate=False,
                source_type="partner_transaction",
                source_id=partner_transaction.id,
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
            "The partner transaction could not be recorded. "
            "No money was changed.",
            "error"
        )

        return redirect(url_for("partners.index"))


    flash(
        f"R{amount:.2f} {transaction_type.replace('_', ' ')} "
        f"recorded for {partner.name}.",
        "success"
    )

    return redirect(url_for("partners.index"))