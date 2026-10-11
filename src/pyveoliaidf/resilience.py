"""The retry policy of the HTTP calls, in one place."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pyveoliaidf.config import ClientConfig

T = TypeVar("T")

Logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """A failure that is worth another attempt: a connection problem, a timeout, or a busy server.

    retry_after is the delay in seconds that the server asked for, if it did, and status is the HTTP status, if there was one.
    """

    def __init__(self, message: str, retry_after: float | None = None, status: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.status = status


def backoff_delay(config: ClientConfig, attempt: int) -> float:
    """Returns the delay before the retry that follows the given attempt (1 for the first one).

    The delay doubles at each attempt up to max_retry_delay, and a random part spreads the retries of concurrent clients.
    """

    delay = min(config.retry_delay * 2 ** (attempt - 1), config.max_retry_delay)

    return float(delay * random.uniform(0.5, 1.0))


async def retrying(
    operation: Callable[[], Awaitable[T]],
    config: ClientConfig,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Runs the operation, and runs it again while it raises RetryableError, up to config.retry_count retries.

    The last RetryableError is raised when the attempts are used up.
    """

    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except RetryableError as error:
            if attempt > config.retry_count:
                raise
            delay = backoff_delay(config, attempt)
            if error.retry_after is not None:
                delay = min(max(delay, error.retry_after), config.max_retry_delay)
            Logger.debug("Attempt %d failed (%s): retrying in %.1fs", attempt, error, delay)
            await sleep(delay)
