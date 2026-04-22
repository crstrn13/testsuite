"""Tests that denied requests do not leak to the upstream service"""

import pytest

from testsuite.backend.mockserver import MockserverBackend
from testsuite.httpx import KuadrantClient
from testsuite.mockserver import Mockserver
from testsuite.utils import rego_allow_header

pytestmark = [pytest.mark.authorino, pytest.mark.data_plane]


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
def header():
    """Header used by OPA policy"""
    return "opa", "opa-test"


@pytest.fixture(scope="module")
def authorization(authorization, header):
    """Adds OPA policy that accepts all requests that contain `header`"""
    authorization.authorization.add_opa_policy("opa", rego_allow_header(*header))
    return authorization


def test_authorized(client, auth, header):
    """Tests that an authorized request reaches the upstream"""
    key, value = header
    response = client.get("/get", auth=auth, headers={key: value})
    assert response.status_code == 200


def test_rejected_does_not_reach_upstream(client, auth):
    """Tests that a request denied by OPA does not reach the upstream"""
    response = client.get("/get", auth=auth)
    assert response.status_code == 403
