"""enable recurring mailing campaign runs

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-07-28
"""

from alembic import op


revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("mailing_deliveries") as batch_op:
        batch_op.drop_constraint("uq_mailing_delivery_recipient", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mailing_delivery_run_recipient",
            ["run_id", "subscriber_id"],
        )


def downgrade():
    # Prima di ripristinare il vincolo storico conserva soltanto la consegna
    # più recente per coppia campagna/destinatario.
    op.execute(
        """
        DELETE FROM mailing_deliveries AS older
        USING mailing_deliveries AS newer
        WHERE older.campaign_id = newer.campaign_id
          AND older.subscriber_id = newer.subscriber_id
          AND older.id < newer.id
        """
    )
    with op.batch_alter_table("mailing_deliveries") as batch_op:
        batch_op.drop_constraint("uq_mailing_delivery_run_recipient", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mailing_delivery_recipient",
            ["campaign_id", "subscriber_id"],
        )
