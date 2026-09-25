"""Track creator of partner transactions

Revision ID: 6ae213b2659e
Revises: 0d403b79dc3b
Create Date: 2026-09-25 02:46:38.206686

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6ae213b2659e'
down_revision = '0d403b79dc3b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('partner_transactions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'created_by_id',
                sa.Integer(),
                nullable=True
            )
        )

        batch_op.create_foreign_key(
            'fk_partner_transactions_created_by_id_users',
            'users',
            ['created_by_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('partner_transactions', schema=None) as batch_op:

        batch_op.drop_constraint(
            'fk_partner_transactions_created_by_id_users',
            type_='foreignkey'
        )

        batch_op.drop_column(
            'created_by_id'
        )
    # ### end Alembic commands ###
