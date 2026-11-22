"""conversation change notifications

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01 15:00:00
"""
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

TABLES = ("messages", "handoffs", "pending_actions")


def upgrade() -> None:
    # Delivered at commit; the payload is only the conversation id (SPEC.md 6.7 events stream).
    op.execute("""
        CREATE FUNCTION notify_conversation_change() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('conversation_events', NEW.conversation_id::text);
            RETURN NULL;
        END $$ LANGUAGE plpgsql
    """)
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_notify AFTER INSERT OR UPDATE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION notify_conversation_change()")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_notify ON {table}")
    op.execute("DROP FUNCTION notify_conversation_change()")
