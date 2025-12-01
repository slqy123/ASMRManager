import asyncio
from functools import wraps


def concurrency_limiter(max_concurrent: int = 4, delay: float | None = None):
    """
    A decorator to limit the number of concurrent executions of an async function.

    Args:
        max_concurrent (int): Maximum number of concurrent executions allowed.
        delay (float): Delay in seconds after each function execution.

    Returns:
        Callable: A decorator that limits concurrency.
    """

    semaphore = asyncio.Semaphore(max_concurrent)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with semaphore:
                result = await func(*args, **kwargs)
                if delay:
                    await asyncio.sleep(delay)
                return result

        return wrapper

    return decorator
