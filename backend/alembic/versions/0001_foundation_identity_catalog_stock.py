"""foundation identity catalog stock

Revision ID: 0001
Revises: 
Create Date: 2026-10-27 12:23:11.479941
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('organizations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=False),
    sa.Column('state', sa.String(length=80), nullable=False),
    sa.Column('can_sell', sa.Boolean(), nullable=False),
    sa.Column('can_buy', sa.Boolean(), nullable=False),
    sa.Column('verification_status', sa.String(length=32), nullable=False),
    sa.Column('is_fictional', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("verification_status IN ('simulated_unverified', 'simulated_verified')", name=op.f('ck_organizations_verification_status')),
    sa.CheckConstraint('can_sell OR can_buy', name=op.f('ck_organizations_capability')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organizations'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('preferred_language', sa.String(length=2), nullable=False),
    sa.Column('is_fictional', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("preferred_language IN ('te', 'en')", name=op.f('ck_users_language')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('audit_events',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_audit_events_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index(op.f('ix_audit_events_org_id'), 'audit_events', ['org_id'], unique=False)
    op.create_table('memberships',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('admin', 'catalog_manager', 'purchaser', 'viewer')", name=op.f('ck_memberships_role')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_memberships_org_id_organizations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_memberships_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memberships')),
    sa.UniqueConstraint('org_id', 'user_id', name=op.f('uq_memberships_org_id_user_id'))
    )
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('sku', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_te', sa.String(length=200), nullable=True),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('brand', sa.String(length=80), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=False),
    sa.Column('rating_amps', sa.SmallInteger(), nullable=False),
    sa.Column('voltage_v', sa.SmallInteger(), nullable=False),
    sa.Column('ways', sa.SmallInteger(), nullable=False),
    sa.Column('unit', sa.String(length=16), nullable=False),
    sa.Column('pack_size', sa.Integer(), nullable=False),
    sa.Column('moq', sa.Integer(), nullable=False),
    sa.Column('price_paise', sa.BigInteger(), nullable=False),
    sa.Column('available_qty', sa.Integer(), nullable=False),
    sa.Column('lead_time_days', sa.SmallInteger(), nullable=False),
    sa.Column('delivery_cities', postgresql.ARRAY(sa.String(length=80)), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category = 'electrical_switch'", name=op.f('ck_products_category')),
    sa.CheckConstraint("pack_size >= 1 AND (unit <> 'piece' OR pack_size = 1)", name=op.f('ck_products_pack_size')),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_products_status')),
    sa.CheckConstraint("unit IN ('piece', 'box')", name=op.f('ck_products_unit')),
    sa.CheckConstraint('available_qty >= 0', name=op.f('ck_products_available_qty')),
    sa.CheckConstraint('lead_time_days >= 0', name=op.f('ck_products_lead_time_days')),
    sa.CheckConstraint('moq >= 1', name=op.f('ck_products_moq')),
    sa.CheckConstraint('price_paise > 0 AND price_paise <= 1000000000000', name=op.f('ck_products_price_paise')),
    sa.CheckConstraint('rating_amps > 0', name=op.f('ck_products_rating_amps')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_products_version')),
    sa.CheckConstraint('voltage_v > 0', name=op.f('ck_products_voltage_v')),
    sa.CheckConstraint('ways IN (1, 2)', name=op.f('ck_products_ways')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_products_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
    sa.UniqueConstraint('org_id', 'sku', name=op.f('uq_products_org_id_sku'))
    )
    op.create_index('ix_products_discovery', 'products', ['status', 'price_paise'], unique=False)
    op.create_table('stock_movements',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('delta', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=16), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('resulting_qty', sa.Integer(), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reason IN ('restock', 'correction', 'damage', 'order', 'order_cancel')", name=op.f('ck_stock_movements_reason')),
    sa.CheckConstraint('delta <> 0', name=op.f('ck_stock_movements_delta')),
    sa.CheckConstraint('resulting_qty >= 0', name=op.f('ck_stock_movements_resulting_qty')),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_stock_movements_actor_user_id_users')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_stock_movements_org_id_organizations')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_stock_movements_product_id_products')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_movements')),
    sa.UniqueConstraint('org_id', 'idempotency_key', name=op.f('uq_stock_movements_org_id_idempotency_key'))
    )
    op.create_index(op.f('ix_stock_movements_product_id'), 'stock_movements', ['product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_stock_movements_product_id'), table_name='stock_movements')
    op.drop_table('stock_movements')
    op.drop_index('ix_products_discovery', table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_memberships_user_id'), table_name='memberships')
    op.drop_table('memberships')
    op.drop_index(op.f('ix_audit_events_org_id'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('organizations')
