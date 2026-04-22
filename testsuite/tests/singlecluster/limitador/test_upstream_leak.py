"""Tests that rate-limited requests do not leak to the upstream service"""

import pytest

from testsuite.backend.mockserver import MockserverBackend
from testsuite.httpx import KuadrantClient
from testsuite.mockserver import Mockserver
from testsuite.kuadrant.policy.rate_limit import Limit

pytestmark = [pytest.mark.limitador, pytest.mark.kuadrant_only, pytest.mark.data_plane]


@pytest.fixture(scope="module")
def backend(request, cluster, blame, label):
    """Deploys MockServer as the upstream backend instead of httpbin"""
    mockserver = MockserverBackend(cluster, blame("mockserver"), label)
    request.addfinalizer(mockserver.delete)
    mockserver.commit()
    mockserver.wait_for_ready()
    return mockserver


@pytest.fixture(scope="module")
def backend_mockserver(backend):
    """Mockserver verification client connected to the upstream backend"""
    url = f"http://{backend.service.external_ip}:8080"
    with KuadrantClient(base_url=url) as client:
        yield Mockserver(client)


@pytest.fixture(scope="module", autouse=True)
def backend_expectation(backend_mockserver):
    """Set up expectation on the backend mockserver so it responds to /get"""
    backend_mockserver.create_response_expectation("get", "")


@pytest.fixture(scope="module")
def rate_limit(rate_limit):
    """Add limit to the policy"""
    rate_limit.add_limit("basic", [Limit(3, "60s")])
    return rate_limit


def test_rate_limited_does_not_reach_upstream(client):
    """Tests that rate-limited requests do not reach the upstream"""
    client.get_many("/get", 3).assert_all(status_code=200)

    response = client.get("/get")
    assert response.status_code == 429
