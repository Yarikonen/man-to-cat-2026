"""Async PostgreSQL database manager for image processing records."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg


FINAL_STATUSES = frozenset({"done", "failed"})

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL,
    original_s3_key TEXT NOT NULL,
    processed_s3_key TEXT,
    status TEXT NOT NULL DEFAULT 'received',
    error_reason TEXT,
    telegram_message_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_images_user_id ON images (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_images_status ON images (status);",
    "CREATE INDEX IF NOT EXISTS idx_images_user_status ON images (user_id, status);",
]


class DatabaseManager:
    """Async PostgreSQL manager for image processing records."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create connection pool and initialize schema."""
        self._pool = await asyncpg.create_pool(self._database_url)
        await self._init_schema()

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            for index_sql in CREATE_INDEXES_SQL:
                await conn.execute(index_sql)

    @staticmethod
    def _now() -> datetime:
        """Return current UTC timestamp."""
        return datetime.now(timezone.utc)

    async def create_image_record(
        self, user_id: int, original_s3_key: str
    ) -> str:
        """Create a new image record and return its UUID string."""
        image_id = str(uuid.uuid4())
        await self._insert_record(image_id, user_id, original_s3_key)
        return image_id

    async def create_image_record_with_id(
        self,
        image_id: str,
        user_id: int,
        original_s3_key: str,
    ) -> None:
        """Create a new image record with a pre-determined UUID."""
        await self._insert_record(image_id, user_id, original_s3_key)

    async def _insert_record(
        self,
        image_id: str,
        user_id: int,
        original_s3_key: str,
    ) -> None:
        """Insert a new image record."""
        assert self._pool is not None
        now = self._now()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO images "
                "(id, user_id, original_s3_key, status, created_at, updated_at) "
                "VALUES ($1::uuid, $2, $3, 'received', $4, $5)",
                image_id, user_id, original_s3_key, now, now,
            )

    async def update_status(
        self,
        image_id: str,
        status: str,
        **kwargs: Any,
    ) -> None:
        """Update image status and optional fields."""
        assert self._pool is not None
        now = self._now()

        field_map = {
            "processed_s3_key": "processed_s3_key",
            "error_reason": "error_reason",
            "telegram_message_id": "telegram_message_id",
            "original_s3_key": "original_s3_key",
        }
        extra_fields: list[str] = []
        values: list[Any] = []
        for key, column in field_map.items():
            if key in kwargs:
                extra_fields.append(f"{column} = ${len(values) + 1}")
                values.append(kwargs[key])

        if status == "preprocessing" and "started_at" not in kwargs:
            extra_fields.append(f"started_at = ${len(values) + 1}")
            values.append(now)

        if status in FINAL_STATUSES and "completed_at" not in kwargs:
            extra_fields.append(f"completed_at = ${len(values) + 1}")
            values.append(now)

        # Add status and updated_at
        extra_fields.append(f"status = ${len(values) + 1}")
        values.append(status)
        extra_fields.append(f"updated_at = ${len(values) + 1}")
        values.append(now)

        # Add image_id as the WHERE parameter
        values.append(image_id)

        set_clause = ", ".join(extra_fields)
        query = f"UPDATE images SET {set_clause} WHERE id = ${len(values)}::uuid"

        async with self._pool.acquire() as conn:
            await conn.execute(query, *values)

    async def get_image(self, image_id: str) -> Optional[dict[str, Any]]:
        """Get image record by ID."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM images WHERE id = $1::uuid",
                image_id,
            )
            if row is None:
                return None
            return dict(row)

    async def get_user_active_image(
        self, user_id: int
    ) -> Optional[dict[str, Any]]:
        """Get the user's current active (non-final) image, if any."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM images "
                "WHERE user_id = $1 AND status != ALL($2::text[]) "
                "ORDER BY created_at DESC LIMIT 1",
                user_id, list(FINAL_STATUSES),
            )
            if row is None:
                return None
            return dict(row)

    async def get_processing_stats(self) -> dict[str, int]:
        """Return count of images grouped by status."""
        assert self._pool is not None
        stats: dict[str, int] = {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT status, COUNT(*) AS cnt FROM images GROUP BY status"
            )
            for row in rows:
                stats[row["status"]] = row["cnt"]
        return stats

    async def get_active_images(
        self,
    ) -> list[dict[str, Any]]:
        """Get all images that are not in a final status."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM images "
                "WHERE status != ALL($1::text[]) "
                "ORDER BY created_at ASC",
                list(FINAL_STATUSES),
            )
            return [dict(row) for row in rows]
