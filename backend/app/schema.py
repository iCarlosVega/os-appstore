"""Explicit schema upgrades; ordinary application queries keep their existing adapters."""
import os
import re
from contextlib import contextmanager

from .config import ROOT, config

BASELINE = "0001_initial"


def _alembic_config():
    from alembic.config import Config
    # Database URLs never pass through ConfigParser's percent interpolation.
    return Config(str(ROOT / "backend/alembic.ini"))


@contextmanager
def _migration_connection():
    import sqlalchemy as sa
    from sqlalchemy.pool import NullPool

    if config.database_url:
        import psycopg
        engine = sa.create_engine(
            "postgresql+psycopg://", poolclass=NullPool, hide_parameters=True,
            creator=lambda: psycopg.connect(config.database_url, connect_timeout=10),
        )
    else:
        if config.production and not os.getenv("SQLITE_PATH"):
            raise RuntimeError("Configure DATABASE_URL or an explicit persistent SQLITE_PATH in production.")
        path = config.sqlite_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = sa.create_engine(sa.URL.create("sqlite+pysqlite", database=str(path)),
                                  poolclass=NullPool, connect_args={"timeout": 10}, hide_parameters=True)

        @sa.event.listens_for(engine, "connect")
        def sqlite_connect(connection, _):
            connection.isolation_level = None
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA busy_timeout=10000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()

        @sa.event.listens_for(engine, "begin")
        def sqlite_begin(connection):
            # Own the real DDL transaction, including on legacy sqlite3 drivers.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    try:
        with engine.begin() as connection:
            if config.database_url:
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(19962411)")
            yield connection
    finally:
        engine.dispose()


def _default(value):
    if value is None:
        return None
    value = str(value).strip()
    # PostgreSQL decorates TEXT literals with a cast; SQLite adds parentheses.
    value = re.sub(r"::(?:text|integer|character varying)\s*$", "", value, flags=re.I)
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    if re.fullmatch(r"'\d+'", value):
        value = value[1:-1]
    return value


def _check(value):
    # Baseline checks contain only identifiers, integer constants and operators.
    return re.sub(r'[\s()"]', "", str(value)).lower()


def _foreign_key(columns, table, targets, options):
    options = options or {}
    return (tuple(columns), table, tuple(targets),
            (options.get("ondelete") or "NO ACTION").upper(),
            (options.get("onupdate") or "NO ACTION").upper(),
            bool(options.get("deferrable")),
            (options.get("initially") or "IMMEDIATE").upper(),
            (options.get("match") or "SIMPLE").upper())


