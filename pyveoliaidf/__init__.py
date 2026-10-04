import importlib.metadata

from pyveoliaidf.enum import PropertyNameEnum  # noqa: F401
from pyveoliaidf.client import Client  # noqa: F401
from pyveoliaidf.client import LoginError  # noqa: F401

# The version is read from the installed package metadata, which comes from pyproject.toml.
__version__ = importlib.metadata.version("pyveoliaidf")
