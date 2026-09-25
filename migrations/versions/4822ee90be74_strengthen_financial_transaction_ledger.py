"""Strengthen financial transaction ledger

Revision ID: 4822ee90be74
Revises:
Create Date: 2026-09-23 15:43:14.036818

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4822ee90be74"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Existing financial transaction records need safe values
    # for the new required fields.

    with op.batch_alter_table(
        "financial_transactions",
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
                "reversal_of_id",
                sa.Integer(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(length=50),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "source_id",
                sa.Integer(),
                nullable=True
            )
        )

        batch_op.add_column(
            sa.Column(
                "notes",
                sa.Text(),
                nullable=True
            )
        )

        batch_op.create_foreign_key(
            "fk_financial_transactions_reversal_of",
            "financial_transactions",
            ["reversal_of_id"],
            ["id"]
        )


def downgrade():

    with op.batch_alter_table(
        "financial_transactions",
        schema=None
    ) as batch_op:

        batch_op.drop_constraint(
            "fk_financial_transactions_reversal_of",
            type_="foreignkey"
        )

        batch_op.drop_column("notes")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_type")
        batch_op.drop_column("reversal_of_id")
        batch_op.drop_column("is_estimate")
        batch_op.drop_column("is_historical")
        batch_op.drop_column("transaction_date")