"""bind quotes to the product terms they were drafted with

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('quotes', sa.Column('product_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # Existing quotes get the product's current terms: the best record available for them.
    op.execute("""
        UPDATE quotes q SET product_snapshot = jsonb_build_object(
            'sku', p.sku, 'name', p.name, 'name_te', p.name_te, 'brand', p.brand, 'model', p.model,
            'rating_amps', p.rating_amps, 'voltage_v', p.voltage_v, 'ways', p.ways, 'unit', p.unit, 'pack_size', p.pack_size)
        FROM products p WHERE p.id = q.product_id
    """)
    op.alter_column('quotes', 'product_snapshot', nullable=False)


def downgrade() -> None:
    op.drop_column('quotes', 'product_snapshot')
