"""Async database session management for Mic-Wise show files."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, Connection, inspect, literal, text
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.compiler import IdentifierPreparer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base


def _add_missing_columns(connection: Connection) -> None:
    """Add model columns that a show file saved by an older version lacks.

    ``create_all`` only creates missing tables, so a column added to a model
    after a show file was created would otherwise make every query on that
    table fail. Existing rows get the column's model default.
    """
    inspector = inspect(connection)
    dialect = connection.dialect
    preparer = dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            _add_column(connection, table.name, column, dialect, preparer)


def _add_column(
    connection: Connection,
    table_name: str,
    column: Column,
    dialect: Dialect,
    preparer: IdentifierPreparer,
) -> None:
    """Add one column to an existing table, filling existing rows with its default."""
    table = preparer.quote(table_name)
    name = preparer.quote(column.name)
    column_type = column.type.compile(dialect=dialect)
    default = column.default
    if default is not None and default.is_scalar and default.arg is not None:
        # SQLite only allows ADD COLUMN ... NOT NULL with a constant default.
        value = literal(default.arg, column.type).compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
        not_null = "" if column.nullable else " NOT NULL"
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type} DEFAULT {value}{not_null}"),
        )
        return

    # Callable defaults (timestamps) can't be a column DEFAULT, so add the column
    # as nullable and fill existing rows with a value computed now.
    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"))
    if default is not None and default.is_callable:
        model_table = Base.metadata.tables[table_name]
        connection.execute(
            model_table.update()
            .where(model_table.c[column.name].is_(None))
            .values({column.name: default.arg(None)}),
        )


class DatabaseManager:
    """Owns the SQLAlchemy engine and session factory for the active show file."""

    def __init__(self, show_path: Path) -> None:
        self.show_path = show_path
        self.engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{show_path}",
            future=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def create_schema(self) -> None:
        """Create the schema if it does not already exist, and add any new columns."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(_add_missing_columns)

    def session(self) -> AsyncSession:
        """Create a new async session."""
        return self.session_factory()

    async def dispose(self) -> None:
        """Dispose of the underlying SQLAlchemy engine."""
        await self.engine.dispose()
