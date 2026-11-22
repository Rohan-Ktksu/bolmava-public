"""organization registration idempotency key

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-22 12:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('created_by', sa.Uuid(), nullable=True))
    op.add_column('organizations', sa.Column('idempotency_key', sa.String(length=80), nullable=True))
    op.create_foreign_key(op.f('fk_organizations_created_by_users'), 'organizations', 'users', ['created_by'], ['id'])
    op.create_unique_constraint(op.f('uq_organizations_created_by_idempotency_key'), 'organizations', ['created_by', 'idempotency_key'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_organizations_created_by_idempotency_key'), 'organizations', type_='unique')
    op.drop_constraint(op.f('fk_organizations_created_by_users'), 'organizations', type_='foreignkey')
    op.drop_column('organizations', 'idempotency_key')
    op.drop_column('organizations', 'created_by')
