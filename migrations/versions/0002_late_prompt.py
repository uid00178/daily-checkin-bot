from alembic import op
import sqlalchemy as sa

revision = "0002_late_prompt"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("daily_state", sa.Column("late_prompt_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("daily_state", sa.Column("late_prompt_response_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("daily_state", sa.Column("late_notify_contacts", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("daily_state", "late_notify_contacts")
    op.drop_column("daily_state", "late_prompt_response_at")
    op.drop_column("daily_state", "late_prompt_sent_at")