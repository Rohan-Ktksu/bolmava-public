"""trade rfq quote order conversation

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27 16:30:57.458908
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('conversations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('language', sa.String(length=2), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel = 'web'", name=op.f('ck_conversations_channel')),
    sa.CheckConstraint("language IN ('te', 'en')", name=op.f('ck_conversations_language')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_conversations_org_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversations_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index('ix_conversations_owner', 'conversations', ['org_id', 'user_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('text', sa.String(length=2000), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f('ck_messages_role')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_table('pending_actions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('result_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("action IN ('create_rfq', 'confirm_order')", name=op.f('ck_pending_actions_action')),
    sa.CheckConstraint("status IN ('pending', 'confirmed', 'expired', 'cancelled')", name=op.f('ck_pending_actions_status')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_pending_actions_actor_user_id_users')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_pending_actions_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_pending_actions_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pending_actions'))
    )
    op.create_index(op.f('ix_pending_actions_conversation_id'), 'pending_actions', ['conversation_id'], unique=False)
    op.create_table('rfqs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('buyer_org_id', sa.Uuid(), nullable=False),
    sa.Column('seller_org_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('delivery_city', sa.String(length=80), nullable=False),
    sa.Column('needed_by', sa.Date(), nullable=True),
    sa.Column('note', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('open', 'quoted', 'closed', 'cancelled')", name=op.f('ck_rfqs_status')),
    sa.CheckConstraint('buyer_org_id <> seller_org_id', name=op.f('ck_rfqs_distinct_orgs')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_rfqs_quantity')),
    sa.ForeignKeyConstraint(['buyer_org_id'], ['organizations.id'], name=op.f('fk_rfqs_buyer_org_id_organizations')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_rfqs_created_by_users')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_rfqs_product_id_products')),
    sa.ForeignKeyConstraint(['seller_org_id'], ['organizations.id'], name=op.f('fk_rfqs_seller_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rfqs'))
    )
    op.create_index(op.f('ix_rfqs_buyer_org_id'), 'rfqs', ['buyer_org_id'], unique=False)
    op.create_index(op.f('ix_rfqs_seller_org_id'), 'rfqs', ['seller_org_id'], unique=False)
    op.create_table('quotes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('rfq_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_paise', sa.BigInteger(), nullable=False),
    sa.Column('discount_paise', sa.BigInteger(), nullable=False),
    sa.Column('freight_paise', sa.BigInteger(), nullable=False),
    sa.Column('tax_bp', sa.SmallInteger(), nullable=False),
    sa.Column('subtotal_paise', sa.BigInteger(), nullable=False),
    sa.Column('tax_paise', sa.BigInteger(), nullable=False),
    sa.Column('total_paise', sa.BigInteger(), nullable=False),
    sa.Column('advance_paise', sa.BigInteger(), nullable=False),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'sent', 'accepted', 'rejected', 'expired', 'superseded')", name=op.f('ck_quotes_status')),
    sa.CheckConstraint('advance_paise BETWEEN 0 AND total_paise', name=op.f('ck_quotes_advance')),
    sa.CheckConstraint('discount_paise >= 0 AND freight_paise >= 0 AND tax_paise >= 0', name=op.f('ck_quotes_non_negative')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_quotes_quantity')),
    sa.CheckConstraint('subtotal_paise = quantity * unit_price_paise - discount_paise AND subtotal_paise > 0', name=op.f('ck_quotes_subtotal')),
    sa.CheckConstraint('tax_bp BETWEEN 0 AND 10000', name=op.f('ck_quotes_tax_bp')),
    sa.CheckConstraint('total_paise = subtotal_paise + freight_paise + tax_paise', name=op.f('ck_quotes_total')),
    sa.CheckConstraint('unit_price_paise > 0', name=op.f('ck_quotes_unit_price')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_quotes_version')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_quotes_created_by_users')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_quotes_product_id_products')),
    sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], name=op.f('fk_quotes_rfq_id_rfqs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_quotes')),
    sa.UniqueConstraint('rfq_id', 'version', name=op.f('uq_quotes_rfq_id_version'))
    )
    op.create_index('uq_quotes_one_sent_per_rfq', 'quotes', ['rfq_id'], unique=True, postgresql_where=sa.text("status = 'sent'"))
    op.create_table('orders',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('quote_id', sa.Uuid(), nullable=False),
    sa.Column('quote_version', sa.Integer(), nullable=False),
    sa.Column('buyer_org_id', sa.Uuid(), nullable=False),
    sa.Column('seller_org_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('product_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_paise', sa.BigInteger(), nullable=False),
    sa.Column('discount_paise', sa.BigInteger(), nullable=False),
    sa.Column('freight_paise', sa.BigInteger(), nullable=False),
    sa.Column('tax_bp', sa.SmallInteger(), nullable=False),
    sa.Column('subtotal_paise', sa.BigInteger(), nullable=False),
    sa.Column('tax_paise', sa.BigInteger(), nullable=False),
    sa.Column('total_paise', sa.BigInteger(), nullable=False),
    sa.Column('advance_paise', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('confirmed_by', sa.Uuid(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('confirmed', 'cancelled', 'completed')", name=op.f('ck_orders_status')),
    sa.CheckConstraint('total_paise = subtotal_paise + freight_paise + tax_paise', name=op.f('ck_orders_total')),
    sa.ForeignKeyConstraint(['buyer_org_id'], ['organizations.id'], name=op.f('fk_orders_buyer_org_id_organizations')),
    sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], name=op.f('fk_orders_confirmed_by_users')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_orders_product_id_products')),
    sa.ForeignKeyConstraint(['quote_id'], ['quotes.id'], name=op.f('fk_orders_quote_id_quotes')),
    sa.ForeignKeyConstraint(['seller_org_id'], ['organizations.id'], name=op.f('fk_orders_seller_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
    sa.UniqueConstraint('buyer_org_id', 'idempotency_key', name=op.f('uq_orders_buyer_org_id_idempotency_key')),
    sa.UniqueConstraint('quote_id', name=op.f('uq_orders_quote_id'))
    )
    op.create_index(op.f('ix_orders_buyer_org_id'), 'orders', ['buyer_org_id'], unique=False)
    op.create_index(op.f('ix_orders_seller_org_id'), 'orders', ['seller_org_id'], unique=False)
    op.add_column('stock_movements', sa.Column('order_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_stock_movements_order_id_orders'), 'stock_movements', 'orders', ['order_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_stock_movements_order_id_orders'), 'stock_movements', type_='foreignkey')
    op.drop_column('stock_movements', 'order_id')
    op.drop_index(op.f('ix_orders_seller_org_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_buyer_org_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index('uq_quotes_one_sent_per_rfq', table_name='quotes', postgresql_where=sa.text("status = 'sent'"))
    op.drop_table('quotes')
    op.drop_index(op.f('ix_rfqs_seller_org_id'), table_name='rfqs')
    op.drop_index(op.f('ix_rfqs_buyer_org_id'), table_name='rfqs')
    op.drop_table('rfqs')
    op.drop_index(op.f('ix_pending_actions_conversation_id'), table_name='pending_actions')
    op.drop_table('pending_actions')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_conversations_owner', table_name='conversations')
    op.drop_table('conversations')
