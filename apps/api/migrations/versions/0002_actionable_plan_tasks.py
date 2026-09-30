"""Store the concrete action and completion check for every plan task."""

from alembic import op
import sqlalchemy as sa

revision = "0002_actionable_plan_tasks"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("migration_tasks")
    }
    if "next_action" not in columns:
        op.add_column(
            "migration_tasks",
            sa.Column("next_action", sa.Text(), nullable=False, server_default=""),
        )
    if "done_when" not in columns:
        op.add_column(
            "migration_tasks",
            sa.Column("done_when", sa.Text(), nullable=False, server_default=""),
        )


def downgrade():
    bind = op.get_bind()
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("migration_tasks")
    }
    if "done_when" in columns:
        op.drop_column("migration_tasks", "done_when")
    if "next_action" in columns:
        op.drop_column("migration_tasks", "next_action")
