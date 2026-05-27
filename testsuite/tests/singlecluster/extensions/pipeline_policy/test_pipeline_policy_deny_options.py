"""Tests for PipelinePolicy deny action with custom body and headers."""

import pytest

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy):
    """Configure PipelinePolicy with deny action that includes custom status, body, and headers."""
    pipeline_policy.add_request_deny(
        predicate='request.url_path == "/denied"',
        with_status=403,
        with_body='"Access Denied"',
        with_headers='[["x-deny-reason", "policy"]]',
    )
    return pipeline_policy


def test_deny_with_status(client):
    """Deny action returns the configured status code."""
    response = client.get("/denied")
    assert response.status_code == 403


def test_deny_with_body(client):
    """Deny action returns the configured body."""
    response = client.get("/denied")
    assert "Access Denied" in response.content.decode()


def test_deny_with_headers(client):
    """Deny action returns the configured response header."""
    response = client.get("/denied")
    assert response.headers.get("x-deny-reason") == "policy"


def test_allowed_path(client):
    """Request to a non-denied path passes through."""
    response = client.get("/get")
    assert response.status_code == 200
