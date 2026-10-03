"""TDM v1.1 money, credit sales and product variants

Revision ID: b71d1a9c2f11
Revises: 6ae213b2659e
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = 'b71d1a9c2f11'
down_revision = '6ae213b2659e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales') as batch:
        batch.alter_column('money_account_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('listed_total', sa.Numeric(12,2), nullable=True))
        batch.add_column(sa.Column('amount_paid', sa.Numeric(12,2), nullable=False, server_default='0'))
        batch.add_column(sa.Column('outstanding_amount', sa.Numeric(12,2), nullable=False, server_default='0'))
        batch.add_column(sa.Column('payment_status', sa.String(30), nullable=False, server_default='paid'))
        batch.add_column(sa.Column('customer_name', sa.String(120), nullable=True))
        batch.add_column(sa.Column('customer_contact', sa.String(80), nullable=True))

    op.create_table('product_variants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('size', sa.String(50)), sa.Column('color', sa.String(50)),
        sa.Column('sku', sa.String(80), unique=True),
        sa.Column('cost_price', sa.Numeric(12,2), nullable=False, server_default='0'),
        sa.Column('selling_price', sa.Numeric(12,2), nullable=False, server_default='0'),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('low_stock_level', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('first_stocked_at', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_index('ix_product_variants_product_id','product_variants',['product_id'])

    op.create_table('sale_payments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('sale_id',sa.Integer(),sa.ForeignKey('sales.id'),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('money_account_id',sa.Integer(),sa.ForeignKey('money_accounts.id'),nullable=False),
        sa.Column('payment_method',sa.String(30),nullable=False),
        sa.Column('payment_date',sa.DateTime(),nullable=False),
        sa.Column('notes',sa.Text()),
        sa.Column('recorded_by_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_sale_payments_sale_id','sale_payments',['sale_id'])

    op.create_table('other_income',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('income_type',sa.String(60),nullable=False),
        sa.Column('description',sa.String(200),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('money_account_id',sa.Integer(),sa.ForeignKey('money_accounts.id'),nullable=False),
        sa.Column('income_date',sa.DateTime(),nullable=False),
        sa.Column('notes',sa.Text()),
        sa.Column('recorded_by_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False))

    conn=op.get_bind(); now=datetime.utcnow()
    # Existing sales were recorded as fully paid under v1.0.
    conn.execute(sa.text("UPDATE sales SET listed_total=total_amount, amount_paid=total_amount, outstanding_amount=0, payment_status='paid'"))
    # Known real v1.0 sale: Iplangwe was agreed at R400, R200 received, R200 still owed.
    # Guarded by the exact sale number and old R200 value so this cannot alter an unrelated record.
    conn.execute(sa.text("""UPDATE sales SET total_amount=400, listed_total=400, amount_paid=200,
        outstanding_amount=200, payment_status='partially_paid', customer_name=COALESCE(customer_name,'Customer not recorded')
        WHERE sale_number='TDM-260930-0001' AND total_amount=200"""))
    conn.execute(sa.text("""UPDATE sale_items SET unit_price=400, line_total=400
        WHERE sale_id IN (SELECT id FROM sales WHERE sale_number='TDM-260930-0001') AND line_total=200 AND quantity=1"""))

    # Create one compatibility variant for every existing product, preserving live stock exactly.
    rows=conn.execute(sa.text("SELECT id,size,color,cost_price,selling_price,quantity,low_stock_level,created_at FROM products")).mappings().all()
    for r in rows:
        conn.execute(sa.text("""INSERT INTO product_variants
            (product_id,size,color,cost_price,selling_price,quantity,low_stock_level,first_stocked_at,is_active,created_at,updated_at)
            VALUES (:product_id,:size,:color,:cost,:sell,:qty,:low,:first,1,:now,:now)"""),
            dict(product_id=r['id'],size=r['size'],color=r['color'],cost=r['cost_price'],sell=r['selling_price'],qty=r['quantity'],low=r['low_stock_level'],first=r['created_at'],now=now))


def downgrade():
    op.drop_table('other_income'); op.drop_index('ix_sale_payments_sale_id',table_name='sale_payments'); op.drop_table('sale_payments')
    op.drop_index('ix_product_variants_product_id',table_name='product_variants'); op.drop_table('product_variants')
    with op.batch_alter_table('sales') as batch:
        for c in ['customer_contact','customer_name','payment_status','outstanding_amount','amount_paid','listed_total']:
            batch.drop_column(c)
