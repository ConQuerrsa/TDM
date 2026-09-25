from datetime import datetime
from decimal import Decimal

from app import db
from flask_login import UserMixin


# ============================================================
# USERS / PARTNERS
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        nullable=False
    )

    phone = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(30),
        nullable=False,
        default="partner"
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    transactions = db.relationship(
        "FinancialTransaction",
        back_populates="created_by",
        foreign_keys="FinancialTransaction.created_by_id"
    )


# ============================================================
# MONEY ACCOUNTS / LOCATIONS
# ============================================================

class MoneyAccount(db.Model):
    """
    Represents a place where TYDAL money physically exists.

    Examples:
    - Partner A Cash
    - Partner B Cash
    - Partner A TymeBank
    - Partner B Capitec
    - Cash Send
    - TYDAL Business Bank Account
    """

    __tablename__ = "money_accounts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    account_type = db.Column(
        db.String(30),
        nullable=False
    )

    owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    opening_balance = db.Column(
        db.Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    owner = db.relationship(
        "User",
        backref="money_accounts"
    )


# ============================================================
# STOCK LOCATIONS
# ============================================================

class StockLocation(db.Model):
    """
    Represents where TYDAL physical stock is currently held.

    Examples:
    - Partner A
    - Partner B
    - Home / Main Stock
    - Storage
    """

    __tablename__ = "stock_locations"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    location_type = db.Column(
        db.String(30),
        nullable=False,
        default="partner"
    )

    owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    owner = db.relationship(
        "User",
        backref="stock_locations"
    )


# ============================================================
# PRODUCTS
# ============================================================

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(150),
        nullable=False
    )

    brand = db.Column(
        db.String(100),
        nullable=True
    )

    category = db.Column(
        db.String(100),
        nullable=True
    )

    size = db.Column(
        db.String(50),
        nullable=True
    )

    color = db.Column(
        db.String(50),
        nullable=True
    )

    cost_price = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00")
    )

    selling_price = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00")
    )

    # Overall quantity across all stock locations.
    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    low_stock_level = db.Column(
        db.Integer,
        nullable=False,
        default=2
    )

    supplier = db.Column(
        db.String(150),
        nullable=True
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    sale_items = db.relationship(
        "SaleItem",
        back_populates="product"
    )

    stock_movements = db.relationship(
        "StockMovement",
        back_populates="product"
    )

    holdings = db.relationship(
        "StockHolding",
        back_populates="product",
        cascade="all, delete-orphan"
    )


# ============================================================
# STOCK HOLDINGS
# ============================================================

class StockHolding(db.Model):
    """
    Shows how much of each product is physically held
    at each stock location.

    Example:

    Product: Billabong Shorts
    Partner A: 4
    Partner B: 3
    Main Stock: 8

    Product.quantity should equal the total of these holdings.
    """

    __tablename__ = "stock_holdings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    stock_location_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_locations.id"),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    product = db.relationship(
        "Product",
        back_populates="holdings"
    )

    stock_location = db.relationship(
        "StockLocation",
        backref="holdings"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "product_id",
            "stock_location_id",
            name="uq_product_stock_location"
        ),
    )


# ============================================================
# SALES
# ============================================================

class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sale_number = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    total_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00")
    )

    payment_method = db.Column(
        db.String(30),
        nullable=False
    )

    money_account_id = db.Column(
        db.Integer,
        db.ForeignKey("money_accounts.id"),
        nullable=False
    )

    sold_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="completed"
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    # When the sale actually happened.
    sale_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Useful when entering remembered historical sales.
    is_historical = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    is_estimate = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    money_account = db.relationship(
        "MoneyAccount"
    )

    sold_by = db.relationship(
        "User"
    )

    items = db.relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan"
    )


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    unit_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    cost_price = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    line_total = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    # Where the sold stock came from.
    stock_location_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_locations.id"),
        nullable=True
    )

    sale = db.relationship(
        "Sale",
        back_populates="items"
    )

    product = db.relationship(
        "Product",
        back_populates="sale_items"
    )

    stock_location = db.relationship(
        "StockLocation"
    )


# ============================================================
# EXPENSES
# ============================================================

