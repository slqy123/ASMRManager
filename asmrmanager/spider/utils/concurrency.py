import asyncio
from functools import wraps
from collections import defaultdict
import time


def concurrent_rate_limit(limit: int = 1, max_rps: float = 1):
    """
    A decorator to limit the number of concurrent executions of an async function.

    Args:
        limit (int): Maximum number of concurrent executions allowed.
        max_rps (float): Maximum requests per second allowed.

    Returns:
        Callable: A decorator that limits concurrency.
    """

    semaphore_map = defaultdict(lambda: asyncio.Semaphore(limit))
    delay = limit / max_rps if max_rps > 0 else 0

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with semaphore_map[asyncio.get_running_loop()]:
                wait_util = time.time() + delay
                result = await func(*args, **kwargs)
                delta = wait_util - time.time()
                if delta > 0:
                    await asyncio.sleep(delta)
                return result

        return wrapper

    return decorator
