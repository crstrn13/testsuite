"""Tests for PipelinePolicy coexistence with AuthPolicy on the same route."""

import pytest

from testsuite.httpx.auth import HeaderApiKeyAuth

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def api_key(create_api_key, module_label):
    """Creates API key Secret for authentication"""
    return create_api_key("api-key", module_label, "pipeline-test-key")


@pytest.fixture(scope="module")
def auth(api_key):
    """Valid API key auth object"""
    return HeaderApiKeyAuth(api_key)


@pytest.fixture(scope="module")
def authorization(authorization, api_key):
    """AuthPolicy with API key identity"""
    authorization.identity.add_api_key("api-key", selector=api_key.selector)
    return authorization


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy):
    """PipelinePolicy that adds a response header to confirm it executed."""
    pipeline_policy.add_response_headers([["x-pipeline", "active"]])
    return pipeline_policy


@pytest.fixture(scope="module", autouse=True)
def commit(request, pipeline_policy, authorization):
    """Commit both PipelinePolicy and AuthPolicy."""
    for component in [pipeline_policy, authorization]:
        if component is not None:
            request.addfinalizer(component.delete)
            component.commit()
            component.wait_for_ready()


def test_auth_and_pipeline(client, auth):
    """Authenticated request passes through both policies, pipeline header is present."""
    response = client.get("/get", auth=auth)
    assert response.status_code == 200
    assert response.headers.get("x-pipeline") == "active"


def test_auth_rejected_no_pipeline(client):
    """Unauthenticated request is rejected by AuthPolicy before pipeline runs."""
    response = client.get("/get")
    assert response.status_code in (401, 403)
