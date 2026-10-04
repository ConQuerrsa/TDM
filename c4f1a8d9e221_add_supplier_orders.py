"""add supplier orders and landed costs

Revision ID: c4f1a8d9e221
Revises: b71d1a9c2f11
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4f1a8d9e221"
down_revision = "b71d1a9c2f11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("supplier", sa.String(length=150), nullable=False),
        sa.Column("goods_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("order_date", sa.DateTime(), nullable=False),
        sa.Column("is_historical", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number"),
    )

    with op.batch_alter_table("supplier_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_supplier_orders_order_number"),
            ["order_number"],
            unique=True,
        )

    op.create_table(
        "supplier_order_costs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_order_id", sa.Integer(), nullable=False),
        sa.Column("cost_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("funding_type", sa.String(length=30), nullable=False),
        sa.Column("money_account_id", sa.Integer(), nullable=True),
        sa.Column("partner_id", sa.Integer(), nullable=True),
        sa.Column("cost_date", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["money_account_id"],
            ["money_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_order_id"],
            ["supplier_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("supplier_order_costs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_supplier_order_costs_supplier_order_id"),
            ["supplier_order_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("supplier_order_costs", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_supplier_order_costs_supplier_order_id")
        )

    op.drop_table("supplier_order_costs")

    with op.batch_alter_table("supplier_orders", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_supplier_orders_order_number")
        )

    op.drop_table("supplier_orders")
