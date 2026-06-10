"""add product platform catalog

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-06-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_platform_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cod_art", sa.String(length=255), nullable=False),
        sa.Column("id_art", sa.BigInteger(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cod_art"], ["articoli.cod_art"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_art"], ["articoli.id_art"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cod_art", "platform", name="uq_product_platform_links_cod_art_platform"),
    )
    op.create_index("ix_product_platform_links_cod_art", "product_platform_links", ["cod_art"], unique=False)
    op.create_index("ix_product_platform_links_external_id", "product_platform_links", ["external_id"], unique=False)
    op.create_index("ix_product_platform_links_id_art", "product_platform_links", ["id_art"], unique=False)
    op.create_index("ix_product_platform_links_platform", "product_platform_links", ["platform"], unique=False)
    op.create_index("ix_product_platform_links_platform_status", "product_platform_links", ["platform", "status"], unique=False)
    op.create_index("ix_product_platform_links_status", "product_platform_links", ["status"], unique=False)

    op.create_table(
        "product_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cod_art", sa.String(length=255), nullable=False),
        sa.Column("id_art", sa.BigInteger(), nullable=True),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("source_platform", sa.String(length=40), nullable=False),
        sa.Column("source_external_id", sa.String(length=255), nullable=True),
        sa.Column("local_path", sa.String(length=1000), nullable=True),
        sa.Column("remote_url", sa.String(length=1000), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cod_art"], ["articoli.cod_art"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_art"], ["articoli.id_art"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cod_art",
            "asset_type",
            "source_platform",
            "local_path",
            "remote_url",
            name="uq_product_assets_source",
        ),
    )
    op.create_index("ix_product_assets_cod_art", "product_assets", ["cod_art"], unique=False)
    op.create_index("ix_product_assets_cod_art_type", "product_assets", ["cod_art", "asset_type"], unique=False)
    op.create_index("ix_product_assets_content_hash", "product_assets", ["content_hash"], unique=False)
    op.create_index("ix_product_assets_id_art", "product_assets", ["id_art"], unique=False)
    op.create_index("ix_product_assets_source_platform", "product_assets", ["source_platform"], unique=False)

    op.create_table(
        "product_platform_fields",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cod_art", sa.String(length=255), nullable=False),
        sa.Column("id_art", sa.BigInteger(), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("field_name", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_external_id", sa.String(length=255), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cod_art"], ["articoli.cod_art"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_art"], ["articoli.id_art"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cod_art",
            "platform",
            "field_name",
            "language",
            name="uq_product_platform_fields_value",
        ),
    )
    op.create_index("ix_product_platform_fields_cod_art", "product_platform_fields", ["cod_art"], unique=False)
    op.create_index("ix_product_platform_fields_cod_art_platform", "product_platform_fields", ["cod_art", "platform"], unique=False)
    op.create_index("ix_product_platform_fields_id_art", "product_platform_fields", ["id_art"], unique=False)
    op.create_index("ix_product_platform_fields_platform", "product_platform_fields", ["platform"], unique=False)

    op.execute(
        """
        INSERT INTO product_assets (
            cod_art,
            id_art,
            asset_type,
            source_platform,
            local_path,
            original_filename,
            is_primary,
            sort_order,
            created_at,
            updated_at
        )
        SELECT
            i.cod_art,
            i.id_art,
            'image',
            'prestashop',
            'images/products/' || i.file_img,
            i.file_img,
            false,
            row_number() OVER (PARTITION BY i.cod_art ORDER BY i.file_img) - 1,
            now(),
            now()
        FROM immagini i
        WHERE i.cod_art IS NOT NULL
          AND i.file_img IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO product_platform_links (
            cod_art,
            id_art,
            platform,
            status,
            created_at,
            updated_at
        )
        SELECT
            source.cod_art,
            max(source.id_art) AS id_art,
            'prestashop',
            'present',
            now(),
            now()
        FROM (
            SELECT cod_art, id_art FROM immagini WHERE cod_art IS NOT NULL
            UNION ALL
            SELECT cod_art, id_art FROM schede_prodotti WHERE cod_art IS NOT NULL
        ) source
        GROUP BY source.cod_art
        ON CONFLICT DO NOTHING
        """
    )


def downgrade():
    op.drop_index("ix_product_platform_fields_platform", table_name="product_platform_fields")
    op.drop_index("ix_product_platform_fields_id_art", table_name="product_platform_fields")
    op.drop_index("ix_product_platform_fields_cod_art_platform", table_name="product_platform_fields")
    op.drop_index("ix_product_platform_fields_cod_art", table_name="product_platform_fields")
    op.drop_table("product_platform_fields")

    op.drop_index("ix_product_assets_source_platform", table_name="product_assets")
    op.drop_index("ix_product_assets_id_art", table_name="product_assets")
    op.drop_index("ix_product_assets_content_hash", table_name="product_assets")
    op.drop_index("ix_product_assets_cod_art_type", table_name="product_assets")
    op.drop_index("ix_product_assets_cod_art", table_name="product_assets")
    op.drop_table("product_assets")

    op.drop_index("ix_product_platform_links_status", table_name="product_platform_links")
    op.drop_index("ix_product_platform_links_platform_status", table_name="product_platform_links")
    op.drop_index("ix_product_platform_links_platform", table_name="product_platform_links")
    op.drop_index("ix_product_platform_links_id_art", table_name="product_platform_links")
    op.drop_index("ix_product_platform_links_external_id", table_name="product_platform_links")
    op.drop_index("ix_product_platform_links_cod_art", table_name="product_platform_links")
    op.drop_table("product_platform_links")
