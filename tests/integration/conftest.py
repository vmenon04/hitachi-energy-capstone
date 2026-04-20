"""
Shared fixtures for integration tests that require Azure Blob Storage.

In CI the ``azurite`` service container starts before the job steps, so port
10000 is already listening when pytest collects tests.  Locally, start Azurite
with either of:

    docker run -d -p 10000:10000 mcr.microsoft.com/azure-storage/azurite azurite-blob --skipApiVersionCheck
    npx azurite-blob --skipApiVersionCheck --silent

The ``--skipApiVersionCheck`` flag is required so that Azurite accepts the API
version used by the current azure-storage-blob SDK without rejecting it.

If Azurite is not reachable after a short retry window, every test that
depends on ``azurite_container`` is automatically skipped (no test failures).
"""

import socket
import time
import uuid

import pytest
from azure.storage.blob import BlobServiceClient
from azure.storage.blob._shared.policies import ExponentialRetry

# ---------------------------------------------------------------------------
# Well-known Azurite development connection string (not a real secret).
# The account key below is the fixed public key published by Microsoft
# in their Azurite documentation.
# ---------------------------------------------------------------------------
AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

_AZURITE_HOST = "127.0.0.1"
_AZURITE_PORT = 10000
_STARTUP_RETRIES = 8   # ~8s (generous enough for slow CI runners)
_RETRY_INTERVAL = 1    # seconds between attempts


@pytest.fixture(scope="session")
def azurite_client():
    """
    Session-scoped BlobServiceClient pointed at Azurite.

    Retries the connection so tests are robust against Azurite needing a
    moment to start (common in GitHub Actions service containers).
    Calls ``pytest.skip`` if the service never becomes reachable, which
    propagates to every test that depends on this fixture, no hard failures.
    """
    for attempt in range(_STARTUP_RETRIES):
        try:
            sock = socket.create_connection((_AZURITE_HOST, _AZURITE_PORT), timeout=1)
            sock.close()
            break
        except OSError:
            if attempt < _STARTUP_RETRIES - 1:
                time.sleep(_RETRY_INTERVAL)
    else:
        pytest.skip(
            f"Azurite Blob Service is not available on {_AZURITE_HOST}:{_AZURITE_PORT}. "
            "Start it locally with:\n"
            "  docker run -d -p 10000:10000 "
            "mcr.microsoft.com/azure-storage/azurite azurite-blob --skipApiVersionCheck"
        )

    # Use a no-retry policy so an API version mismatch fails fast (skip) instead
    # of hanging for 20+ seconds while the SDK retries with exponential backoff.
    client = BlobServiceClient.from_connection_string(
        AZURITE_CONN_STR,
        retry_policy=ExponentialRetry(initial_backoff=0, increment_base=0, retry_total=0),
    )
    try:
        next(iter(client.list_containers()), None)
    except Exception as exc:
        pytest.skip(
            f"Azurite is reachable but rejected the request: {exc}\n"
            "Ensure Azurite is started with --skipApiVersionCheck:\n"
            "  docker run -d -p 10000:10000 "
            "mcr.microsoft.com/azure-storage/azurite azurite-blob --skipApiVersionCheck"
        )
    return client


@pytest.fixture
def azurite_container(azurite_client):
    """
    Creates a uniquely-named container in Azurite, yields
    ``(container_name, AZURITE_CONN_STR)``, then deletes the container.

    Using a unique name per test ensures complete isolation even if a
    previous test left blobs behind.
    """
    name = f"test-{uuid.uuid4().hex[:10]}"
    azurite_client.create_container(name)
    yield name, AZURITE_CONN_STR
    try:
        azurite_client.delete_container(name)
    except Exception:
        pass  # best-effort, don't mask the real test failure
