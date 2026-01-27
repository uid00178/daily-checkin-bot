from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_user_id", sa.Integer, nullable=False, unique=True, index=True),
        sa.Column("tg_chat_id", sa.Integer, nullable=False, index=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("checkin_time_local", sa.Time(), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "PAUSED", "DISABLED", name="userstatus")),
        sa.Column("pause_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unreachable_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "trusted_contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("contact_tg_user_id", sa.Integer, nullable=False),
        sa.Column("contact_chat_id", sa.Integer, nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "DECLINED", "REVOKED", name="contactstatus"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "contact_tg_user_id"),
    )

    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("date_local", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("photo_file_id", sa.String(length=512), nullable=False),
        sa.Column("photo_s3_key", sa.String(length=512), nullable=True),
        sa.Column("geo_lat", sa.Float, nullable=True),
        sa.Column("geo_lon", sa.Float, nullable=True),
        sa.Column("is_late", sa.Boolean, default=False),
    )

    op.create_table(
        "daily_state",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("date_local", sa.Date, primary_key=True),
        sa.Column("due_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.Enum("PENDING", "DONE", "MISSED", name="dailystateenum"),
            nullable=False,
        ),
        sa.Column("reminders_sent_count", sa.Integer, default=0),
        sa.Column("escalation_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), unique=True, index=True),
        sa.Column("type", sa.String(length=64)),
        sa.Column("user_id", sa.Integer, index=True),
        sa.Column("target_chat_id", sa.Integer, index=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32)),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("notification_log")
    op.drop_table("daily_state")
    op.drop_table("checkins")
    op.drop_table("trusted_contacts")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS dailystateenum")
    op.execute("DROP TYPE IF EXISTS contactstatus")
    op.execute("DROP TYPE IF EXISTS userstatus")