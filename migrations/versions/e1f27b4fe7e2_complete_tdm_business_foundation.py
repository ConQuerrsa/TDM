"""Complete TDM business foundation

Revision ID: e1f27b4fe7e2
Revises: 4822ee90be74
Create Date: 2026-09-23 16:12:23.261614

"""

from alembic import op
import sqlalchemy as sa


revision = "e1f27b4fe7e2"
down_revision = "4822ee90be74"
branch_labels = None
depends_on = None


def upgrade():

    # --------------------------------------------------------
    # EXPENSES
    # --------------------------------------------------------

    with op.batch_alter_table(
        "expenses",
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "expense_date",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_historical",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )


    # --------------------------------------------------------
    # FINANCIAL TRANSACTIONS
    # --------------------------------------------------------

    with op.batch_alter_table(
        "financial_transactions",
        schema=None
    ) as batch_op:

        batch_op.create_index(
            batch_op.f("ix_financial_transactions_transaction_date"),
            ["transaction_date"],
            unique=False
        )

        batch_op.create_index(
            batch_op.f("ix_financial_transactions_transaction_type"),
            ["transaction_type"],
            unique=False
        )


    # --------------------------------------------------------
    # MONEY ACCOUNTS
    # --------------------------------------------------------

    with op.batch_alter_table(
        "money_accounts",
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            "opening_balance",
            existing_type=sa.NUMERIC(
                precision=12,
                scale=2
            ),
            nullable=False,
            existing_nullable=True,
            server_default=sa.text("0.00")
        )


    # --------------------------------------------------------
    # PARTNER TRANSACTIONS
    # --------------------------------------------------------

    with op.batch_alter_table(
        "partner_transactions",
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "transaction_date",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_historical",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "notes",
                sa.Text(),
                nullable=True
            )
        )


    # --------------------------------------------------------
    # SALE ITEMS
    # --------------------------------------------------------

    with op.batch_alter_table(
        "sale_items",
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "stock_location_id",
                sa.Integer(),
                nullable=True
            )
        )

        batch_op.create_foreign_key(
            "fk_sale_items_stock_location",
            "stock_locations",
            ["stock_location_id"],
            ["id"]
        )


    # --------------------------------------------------------
    # SALES
    # --------------------------------------------------------

    with op.batch_alter_table(
        "sales",
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "sale_date",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_historical",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.create_index(
            batch_op.f("ix_sales_sale_number"),
            ["sale_number"],
            unique=True
        )


    # --------------------------------------------------------
    # STOCK MOVEMENTS
    # --------------------------------------------------------

    with op.batch_alter_table(
        "stock_movements",
        schema=None
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "from_location_id",
                sa.Integer(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "to_location_id",
                sa.Integer(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "movement_date",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_historical",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.add_column(
            sa.Column(
                "is_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

        batch_op.create_foreign_key(
            "fk_stock_movements_to_location",
            "stock_locations",
            ["to_location_id"],
            ["id"]
        )

        batch_op.create_foreign_key(
            "fk_stock_movements_from_location",
            "stock_locations",
            ["from_location_id"],
            ["id"]
        )


    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    with op.batch_alter_table(
        "users",
        schema=None
    ) as batch_op:

        batch_op.create_index(
            batch_op.f("ix_users_phone"),
            ["phone"],
            unique=True
        )


def downgrade():

    with op.batch_alter_table(
        "users",
        schema=None
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f("ix_users_phone")
        )


    with op.batch_alter_table(
        "stock_movements",
        schema=None
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_stock_movements_from_location",
            type_="foreignkey"
        )

        batch_op.drop_constraint(
            "fk_stock_movements_to_location",
            type_="foreignkey"
        )

        batch_op.drop_column("is_estimate")
        batch_op.drop_column("is_historical")
        batch_op.drop_column("movement_date")
        batch_op.drop_column("to_location_id")
        batch_op.drop_column("from_location_id")


    with op.batch_alter_table(
        "sales",
        schema=None
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f("ix_sales_sale_number")
        )

        batch_op.drop_column("is_estimate")
        batch_op.drop_column("is_historical")
        batch_op.drop_column("sale_date")


    with op.batch_alter_table(
        "sale_items",
        schema=None
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_sale_items_stock_location",
            type_="foreignkey"
        )

        batch_op.drop_column("stock_location_id")


    with op.batch_alter_table(
        "partner_transactions",
        schema=None
    ) as batch_op:

        batch_op.drop_column("notes")
        batch_op.drop_column("is_estimate")
        batch_op.drop_column("is_historical")
        batch_op.drop_column("transaction_date")


    with op.batch_alter_table(
        "money_accounts",
        schema=None
    ) as batch_op:

        batch_op.alter_column(
            "opening_balance",
            existing_type=sa.NUMERIC(
                precision=12,
                scale=2
            ),
            nullable=True,
            existing_nullable=False,
            server_default=None
        )


    with op.batch_alter_table(
        "financial_transactions",
        schema=None
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f("ix_financial_transactions_transaction_type")
        )

        batch_op.drop_index(
            batch_op.f("ix_financial_transactions_transaction_date")
        )


    with op.batch_alter_table(
        "expenses",
        schema=None
    ) as batch_op:

        batch_op.drop_column("is_estimate")
        batch_op.drop_column("is_historical")
        batch_op.drop_column("expense_date")