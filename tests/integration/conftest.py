"""Fixtures of the live tests: they talk to the real Veolia site.

The credentials come from the environment or from a .env file. Without them, the tests are skipped.
One login serves a whole module, so that the site sees few logins.
"""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is a dev dependency: without it, the credentials must come from the environment
    load_dotenv = None  # type: ignore[assignment]

from pyveoliaidf import Client


@pytest.fixture(scope="session")
def credentials() -> tuple[str, str]:
    # Only the live tests read the .env file: the unit tests never see the credentials.
    if load_dotenv is not None:
        load_dotenv()
    username = os.environ.get("VEOLIAIDF_USERNAME")
    password = os.environ.get("VEOLIAIDF_PASSWORD")
    if not username or not password:
        pytest.skip("VEOLIAIDF_USERNAME and VEOLIAIDF_PASSWORD are not set (see .env.example)")

    return username, password


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client(credentials: tuple[str, str]) -> AsyncIterator[Client]:
    async with Client(*credentials) as live_client:
        yield live_client
