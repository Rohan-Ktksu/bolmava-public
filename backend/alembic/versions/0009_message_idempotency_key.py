"""message idempotency key

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01 14:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('idempotency_key', sa.String(length=80), nullable=True))
    op.create_unique_constraint(op.f('uq_messages_conversation_id_idempotency_key'), 'messages', ['conversation_id', 'idempotency_key'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_messages_conversation_id_idempotency_key'), 'messages', type_='unique')
    op.drop_column('messages', 'idempotency_key')
