"""Tests for PipelinePolicy fail action. Wasm-shim marks Fail as unsupported for top-level use."""

import pytest

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy):
    """Configure PipelinePolicy with a conditional fail action and a response header."""
    pipeline_policy.add_request_fail("blocked by fail action", predicate='request.url_path == "/fail"')
    pipeline_policy.add_response_headers([["x-pipeline", "active"]])
    return pipeline_policy


def test_fail_action_rejects(client):
    """Request matching the fail predicate is rejected."""
    response = client.get("/fail")
    assert response.status_code != 200


def test_non_failing_path_allowed(client):
    """Request not matching fail predicate passes through with response header."""
    response = client.get("/get")
    assert response.status_code == 200
    assert response.headers.get("x-pipeline") == "active"
