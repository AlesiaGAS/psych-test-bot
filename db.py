import json
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
                    test_type VARCHAR(10) NOT NULL,
                    result_code VARCHAR(16) NOT NULL,
                    scales_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
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
