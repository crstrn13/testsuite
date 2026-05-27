"""Tests for PipelinePolicy response-phase deny action (deny after backend has responded)."""

import pytest

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy):
    """Configure PipelinePolicy with a response-phase deny action."""
    pipeline_policy.add_response_deny(predicate='request.url_path == "/anything"', with_status=403)
    return pipeline_policy


def test_response_deny_blocks(client):
    """Request to /anything is denied during response phase."""
    response = client.get("/anything")
    assert response.status_code == 403


def test_response_deny_allows_other(client):
    """Request to /get is not affected by response-phase deny."""
    response = client.get("/get")
    assert response.status_code == 200
