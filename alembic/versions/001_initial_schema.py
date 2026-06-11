"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Symbols table
    op.create_table(
        "symbols",
        sa.Column("ticker", sa.String(10), primary_key=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # Company profiles table
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "symbol", sa.String(10), sa.ForeignKey("symbols.ticker"), unique=True
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(100)),
        sa.Column("profile_json", sa.JSON()),
        sa.Column(
            "updated_at", sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()
        ),
    )

    # Price bars table
    op.create_table(
        "price_bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(10), sa.ForeignKey("symbols.ticker")),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_price_bars_symbol_date", "price_bars", ["symbol", "date"], unique=True
    )

    # Price movements table
    op.create_table(
        "price_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(10), sa.ForeignKey("symbols.ticker")),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("pct_change", sa.Numeric(8, 4), nullable=False),
        sa.Column("direction", sa.String(4), nullable=False),
        sa.Column("is_major", sa.Boolean(), default=False),
        sa.Column("prev_close", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger()),
    )
    op.create_index(
        "ix_price_movements_symbol_date",
        "price_movements",
        ["symbol", "date"],
        unique=True,
    )
    op.create_index("ix_price_movements_is_major", "price_movements", ["is_major"])

    # News events table
    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), unique=True, nullable=False),
        sa.Column("source", sa.String(100)),
        sa.Column("summary", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )
    op.create_index("ix_news_events_published_at", "news_events", ["published_at"])

    # Event symbol scores table (mapper)
    op.create_table(
        "event_symbol_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("news_events.id")),
        sa.Column("symbol", sa.String(10), sa.ForeignKey("symbols.ticker")),
        sa.Column("correlation_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("correlation_tier", sa.String(10), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("scored_at", sa.DateTime(), default=sa.func.now()),
    )
    op.create_index(
        "ix_event_symbol_scores_event_symbol",
        "event_symbol_scores",
        ["event_id", "symbol"],
        unique=True,
    )
    op.create_index("ix_event_symbol_scores_symbol", "event_symbol_scores", ["symbol"])

    # Movement event attributions table
    op.create_table(
        "movement_event_attributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("price_movements.id")),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("news_events.id")),
        sa.Column("symbol", sa.String(10), sa.ForeignKey("symbols.ticker")),
        sa.Column("impact_rank", sa.Integer(), nullable=False),
        sa.Column("temporal_score", sa.Numeric(5, 4)),
        sa.Column("attribution_label", sa.String(50)),
    )
    op.create_index(
        "ix_movement_event_attributions_movement_event",
        "movement_event_attributions",
        ["movement_id", "event_id"],
        unique=True,
    )
    op.create_index(
        "ix_movement_event_attributions_movement",
        "movement_event_attributions",
        ["movement_id"],
    )


def downgrade() -> None:
    op.drop_table("movement_event_attributions")
    op.drop_table("event_symbol_scores")
    op.drop_table("news_events")
    op.drop_table("price_movements")
    op.drop_table("price_bars")
    op.drop_table("company_profiles")
    op.drop_table("symbols")