def _extra_objects(connection, inspector):
    objects = [f"view {name}" for name in inspector.get_view_names()]
    if connection.dialect.name == "postgresql":
        objects += [f"materialized view {name}" for name in inspector.get_materialized_view_names()]
        objects += [f"sequence {name}" for name in inspector.get_sequence_names()]
        rows = connection.exec_driver_sql("""
            SELECT t.tgname FROM pg_trigger t
            JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND NOT t.tgisinternal
        """).all()
        objects += [f"trigger {row[0]}" for row in rows]
        # Reflection omits PK deferrability and FK validation state. Ordinary
        # PK/unique/FK constraints are non-inheritable; only CHECK/NOT NULL can
        # use NO INHERIT to alter the baseline's inheritance behavior.
        rows = connection.exec_driver_sql("""
            SELECT c.relname, k.conname FROM pg_constraint k
            JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND
                (NOT k.convalidated OR k.condeferrable OR k.condeferred
                 OR (k.contype IN ('c','n') AND k.connoinherit)
                 OR k.contype NOT IN ('p','u','f','c','n'))
        """).all()
        objects += [f"non-baseline constraint {row[0]}.{row[1]}" for row in rows]
        rows = connection.exec_driver_sql("""
            SELECT c.relname, a.attname FROM pg_attribute a
            JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_type t ON t.oid=a.atttypid
            WHERE n.nspname=current_schema() AND c.relkind IN ('r','p')
                AND a.attnum>0 AND NOT a.attisdropped AND a.attcollation<>t.typcollation
        """).all()
        objects += [f"non-baseline collation {row[0]}.{row[1]}" for row in rows]
        rows = connection.exec_driver_sql("""
            SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relkind IN ('r','p') AND
                (c.relrowsecurity OR c.relforcerowsecurity OR c.relkind='p' OR c.relispartition
                 OR EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid=c.oid))
        """).all()
        objects += [f"non-baseline table policy/inheritance {row[0]}" for row in rows]
        rows = connection.exec_driver_sql("""
            SELECT r.rulename FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relkind IN ('r','p')
        """).all()
        objects += [f"rule {row[0]}" for row in rows]
    else:
        objects += [f"trigger {row[0]}" for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='trigger'").all()]
        for name, ddl in connection.exec_driver_sql(
                "SELECT name,sql FROM sqlite_master WHERE type='table'").all():
            if re.search(r"\b(?:ON\s+CONFLICT|COLLATE|AUTOINCREMENT|WITHOUT\s+ROWID|STRICT|VIRTUAL)\b", ddl or "", re.I):
                objects.append(f"non-baseline SQLite table options {name}")
        reflected = {item["name"] for table in inspector.get_table_names()
                     for item in inspector.get_indexes(table)}
        actual = {row[0] for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").all()}
        objects += [f"unreflected SQLite index {name}" for name in sorted(actual - reflected)]
    return objects


def _schema_differences(connection, inspector, expected):
    import sqlalchemy as sa

    differences = []
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    wanted_tables = set(expected.tables)
    differences += [f"missing table {name}" for name in sorted(wanted_tables - actual_tables)]
    differences += [f"unexpected table {name}" for name in sorted(actual_tables - wanted_tables)]
    for name in sorted(actual_tables & wanted_tables):
        table = expected.tables[name]
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        if set(columns) != set(table.columns.keys()):
            differences.append(f"{name}: column names differ")
        for column in table.columns:
            actual = columns.get(column.name)
            if actual is None:
                continue
            default = column.server_default
            wanted_default = None
            if default is not None:
                wanted_default = (str(default.arg.compile(dialect=connection.dialect))
                                  if hasattr(default.arg, "compile") else "'" + str(default.arg) + "'")
            if (str(actual["type"]).upper() != str(column.type).upper()
                    or actual["nullable"] != column.nullable
                    or _default(actual.get("default")) != _default(wanted_default)
                    or actual.get("identity") or actual.get("computed")):
                differences.append(f"{name}.{column.name}: type, nullability, default or generated value differs")
        if tuple(inspector.get_pk_constraint(name).get("constrained_columns") or ()) != tuple(
                column.name for column in table.primary_key.columns):
            differences.append(f"{name}: primary key differs")
        actual_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(name)}
        wanted_unique = {tuple(column.name for column in item.columns) for item in table.constraints
                         if isinstance(item, sa.UniqueConstraint)}
        if actual_unique != wanted_unique:
            differences.append(f"{name}: unique constraints differ")
        wanted_foreign = {_foreign_key(
            [element.parent.name for element in item.elements], item.referred_table.name,
            [element.column.name for element in item.elements],
            {"ondelete": item.ondelete, "onupdate": item.onupdate, "deferrable": item.deferrable,
             "initially": item.initially, "match": item.match})
            for item in table.foreign_key_constraints}
        actual_foreign = {_foreign_key(item["constrained_columns"], item["referred_table"],
                                       item["referred_columns"], item.get("options"))
                          for item in inspector.get_foreign_keys(name)}
        if actual_foreign != wanted_foreign or any(
                item.get("referred_schema") not in (None, inspector.default_schema_name)
                for item in inspector.get_foreign_keys(name)):
            differences.append(f"{name}: foreign keys differ")
        actual_checks = {_check(item["sqltext"]) for item in inspector.get_check_constraints(name)}
        wanted_checks = {_check(item.sqltext) for item in table.constraints if isinstance(item, sa.CheckConstraint)}
        if actual_checks != wanted_checks:
            differences.append(f"{name}: check constraints differ")
        actual_indexes = []
        for item in inspector.get_indexes(name):
            options = item.get("dialect_options") or {}
            if (any(value is not None and value != [] and value != "btree" for value in options.values())
                    or item.get("column_sorting")):
                differences.append(f"{name}: non-baseline index options on {item['name']}")
            if item.get("duplicates_constraint"):
                continue
            actual_indexes.append((tuple(item["column_names"]), bool(item["unique"])))
        wanted_indexes = [(tuple(column.name for column in item.columns), bool(item.unique))
                          for item in table.indexes]
        if sorted(actual_indexes, key=str) != sorted(wanted_indexes, key=str):
            differences.append(f"{name}: indexes differ")
    return differences


def _version_table_differences(inspector):
    columns = inspector.get_columns("alembic_version")
    if (len(columns) != 1 or columns[0]["name"] != "version_num"
            or str(columns[0]["type"]).upper() != "VARCHAR(32)" or columns[0]["nullable"]
            or columns[0].get("default") is not None
            or columns[0].get("identity") or columns[0].get("computed")
            or inspector.get_pk_constraint("alembic_version").get("constrained_columns") != ["version_num"]
            or inspector.get_foreign_keys("alembic_version")
            or inspector.get_check_constraints("alembic_version")
            or inspector.get_unique_constraints("alembic_version")
            or any(not item.get("duplicates_constraint") for item in inspector.get_indexes("alembic_version"))):
        return ["alembic_version: unexpected version table definition"]
    return []


def _upgrade_locked(connection, alembic_config):
    import sqlalchemy as sa
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory.from_config(alembic_config)
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    differences = _extra_objects(connection, inspector)
    if "alembic_version" in tables:
        differences += _version_table_differences(inspector)
    if differences:
        raise RuntimeError("Schema needs manual review; no schema changes made: " + "; ".join(differences[:30]))
    current = MigrationContext.configure(connection).get_current_heads()
    known = {item.revision for item in scripts.walk_revisions()}
    if len(current) > 1 or any(item not in known for item in current):
        raise RuntimeError("Unknown or multiple schema revisions. Use the matching application release and review a backup; no schema changes made.")
    app_tables = tables - {"alembic_version"}
    if not current or current == (BASELINE,):
        expected = scripts.get_revision(BASELINE).module.baseline_metadata(connection.dialect.name)
        if app_tables or current:
            differences = _schema_differences(connection, inspector, expected)
            if differences:
                raise RuntimeError("Schema needs manual review; no schema changes made: " + "; ".join(differences[:30]))
            if not current:
                command.stamp(alembic_config, BASELINE)
    command.upgrade(alembic_config, "head")


def upgrade_schema() -> None:
    from .db import _connection
    if _connection.get() is not None:
        raise RuntimeError("Run schema migrations outside an application transaction to avoid a second migration lock.")
    try:
        alembic_config = _alembic_config()
        with _migration_connection() as connection:
            alembic_config.attributes["connection"] = connection
            _upgrade_locked(connection, alembic_config)
    except RuntimeError:
        raise
    except Exception:
        # Driver exceptions can include credentials, SQL or user payloads.
        raise RuntimeError("Schema migration failed. Check connectivity, permissions and migration resources, and inspect the destination before retrying; restore a verified backup into a separate database if recovery is needed.") from None
