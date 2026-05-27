"""Tests for PipelinePolicy request header injection via add_headers action."""

import pytest

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy):
    """Configure PipelinePolicy with unconditional and conditional request headers."""
    pipeline_policy.add_request_headers([["x-custom-injected", "hello"]])
    pipeline_policy.add_request_headers(
        [["x-conditional", "only-on-get"]],
        predicate='request.url_path == "/get"',
    )
    return pipeline_policy


def test_request_header_injected(client):
    """Unconditional request header is forwarded to the backend."""
    response = client.get("/get")
    assert response.status_code == 200
    assert response.json()["headers"].get("X-Custom-Injected") == "hello"


def test_conditional_header_present(client):
    """Conditional header appears when predicate matches."""
    response = client.get("/get")
    assert response.status_code == 200
    assert response.json()["headers"].get("X-Conditional") == "only-on-get"


def test_conditional_header_absent(client):
    """Conditional header is absent when predicate does not match."""
    response = client.get("/anything")
    assert response.status_code == 200
    assert "X-Conditional" not in response.json()["headers"]
