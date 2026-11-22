"""staff grants and simulated payments

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28 16:08:31.220237
"""
import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('staff_grants',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("role IN ('finance', 'support')", name=op.f('ck_staff_grants_role')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_staff_grants_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_grants'))
    )
    op.create_index('uq_staff_grants_active', 'staff_grants', ['user_id', 'role'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_table('payment_requests',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=16), nullable=False),
    sa.Column('amount_paise', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('quote_version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('requested_by', sa.Uuid(), nullable=False),
    sa.Column('decided_by', sa.Uuid(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.String(length=500), nullable=True),
    sa.Column('approval_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency = 'INR'", name=op.f('ck_payment_requests_currency')),
    sa.CheckConstraint("purpose IN ('advance', 'balance')", name=op.f('ck_payment_requests_purpose')),
    sa.CheckConstraint("status IN ('pending_approval', 'approved', 'rejected', 'recorded', 'expired', 'cancelled')", name=op.f('ck_payment_requests_status')),
    sa.CheckConstraint('amount_paise > 0', name=op.f('ck_payment_requests_amount')),
    sa.CheckConstraint('decided_by <> requested_by', name=op.f('ck_payment_requests_maker_checker')),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_payment_requests_decided_by_users')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payment_requests_order_id_orders')),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_payment_requests_requested_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_requests'))
    )
    op.create_index(op.f('ix_payment_requests_order_id'), 'payment_requests', ['order_id'], unique=False)
    op.create_index('uq_payment_requests_one_open', 'payment_requests', ['order_id'], unique=True, postgresql_where=sa.text("status IN ('pending_approval', 'approved')"))
    op.create_table('payment_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('amount_paise', sa.BigInteger(), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=True),
    sa.Column('reverses_event_id', sa.Uuid(), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('recorded_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(kind = 'receipt' AND request_id IS NOT NULL AND reverses_event_id IS NULL) OR (kind = 'reversal' AND reverses_event_id IS NOT NULL AND request_id IS NULL)", name=op.f('ck_payment_events_kind')),
    sa.CheckConstraint('amount_paise > 0', name=op.f('ck_payment_events_amount')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payment_events_order_id_orders')),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], name=op.f('fk_payment_events_recorded_by_users')),
    sa.ForeignKeyConstraint(['request_id'], ['payment_requests.id'], name=op.f('fk_payment_events_request_id_payment_requests')),
    sa.ForeignKeyConstraint(['reverses_event_id'], ['payment_events.id'], name=op.f('fk_payment_events_reverses_event_id_payment_events')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_events')),
    sa.UniqueConstraint('request_id', name=op.f('uq_payment_events_request_id')),
    sa.UniqueConstraint('reverses_event_id', name=op.f('uq_payment_events_reverses_event_id'))
    )
    op.create_index(op.f('ix_payment_events_order_id'), 'payment_events', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_events_order_id'), table_name='payment_events')
    op.drop_table('payment_events')
    op.drop_index('uq_payment_requests_one_open', table_name='payment_requests', postgresql_where=sa.text("status IN ('pending_approval', 'approved')"))
    op.drop_index(op.f('ix_payment_requests_order_id'), table_name='payment_requests')
    op.drop_table('payment_requests')
    op.drop_index('uq_staff_grants_active', table_name='staff_grants', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_table('staff_grants')