class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    description = db.Column(
        db.String(200),
        nullable=False
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    money_account_id = db.Column(
        db.Integer,
        db.ForeignKey("money_accounts.id"),
        nullable=False
    )

    recorded_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    # Actual date of expense.
    expense_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    is_historical = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    is_estimate = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    money_account = db.relationship(
        "MoneyAccount"
    )

    recorded_by = db.relationship(
        "User"
    )


# ============================================================
# PARTNER TRANSACTIONS
# ============================================================

class PartnerTransaction(db.Model):
    """
    Tracks money between TYDAL and individual partners.

    Types:

    contribution
        Partner helps TYDAL with money.
        Normally no repayment expected.

    advance
        TYDAL owes the partner.

    withdrawal
        Partner takes TYDAL money.

    personal_expense
        Partner pays a legitimate TYDAL expense personally.

    repayment
        Partner returns money to TYDAL.
    """

    __tablename__ = "partner_transactions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    partner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    transaction_type = db.Column(
        db.String(40),
        nullable=False
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    money_account_id = db.Column(
        db.Integer,
        db.ForeignKey("money_accounts.id"),
        nullable=True
    )

    description = db.Column(
        db.String(255),
        nullable=True
    )

    repayment_expected = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    transaction_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    is_historical = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    is_estimate = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    created_by_id = db.Column(
    db.Integer,
    db.ForeignKey("users.id"),
    nullable=True
    )

    created_by = db.relationship(
    "User",
    foreign_keys=[created_by_id]
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    partner = db.relationship(
    "User",
    foreign_keys=[partner_id]
)

    money_account = db.relationship(
        "MoneyAccount"
    )


# ============================================================
# STOCK MOVEMENTS
# ============================================================

class StockMovement(db.Model):
    """
    Keeps a permanent history of stock entering,
    leaving, or moving inside TYDAL.
    """

    __tablename__ = "stock_movements"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    movement_type = db.Column(
        db.String(40),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    unit_cost = db.Column(
        db.Numeric(12, 2),
        nullable=True
    )

    from_location_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_locations.id"),
        nullable=True
    )

    to_location_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_locations.id"),
        nullable=True
    )

    reference = db.Column(
        db.String(100),
        nullable=True
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    movement_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    is_historical = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    is_estimate = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    product = db.relationship(
        "Product",
        back_populates="stock_movements"
    )

    from_location = db.relationship(
        "StockLocation",
        foreign_keys=[from_location_id]
    )

    to_location = db.relationship(
        "StockLocation",
        foreign_keys=[to_location_id]
    )

    created_by = db.relationship(
        "User"
    )


# ============================================================
# PURCHASES / SUPPLIER ORDERS
# ============================================================

class Purchase(db.Model):
    """
    Represents a stock purchase/order.

    This is particularly important for TYDAL's Alibaba orders.
    """

    __tablename__ = "purchases"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    purchase_number = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    supplier = db.Column(
        db.String(150),
        nullable=False
    )

    total_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00")
    )

    money_account_id = db.Column(
        db.Integer,
        db.ForeignKey("money_accounts.id"),
        nullable=True
    )

    purchased_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="completed"
    )

    purchase_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    is_historical = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    is_estimate = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    money_account = db.relationship(
        "MoneyAccount"
    )

    purchased_by = db.relationship(
        "User"
    )

    items = db.relationship(
        "PurchaseItem",
        back_populates="purchase",
        cascade="all, delete-orphan"
    )


class PurchaseItem(db.Model):
    __tablename__ = "purchase_items"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    purchase_id = db.Column(
        db.Integer,
        db.ForeignKey("purchases.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    unit_cost = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    line_total = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    purchase = db.relationship(
        "Purchase",
        back_populates="items"
    )

    product = db.relationship(
        "Product"
    )


# ============================================================
# CENTRAL FINANCIAL LEDGER
# ============================================================

class FinancialTransaction(db.Model):
    """
    Central financial history for TYDAL.

    This records where business money came from,
    where it went, or when it moved between accounts.

    Important:
    - Sale
    - Expense
    - Partner transaction
    - Purchase
    - Transfer
    - Opening balance
    - Adjustment

    Financial history should not be silently deleted.
    Corrections should use reversals/adjustments.
    """

    __tablename__ = "financial_transactions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    transaction_type = db.Column(
        db.String(50),
        nullable=False,
        index=True
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    from_account_id = db.Column(
        db.Integer,
        db.ForeignKey("money_accounts.id"),
        nullable=True
    )

    to_account_id = db.Column(
        db.Integer,
        db.ForeignKey("money_accounts.id"),
        nullable=True
    )

    description = db.Column(
        db.String(255),
        nullable=False
    )

    reference = db.Column(
        db.String(100),
        nullable=True
    )

    # When the transaction actually happened.
    transaction_date = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    # When TDM recorded it.
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Historical/opening information.
    is_historical = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # Used when details are remembered but not completely certain.
    is_estimate = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # Used for corrections without destroying history.
    reversal_of_id = db.Column(
        db.Integer,
        db.ForeignKey("financial_transactions.id"),
        nullable=True
    )

    # Source of the transaction.
    #
    # Examples:
    # sale
    # expense
    # partner_transaction
    # purchase
    # transfer
    # opening_balance
    # adjustment
    source_type = db.Column(
        db.String(50),
        nullable=True
    )

    source_id = db.Column(
        db.Integer,
        nullable=True
    )

    notes = db.Column(
        db.Text,
        nullable=True
    )

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    from_account = db.relationship(
        "MoneyAccount",
        foreign_keys=[from_account_id]
    )

    to_account = db.relationship(
        "MoneyAccount",
        foreign_keys=[to_account_id]
    )

    created_by = db.relationship(
        "User",
        back_populates="transactions",
        foreign_keys=[created_by_id]
    )

    reversal_of = db.relationship(
        "FinancialTransaction",
        remote_side=[id],
        uselist=False
    )

# ============================================================
# BUSINESS SETTINGS / SYSTEM STATE
# ============================================================

class BusinessSettings(db.Model):
    """
    Stores TYDAL-wide configuration and initialization state.

    There should normally be only one BusinessSettings record
    for the entire TDM installation.
    """

    __tablename__ = "business_settings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    business_name = db.Column(
        db.String(150),
        nullable=False,
        default="TYDAL"
    )

    setup_completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    setup_completed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    setup_completed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    setup_completed_by = db.relationship(
        "User",
        foreign_keys=[setup_completed_by_id]
    )