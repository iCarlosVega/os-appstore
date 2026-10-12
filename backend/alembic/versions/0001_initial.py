"""Immutable baseline matching migrations/001_initial.sql; no application data."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def baseline_metadata(dialect):
    metadata = sa.MetaData()

    def text(name, *, primary=False, required=False, unique=False, default=None, foreign=None):
        args = [sa.ForeignKey(foreign)] if foreign else []
        return sa.Column(name, sa.Text(), *args, primary_key=primary,
                         nullable=not required and not (primary and dialect == "postgresql"),
                         unique=unique, server_default=default)

    def integer(name, *, primary=False, required=True, default=None):
        return sa.Column(name, sa.Integer(), primary_key=primary, autoincrement=False,
                         nullable=not required and not (primary and dialect == "postgresql"),
                         server_default=sa.text(default) if default is not None else None)

    def table(name, *columns):
        return sa.Table(name, metadata, *columns)

    table("settings", integer("id", primary=True, required=False), text("data", required=True),
          sa.CheckConstraint("id = 1"))
    table("categories", text("id", primary=True), text("name", required=True),
          text("parent_id", foreign="categories.id"))
    apps = table("apps", text("id", primary=True), text("repo_id", required=True, unique=True),
                 text("slug", required=True, unique=True), integer("published", default="1"),
                 integer("revision", default="1"), text("data", required=True), text("updated_at", required=True))
    table("slug_aliases", text("slug", primary=True), text("app_id", required=True, foreign="apps.id"))
    candidates = table("candidates", text("repo_id", primary=True), integer("revision", default="1"),
                       text("status", required=True, default="pending"), text("data", required=True),
                       text("assessment", required=True), text("updated_at", required=True))
    table("daily_additions", text("day", primary=True), integer("total", default="0"))
    table("proposals", text("id", primary=True), text("app_id", required=True, unique=True, foreign="apps.id"),
          integer("revision", default="1"), text("data", required=True),
          text("status", required=True, default="pending"), text("updated_at", required=True))
    table("star_snapshots", text("repo_id", primary=True, required=True),
          text("observed_at", primary=True, required=True), integer("stars"))
    table("app_requests", text("id", primary=True), text("name", required=True), text("repo_url"),
          text("status", required=True, default="pending"), text("created_at", required=True))
    table("clicks", text("app_id", primary=True, required=True, foreign="apps.id"),
          text("day", primary=True, required=True), integer("total", default="0"))
    costs = table("cost_entries", text("id", primary=True), text("period", required=True),
                  text("provider", required=True), integer("amount"), integer("settled", default="0"),
                  text("created_at", required=True), sa.CheckConstraint("amount >= 0"))
    table("jobs", text("id", primary=True), text("kind", required=True), text("status", required=True),
          text("checkpoint", required=True, default="{}"), text("started_at", required=True),
          text("finished_at"), text("error"))
    table("leases", text("id", primary=True), text("owner", required=True), text("expires_at", required=True))
    table("notifications", text("id", primary=True), text("message", required=True),
          text("status", required=True, default="pending"), text("created_at", required=True), text("error"))
    table("search_cache", text("id", primary=True), text("data", required=True), text("expires_at", required=True))
    table("rate_limits", text("id", primary=True), integer("total"), text("expires_at", required=True))
    table("audit", text("id", primary=True), text("action", required=True),
          text("data", required=True), text("created_at", required=True))
    sa.Index("apps_published", apps.c.published)
    sa.Index("costs_period", costs.c.period)
    sa.Index("candidates_status", candidates.c.status)
    return metadata


def upgrade():
    connection = op.get_bind()
    baseline_metadata(connection.dialect.name).create_all(connection, checkfirst=False)


def downgrade():
    raise RuntimeError("Baseline downgrade is disabled to preserve data. Restore a verified backup into a separate database for recovery.")
