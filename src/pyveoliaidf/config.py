"""The settings of the clients, gathered in one immutable object."""

from dataclasses import dataclass

DEFAULT_BASE_URL = "https://connexion.leaudiledefrance.fr"

# Sent with every request: the site refuses requests that do not look like a browser.
DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


@dataclass(frozen=True)
class ClientConfig:
    """The settings of the HTTP side of the clients.

    The timeouts are in seconds. A failed call is retried retry_count times at most, after a delay that starts at
    retry_delay and doubles at each attempt, up to max_retry_delay.
    """

    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    retry_count: int = 3
    retry_delay: float = 1.0
    max_retry_delay: float = 15.0
