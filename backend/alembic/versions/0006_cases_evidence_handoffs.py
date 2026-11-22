"""cases evidence handoffs

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28 16:16:53.526994
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cases',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('buyer_org_id', sa.Uuid(), nullable=False),
    sa.Column('seller_org_id', sa.Uuid(), nullable=False),
    sa.Column('category', sa.String(length=24), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=False),
    sa.Column('urgency', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('assigned_to', sa.Uuid(), nullable=True),
    sa.Column('resolution', sa.String(length=2000), nullable=True),
    sa.Column('reopen_count', sa.Integer(), nullable=False),
    sa.Column('opened_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("category IN ('damaged', 'wrong_product', 'missing_quantity', 'delay', 'quality', 'payment', 'other')", name=op.f('ck_cases_category')),
    sa.CheckConstraint("status IN ('open', 'assigned', 'investigating', 'resolved', 'closed')", name=op.f('ck_cases_status')),
    sa.CheckConstraint("status IN ('open', 'resolved', 'closed') OR assigned_to IS NOT NULL", name=op.f('ck_cases_assignee')),
    sa.CheckConstraint("status NOT IN ('resolved', 'closed') OR resolution IS NOT NULL", name=op.f('ck_cases_resolution')),
    sa.CheckConstraint("urgency IN ('low', 'normal', 'high')", name=op.f('ck_cases_urgency')),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], name=op.f('fk_cases_assigned_to_users')),
    sa.ForeignKeyConstraint(['buyer_org_id'], ['organizations.id'], name=op.f('fk_cases_buyer_org_id_organizations')),
    sa.ForeignKeyConstraint(['opened_by'], ['users.id'], name=op.f('fk_cases_opened_by_users')),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_cases_order_id_orders')),
    sa.ForeignKeyConstraint(['seller_org_id'], ['organizations.id'], name=op.f('fk_cases_seller_org_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cases'))
    )
    op.create_index(op.f('ix_cases_buyer_org_id'), 'cases', ['buyer_org_id'], unique=False)
    op.create_index(op.f('ix_cases_order_id'), 'cases', ['order_id'], unique=False)
    op.create_index(op.f('ix_cases_seller_org_id'), 'cases', ['seller_org_id'], unique=False)
    op.create_table('case_evidence',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('added_by', sa.Uuid(), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_case_evidence_sha256')),
    sa.CheckConstraint('size_bytes > 0 AND size_bytes <= 20971520', name=op.f('ck_case_evidence_size')),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_case_evidence_added_by_users')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_evidence_case_id_cases')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_evidence'))
    )
    op.create_index(op.f('ix_case_evidence_case_id'), 'case_evidence', ['case_id'], unique=False)
    op.create_table('case_updates',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('visibility', sa.String(length=16), nullable=False),
    sa.Column('body', sa.String(length=2000), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("visibility IN ('parties', 'internal')", name=op.f('ck_case_updates_visibility')),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_case_updates_author_id_users')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_updates_case_id_cases')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_updates'))
    )
    op.create_index(op.f('ix_case_updates_case_id'), 'case_updates', ['case_id'], unique=False)
    op.create_table('handoffs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('case_id', sa.Uuid(), nullable=True),
    sa.Column('urgency', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('requested_by', sa.Uuid(), nullable=False),
    sa.Column('assigned_to', sa.Uuid(), nullable=True),
    sa.Column('cancelled_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status = 'queued' OR assigned_to IS NOT NULL", name=op.f('ck_handoffs_assignee')),
    sa.CheckConstraint("status IN ('queued', 'assigned', 'released')", name=op.f('ck_handoffs_status')),
    sa.CheckConstraint("urgency IN ('low', 'normal', 'high')", name=op.f('ck_handoffs_urgency')),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], name=op.f('fk_handoffs_assigned_to_users')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_handoffs_case_id_cases')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_handoffs_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name=op.f('fk_handoffs_org_id_organizations')),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_handoffs_requested_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_handoffs'))
    )
    op.create_index(op.f('ix_handoffs_conversation_id'), 'handoffs', ['conversation_id'], unique=False)
    op.create_index('uq_handoffs_one_active', 'handoffs', ['conversation_id'], unique=True, postgresql_where=sa.text("status IN ('queued', 'assigned')"))

    # Autogenerate skips check constraints on existing tables: allow human agent messages.
    op.drop_constraint(op.f('ck_messages_role'), 'messages', type_='check')
    op.create_check_constraint(op.f('ck_messages_role'), 'messages', "role IN ('user', 'assistant', 'agent')")

def downgrade() -> None:
    op.execute("DELETE FROM messages WHERE role = 'agent'")
    op.drop_constraint(op.f('ck_messages_role'), 'messages', type_='check')
    op.create_check_constraint(op.f('ck_messages_role'), 'messages', "role IN ('user', 'assistant')")
    op.drop_index('uq_handoffs_one_active', table_name='handoffs', postgresql_where=sa.text("status IN ('queued', 'assigned')"))
    op.drop_index(op.f('ix_handoffs_conversation_id'), table_name='handoffs')
    op.drop_table('handoffs')
    op.drop_index(op.f('ix_case_updates_case_id'), table_name='case_updates')
    op.drop_table('case_updates')
    op.drop_index(op.f('ix_case_evidence_case_id'), table_name='case_evidence')
    op.drop_table('case_evidence')
    op.drop_index(op.f('ix_cases_seller_org_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_order_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_buyer_org_id'), table_name='cases')
    op.drop_table('cases')
