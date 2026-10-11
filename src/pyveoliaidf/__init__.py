import importlib.metadata
import logging

from pyveoliaidf.client import Client
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.enum import PropertyNameEnum
from pyveoliaidf.errors import (
    LoginError,
    NotLoggedInError,
    PyVeoliaIDFError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnexpectedResponseError,
    UnknownContractError,
)
from pyveoliaidf.model import DailyReading
from pyveoliaidf.tls import build_ssl_context

# The version is read from the installed package metadata, which comes from pyproject.toml.
__version__ = importlib.metadata.version("pyveoliaidf")

__all__ = [
    "Client",
    "ClientConfig",
    "DailyReading",
    "LoginError",
    "NotLoggedInError",
    "PropertyNameEnum",
    "PyVeoliaIDFError",
    "RateLimitError",
    "ServerError",
    "SessionExpiredError",
    "UnexpectedResponseError",
    "UnknownContractError",
    "__version__",
    "build_ssl_context",
]

# A library logs through the logging module and leaves its configuration to the application.
logging.getLogger(__name__).addHandler(logging.NullHandler())
