import pytest

from pyveoliaidf.config import ClientConfig
from pyveoliaidf.resilience import RetryableError, backoff_delay, retrying

CONFIG = ClientConfig(retry_count=3, retry_delay=1.0, max_retry_delay=5.0)


class Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


class Flaky:
    """An operation that fails a number of times and then answers."""

    def __init__(self, failures: int, retry_after: float | None = None):
        self.failures = failures
        self.retry_after = retry_after
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RetryableError("busy", self.retry_after)

        return "done"


class TestBackoffDelay:
    @pytest.mark.parametrize(("attempt", "upper"), [(1, 1.0), (2, 2.0), (3, 4.0), (4, 5.0), (10, 5.0)])
    def test_doubles_up_to_the_maximum_with_jitter(self, attempt: int, upper: float) -> None:
        for _ in range(50):
            assert upper / 2 <= backoff_delay(CONFIG, attempt) <= upper


class TestRetrying:
    async def test_returns_at_the_first_success_without_waiting(self) -> None:
        recorder = Recorder()
        operation = Flaky(0)

        assert await retrying(operation, CONFIG, recorder.sleep) == "done"
        assert operation.calls == 1
        assert recorder.delays == []

    async def test_retries_until_success(self) -> None:
        recorder = Recorder()
        operation = Flaky(2)

        assert await retrying(operation, CONFIG, recorder.sleep) == "done"
        assert operation.calls == 3
        assert len(recorder.delays) == 2

    async def test_gives_up_after_the_retries(self) -> None:
        recorder = Recorder()
        operation = Flaky(100)

        with pytest.raises(RetryableError):
            await retrying(operation, CONFIG, recorder.sleep)

        assert operation.calls == CONFIG.retry_count + 1

    async def test_honors_retry_after_within_the_maximum(self) -> None:
        recorder = Recorder()

        await retrying(Flaky(1, retry_after=3.0), CONFIG, recorder.sleep)

        assert recorder.delays == [3.0]

    async def test_caps_retry_after_at_the_maximum_delay(self) -> None:
        recorder = Recorder()

        await retrying(Flaky(1, retry_after=3600.0), CONFIG, recorder.sleep)

        assert recorder.delays == [CONFIG.max_retry_delay]

    async def test_other_errors_are_not_retried(self) -> None:
        calls = []

        async def operation() -> None:
            calls.append(1)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await retrying(operation, CONFIG)

        assert len(calls) == 1
