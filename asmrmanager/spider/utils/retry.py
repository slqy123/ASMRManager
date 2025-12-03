import asyncio
import time
from functools import wraps
from asmrmanager.logger import logger
from collections import defaultdict


class RetryError(Exception):
    pass


def retry(base_delay=2, max_retry=5):
    def decorator(func):
        faillock_map = defaultdict(asyncio.Lock)
        wait_util = 0
        retries = 0

        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal wait_util, retries
            faillock = faillock_map[asyncio.get_running_loop()]

            while True:
                if time.time() < wait_util:
                    async with faillock:
                        pass
                try:
                    result = await func(*args, **kwargs)
                    retries = 0
                    return result
                except RetryError:
                    async with faillock:
                        now = time.time()
                        if now < wait_util:
                            continue

                        retries += 1
                        if retries > max_retry:
                            logger.error(
                                f"Function {func.__name__} failed after {max_retry} retries. No more retries."
                            )
                            raise RuntimeError(
                                f"Function {func.__name__} failed after {max_retry} retries."
                            )
                        delay = base_delay * (2 ** (retries - 1))
                        wait_util = now + delay

                        logger.warning(
                            f"Function {func.__name__} failed. Retrying in {delay} seconds... (Attempt {retries}/{max_retry})"
                        )

                        remaining = wait_util - now
                        if remaining > 0:
                            await asyncio.sleep(remaining)

        return wrapper

    return decorator
