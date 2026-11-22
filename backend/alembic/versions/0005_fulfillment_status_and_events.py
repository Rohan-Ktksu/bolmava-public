"""fulfillment status and events

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 16:12:46.941277
"""
import sqlalchemy as sa
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('fulfillment_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('dispatched', 'delivered', 'accepted', 'cancelled')", name=op.f('ck_fulfillment_events_status')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_fulfillment_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_fulfillment_events_order_id_orders')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fulfillment_events'))
    )
    op.create_index(op.f('ix_fulfillment_events_order_id'), 'fulfillment_events', ['order_id'], unique=False)
    op.add_column('orders', sa.Column('fulfillment_status', sa.String(length=16), server_default='pending', nullable=False))
    op.create_check_constraint(op.f('ck_orders_fulfillment_status'), 'orders', "fulfillment_status IN ('pending', 'dispatched', 'delivered', 'accepted')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_orders_fulfillment_status'), 'orders', type_='check')
    op.drop_column('orders', 'fulfillment_status')
    op.drop_index(op.f('ix_fulfillment_events_order_id'), table_name='fulfillment_events')
    op.drop_table('fulfillment_events')
