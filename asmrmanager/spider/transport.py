import asyncio
from typing import Any, Self

from aiohttp import (
    ClientConnectionError,
    ClientResponseError,
    ClientSession,
    ClientSSLError,
    ClientTimeout,
    ServerFingerprintMismatch,
    TCPConnector,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from asmrmanager.logger import logger


def is_retryable_error(error: BaseException) -> bool:
    if isinstance(error, (ClientSSLError, ServerFingerprintMismatch)):
        return False
    if isinstance(error, ClientResponseError):
        return error.status in {408, 429, 500, 502, 503, 504}
    return isinstance(error, (ClientConnectionError, asyncio.TimeoutError))


class HTTPTransport:
    def __init__(self, base_url: str, proxy: str | None, limit: int) -> None:
        self.base_url = base_url
        self.proxy = proxy
        self.limit = limit
        self._session: ClientSession | None = None

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("HTTP transport is already open.")
        self._session = ClientSession(
            connector=TCPConnector(limit=self.limit),
            timeout=ClientTimeout(total=30, connect=10),
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def request(
        self,
        method: str,
        route: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        binary: bool = False,
        retryable: bool = False,
    ) -> Any:
        session = self._session
        if session is None:
            raise RuntimeError("HTTP transport is not open.")
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_random_exponential(multiplier=2, min=1, max=30),
            retry=retry_if_exception(
                lambda error: retryable and is_retryable_error(error)
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
                async with session.request(
                    method,
                    self.base_url + route,
                    headers=headers,
                    proxy=self.proxy,
                    params=params,
                    json=data,
                ) as response:
                    response.raise_for_status()
                    if binary:
                        return await response.read()
                    return await response.json()
