import asyncio
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Self

from aiohttp import (
    ClientConnectionError,
    ClientPayloadError,
    ClientSession,
    ClientTimeout,
    TCPConnector,
)
from aiolimiter import AsyncLimiter
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from asmrmanager.logger import logger


class HTTPTransport:
    def __init__(
        self, base_url: str, proxy: str | None, limit: int, max_rps: float
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(
                "API concurrency limit must be a positive integer."
            )
        if (
            isinstance(max_rps, bool)
            or not isinstance(max_rps, (int, float))
            or not math.isfinite(max_rps)
        ):
            raise ValueError("API request rate must be a finite number.")
        self.base_url = base_url
        self.proxy = proxy
        self.limit = limit
        self.max_rps = max_rps
        self._session: ClientSession | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._limiter: AsyncLimiter | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("HTTP transport is already open.")
        self._semaphore = asyncio.Semaphore(self.limit)
        self._limiter = (
            AsyncLimiter(1, 1 / self.max_rps) if self.max_rps > 0 else None
        )
        self._session = ClientSession(
            connector=TCPConnector(limit=self.limit),
            timeout=ClientTimeout(total=30, connect=10),
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._semaphore = None
        self._limiter = None

    @asynccontextmanager
    async def _request_slot(self) -> AsyncIterator[ClientSession]:
        session, semaphore = self._session, self._semaphore
        if session is None or semaphore is None:
            raise RuntimeError("HTTP transport is not open.")
        async with semaphore:
            if self._limiter is not None:
                await self._limiter.acquire()
            yield session

    async def request(
        self,
        method: str,
        route: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        binary: bool = False,
    ) -> Any:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_random_exponential(multiplier=2, min=1, max=30),
            retry=retry_if_exception_type(
                (
                    ClientConnectionError,
                    ClientPayloadError,
                    asyncio.TimeoutError,
                )
            ),
            before_sleep=lambda state: logger.warning(
                "Retrying %s %s in %.1fs (attempt %d/5)",
                method,
                route,
                state.upcoming_sleep,
                state.attempt_number + 1,
            ),
            reraise=True,
        ):
            with attempt:
                async with (
                    self._request_slot() as session,
                    session.request(
                        method,
                        self.base_url + route,
                        headers=headers,
                        proxy=self.proxy,
                        params=params,
                        json=data,
                    ) as response,
                ):
                    content = await response.read()
        if binary:
            return content
        return await response.json()
