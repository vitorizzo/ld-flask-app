"""add mailing campaign templates, attachments, schedules and runs

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mailing_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_mailing_templates_name"),
    )
    op.create_index("ix_mailing_templates_is_active", "mailing_templates", ["is_active"])

    with op.batch_alter_table("mailing_campaigns") as batch_op:
        batch_op.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_mailing_campaigns_template_id",
            "mailing_templates",
            ["template_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_mailing_campaigns_template_id", ["template_id"])

    op.create_table(
        "mailing_campaign_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("file_size > 0", name="ck_mailing_campaign_attachment_size"),
        sa.UniqueConstraint("storage_path", name="uq_mailing_campaign_attachments_storage_path"),
    )
    op.create_index(
        "ix_mailing_campaign_attachments_campaign_id",
        "mailing_campaign_attachments",
        ["campaign_id"],
    )

    op.create_table(
        "mailing_campaign_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="single"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_value", sa.Integer(), nullable=True),
        sa.Column("interval_unit", sa.String(length=12), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_runs", sa.Integer(), nullable=True),
        sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "mode IN ('single', 'periodic', 'multiple', 'until')",
            name="ck_mailing_campaign_schedule_mode",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_mailing_campaign_schedule_status",
        ),
        sa.CheckConstraint(
            "interval_unit IS NULL OR interval_unit IN ('day', 'week', 'month')",
            name="ck_mailing_campaign_schedule_interval_unit",
        ),
        sa.CheckConstraint(
            "interval_value IS NULL OR interval_value > 0",
            name="ck_mailing_campaign_schedule_interval_value",
        ),
        sa.CheckConstraint(
            "max_runs IS NULL OR max_runs > 0",
            name="ck_mailing_campaign_schedule_max_runs",
        ),
        sa.CheckConstraint(
            "completed_runs >= 0",
            name="ck_mailing_campaign_schedule_completed_runs",
        ),
        sa.UniqueConstraint("campaign_id", name="uq_mailing_campaign_schedules_campaign"),
    )
    op.create_index(
        "ix_mailing_campaign_schedules_campaign_id",
        "mailing_campaign_schedules",
        ["campaign_id"],
    )
    op.create_index(
        "ix_mailing_campaign_schedules_status",
        "mailing_campaign_schedules",
        ["status"],
    )
    op.create_index(
        "ix_mailing_campaign_schedules_next_run_at",
        "mailing_campaign_schedules",
        ["next_run_at"],
    )
    op.create_index(
        "ix_mailing_campaign_schedules_due",
        "mailing_campaign_schedules",
        ["status", "next_run_at"],
    )

    op.create_table(
        "mailing_campaign_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("run_number > 0", name="ck_mailing_campaign_run_number"),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'scheduled', 'legacy')",
            name="ck_mailing_campaign_run_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'queued', 'sending', 'sent', 'failed', 'cancelled')",
            name="ck_mailing_campaign_run_status",
        ),
        sa.UniqueConstraint("campaign_id", "run_number", name="uq_mailing_campaign_run_number"),
    )
    op.create_index("ix_mailing_campaign_runs_campaign_id", "mailing_campaign_runs", ["campaign_id"])
    op.create_index("ix_mailing_campaign_runs_scheduled_for", "mailing_campaign_runs", ["scheduled_for"])
    op.create_index("ix_mailing_campaign_runs_status", "mailing_campaign_runs", ["status"])
    op.create_index(
        "ix_mailing_campaign_runs_campaign_status",
        "mailing_campaign_runs",
        ["campaign_id", "status"],
    )

    with op.batch_alter_table("mailing_deliveries") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_mailing_deliveries_run_id",
            "mailing_campaign_runs",
            ["run_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_mailing_deliveries_run_id", ["run_id"])

    op.execute(
        """
        INSERT INTO mailing_campaign_runs (
            campaign_id,
            run_number,
            trigger_type,
            scheduled_for,
            status,
            recipient_count,
            sent_count,
            failed_count,
            started_at,
            completed_at,
            created_at
        )
        SELECT
            campaign.id,
            1,
            'legacy',
            COALESCE(campaign.started_at, campaign.created_at),
            CASE
                WHEN campaign.status = 'draft' THEN 'pending'
                ELSE campaign.status
            END,
            campaign.recipient_count,
            campaign.sent_count,
            campaign.failed_count,
            campaign.started_at,
            campaign.completed_at,
            campaign.created_at
        FROM mailing_campaigns AS campaign
        WHERE EXISTS (
            SELECT 1
            FROM mailing_deliveries AS delivery
            WHERE delivery.campaign_id = campaign.id
        )
        """
    )
    op.execute(
        """
        UPDATE mailing_deliveries AS delivery
        SET run_id = run.id
        FROM mailing_campaign_runs AS run
        WHERE run.campaign_id = delivery.campaign_id
          AND run.run_number = 1
          AND run.trigger_type = 'legacy'
        """
    )


def downgrade():
    with op.batch_alter_table("mailing_deliveries") as batch_op:
        batch_op.drop_index("ix_mailing_deliveries_run_id")
        batch_op.drop_constraint("fk_mailing_deliveries_run_id", type_="foreignkey")
        batch_op.drop_column("run_id")

    op.drop_table("mailing_campaign_runs")
    op.drop_table("mailing_campaign_schedules")
    op.drop_table("mailing_campaign_attachments")

    with op.batch_alter_table("mailing_campaigns") as batch_op:
        batch_op.drop_index("ix_mailing_campaigns_template_id")
        batch_op.drop_constraint("fk_mailing_campaigns_template_id", type_="foreignkey")
        batch_op.drop_column("template_id")

    op.drop_table("mailing_templates")
