"""Add durable Telegram review drafts and scoped polling offsets."""
from alembic import op
import sqlalchemy as sa

revision = "0002_telegram_reviews"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def review_metadata():
    metadata = sa.MetaData()
    reviews = sa.Table(
        "telegram_reviews", metadata,
        sa.Column("token", sa.Text(), primary_key=True, nullable=False),
        sa.Column("repo_id", sa.Text(), nullable=False),
        sa.Column("candidate_revision", sa.Integer(), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("assessment", sa.Text(), nullable=False),
        sa.Column("draft", sa.Text(), nullable=False),
        sa.Column("options", sa.Text(), nullable=False),
        sa.Column("confirmed", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("app_slug", sa.Text(), nullable=True),
    )
    sa.Index("telegram_reviews_lookup", reviews.c.repo_id, reviews.c.candidate_revision,
             reviews.c.owner_user_id, reviews.c.chat_id, reviews.c.status)
    sa.Table(
        "telegram_state", metadata,
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )
    return metadata


def upgrade():
    review_metadata().create_all(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError(
        "Telegram review downgrade is disabled to preserve review history and polling offsets. "
        "Disable Telegram and restore a verified backup into a separate database instead."
    )
