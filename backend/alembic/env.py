"""Use only the already locked, verified connection from app.schema."""
from alembic import context

connection = context.config.attributes.get("connection")
if context.is_offline_mode() or connection is None:
    raise RuntimeError("Run the backend migration command; direct/offline Alembic execution is disabled.")

context.configure(connection=connection, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
