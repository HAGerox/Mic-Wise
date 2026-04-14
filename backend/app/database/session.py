"""Async database session management for Mic-Wise show files."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base


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
        """Create the schema if it does not already exist."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    def session(self) -> AsyncSession:
        """Create a new async session."""
        return self.session_factory()

    async def dispose(self) -> None:
        """Dispose of the underlying SQLAlchemy engine."""
        await self.engine.dispose()
