import importlib.metadata
import logging

from pyveoliaidf.api_client import VeoliaApiClient
from pyveoliaidf.aura import AuraClient
from pyveoliaidf.client import Client
from pyveoliaidf.config import ClientConfig
from pyveoliaidf.errors import (
    LoginError,
    NotLoggedInError,
    PyVeoliaIDFError,
    RateLimitError,
    ServerError,
    SessionExpiredError,
    UnexpectedResponseError,
    UnknownContractError,
    UnknownMeterError,
)
from pyveoliaidf.model import (
    ConsumptionHistory,
    Contract,
    Meter,
    MeterIndex,
    Party,
    Reading,
    Site,
    Step,
)
from pyveoliaidf.tls import build_ssl_context

# The version is read from the installed package metadata, which comes from pyproject.toml.
__version__ = importlib.metadata.version("pyveoliaidf")

__all__ = [
    "AuraClient",
    "Client",
    "ClientConfig",
    "ConsumptionHistory",
    "Contract",
    "LoginError",
    "Meter",
    "MeterIndex",
    "NotLoggedInError",
    "Party",
    "PyVeoliaIDFError",
    "RateLimitError",
    "Reading",
    "ServerError",
    "SessionExpiredError",
    "Site",
    "Step",
    "UnexpectedResponseError",
    "UnknownContractError",
    "UnknownMeterError",
    "VeoliaApiClient",
    "__version__",
    "build_ssl_context",
]

# A library logs through the logging module and leaves its configuration to the application.
logging.getLogger(__name__).addHandler(logging.NullHandler())
