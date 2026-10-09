"""Audit supplier cost reversals and link inventory receipts.

Revision ID: d8e2b6a41001
Revises: c4f1a8d9e221
"""
from alembic import op
import sqlalchemy as sa
revision = 'd8e2b6a41001'
down_revision = 'c4f1a8d9e221'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('supplier_order_costs') as batch:
        batch.add_column(sa.Column('partner_transaction_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_supplier_cost_partner_transaction', 'partner_transactions', ['partner_transaction_id'], ['id'])
        batch.create_unique_constraint('uq_supplier_cost_partner_transaction', ['partner_transaction_id'])
    op.create_table('supplier_cost_reversals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cost_id', sa.Integer(), sa.ForeignKey('supplier_order_costs.id'), nullable=False, unique=True),
        sa.Column('original_partner_transaction_id', sa.Integer(), sa.ForeignKey('partner_transactions.id'), unique=True),
        sa.Column('partner_transaction_id', sa.Integer(), sa.ForeignKey('partner_transactions.id'), unique=True),
        sa.Column('financial_transaction_id', sa.Integer(), sa.ForeignKey('financial_transactions.id'), unique=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('supplier_order_receipts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('supplier_order_id', sa.Integer(), sa.ForeignKey('supplier_orders.id'), nullable=False, unique=True),
        sa.Column('purchase_id', sa.Integer(), sa.ForeignKey('purchases.id'), nullable=False, unique=True),
        sa.Column('received_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('supplier_order_receipts')
    op.drop_table('supplier_cost_reversals')
    with op.batch_alter_table('supplier_order_costs') as batch:
        batch.drop_constraint('uq_supplier_cost_partner_transaction', type_='unique')
        batch.drop_constraint('fk_supplier_cost_partner_transaction', type_='foreignkey')
        batch.drop_column('partner_transaction_id')
