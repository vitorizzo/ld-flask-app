"""add mailing list

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
"""
from alembic import op
import sqlalchemy as sa

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("mailing_subscribers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(255), nullable=False), sa.Column("email_normalized", sa.String(255), nullable=False), sa.Column("name", sa.String(160)), sa.Column("status", sa.String(20), nullable=False, server_default="subscribed"), sa.Column("source", sa.String(40), nullable=False, server_default="manual"), sa.Column("consent_at", sa.DateTime(timezone=True)), sa.Column("unsubscribed_at", sa.DateTime(timezone=True)), sa.Column("unsubscribe_token", sa.String(64), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("email_normalized", name="uq_mailing_subscribers_email"))
    op.create_index("ix_mailing_subscribers_email_normalized", "mailing_subscribers", ["email_normalized"]); op.create_index("ix_mailing_subscribers_status", "mailing_subscribers", ["status"])
    op.create_table("mailing_campaigns", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("subject", sa.String(255), nullable=False), sa.Column("html_body", sa.Text(), nullable=False), sa.Column("account_code", sa.String(50), nullable=False, server_default="general"), sa.Column("status", sa.String(20), nullable=False, server_default="draft"), sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("user.id")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_mailing_campaigns_status", "mailing_campaigns", ["status"])
    op.create_table("mailing_deliveries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"), nullable=False), sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("mailing_subscribers.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("error_message", sa.Text()), sa.Column("sent_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("campaign_id", "subscriber_id", name="uq_mailing_delivery_recipient"))
    op.create_index("ix_mailing_deliveries_campaign_id", "mailing_deliveries", ["campaign_id"]); op.create_index("ix_mailing_deliveries_subscriber_id", "mailing_deliveries", ["subscriber_id"]); op.create_index("ix_mailing_deliveries_status", "mailing_deliveries", ["status"])
    op.execute("UPDATE menus SET route='/mailing-list/' WHERE lower(name)=lower('Mailing List')")

def downgrade():
    op.execute("UPDATE menus SET route='/mailing_list' WHERE lower(name)=lower('Mailing List')")
    op.drop_table("mailing_deliveries"); op.drop_table("mailing_campaigns"); op.drop_table("mailing_subscribers")
