import json
from typing import Any
import asyncpg


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(dsn=self._dsn, ssl="require")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_results (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    test_type VARCHAR(20) NOT NULL,
                    result_code VARCHAR(32) NOT NULL,
                    scales_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            # Расширяем колонки, если таблица была создана ранее
            await conn.execute(
                """
                ALTER TABLE test_results
                    ALTER COLUMN test_type TYPE VARCHAR(20),
                    ALTER COLUMN result_code TYPE VARCHAR(32);
                """
            )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def save_result(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        test_type: str,
        result_code: str,
        scales_data: dict,
    ) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO test_results
                    (user_id, username, full_name, test_type, result_code, scales_json)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb);
                """,
                user_id,
                username,
                full_name,
                test_type,
                result_code,
                json.dumps(scales_data, ensure_ascii=False),
            )

    async def get_all_candidates(self, limit: int = 30) -> list[dict[str, Any]]:
        """Возвращает список уникальных пользователей, отсортированный по дате последнего теста."""
        if not self._pool:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    user_id,
                    (ARRAY_AGG(full_name ORDER BY created_at DESC))[1] AS full_name,
                    (ARRAY_AGG(username ORDER BY created_at DESC))[1] AS username,
                    COUNT(DISTINCT test_type) AS tests_count,
                    MAX(created_at) AS last_at
                FROM test_results
                GROUP BY user_id
                ORDER BY last_at DESC
                LIMIT $1;
                """,
                limit,
            )
            return [dict(r) for r in rows]

    async def get_candidate_results(self, user_id: int) -> list[dict[str, Any]]:
        """Возвращает последний результат по каждому пройденному тесту для конкретного user_id."""
        if not self._pool:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (test_type)
                    user_id,
                    username,
                    full_name,
                    test_type,
                    result_code,
                    scales_json,
                    created_at
                FROM test_results
                WHERE user_id = $1
                ORDER BY test_type, created_at DESC;
                """,
                user_id,
            )
            results = []
            for r in rows:
                item = dict(r)
                if isinstance(item["scales_json"], str):
                    item["scales_json"] = json.loads(item["scales_json"])
                results.append(item)
            return results
