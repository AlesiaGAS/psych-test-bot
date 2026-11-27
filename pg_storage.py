import json
import logging
from typing import Any, Dict, Optional

import asyncpg
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

logger = logging.getLogger(__name__)


class PostgresStorage(BaseStorage):
    """Хранилище состояний FSM в PostgreSQL (Neon), переживает перезапуски Render."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=1,
                max_size=5,
            )
        if not self._initialized:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fsm_states (
                        storage_key TEXT PRIMARY KEY,
                        state TEXT,
                        data JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
            self._initialized = True
            logger.info("Таблица fsm_states в PostgreSQL готова.")
        return self._pool

    @staticmethod
    def _make_key(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id or ''}:{key.destiny}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        pool = await self._get_pool()
        storage_key = self._make_key(key)
        state_str = state.state if isinstance(state, State) else state

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO fsm_states (storage_key, state, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (storage_key)
                DO UPDATE SET state = EXCLUDED.state, updated_at = NOW();
                """,
                storage_key,
                state_str,
            )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        pool = await self._get_pool()
        storage_key = self._make_key(key)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM fsm_states WHERE storage_key = $1;",
                storage_key,
            )
            return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        pool = await self._get_pool()
        storage_key = self._make_key(key)
        payload = json.dumps(data or {}, ensure_ascii=False)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO fsm_states (storage_key, data, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (storage_key)
                DO UPDATE SET data = EXCLUDED.data, updated_at = NOW();
                """,
                storage_key,
                payload,
            )

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        pool = await self._get_pool()
        storage_key = self._make_key(key)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM fsm_states WHERE storage_key = $1;",
                storage_key,
            )
            if not row or row["data"] is None:
                return {}
            raw = row["data"]
            return json.loads(raw) if isinstance(raw, str) else dict(raw)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
