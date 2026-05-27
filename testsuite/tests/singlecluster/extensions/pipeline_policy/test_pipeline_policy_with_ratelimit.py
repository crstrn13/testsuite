"""Tests for PipelinePolicy coexistence with RateLimitPolicy on the same route."""

import pytest

from testsuite.kuadrant.policy.rate_limit import Limit

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def rate_limit(rate_limit):
    """RateLimitPolicy with a low limit for testing"""
    rate_limit.add_limit("basic", [Limit(2, "10s")])
    return rate_limit


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy):
    """PipelinePolicy that adds a response header to confirm it executed."""
    pipeline_policy.add_response_headers([["x-pipeline", "active"]])
    return pipeline_policy


@pytest.fixture(scope="module", autouse=True)
def commit(request, pipeline_policy, rate_limit):
    """Commit both PipelinePolicy and RateLimitPolicy."""
    for component in [pipeline_policy, rate_limit]:
        if component is not None:
            request.addfinalizer(component.delete)
            component.commit()
            component.wait_for_ready()


@pytest.mark.flaky(reruns=3, reruns_delay=15)
def test_ratelimit_and_pipeline(client):
    """Requests within rate limit pass through with pipeline header."""
    responses = client.get_many("/get", 2)
    responses.assert_all(status_code=200)
    for resp in responses:
        assert resp.headers.get("x-pipeline") == "active"


@pytest.mark.flaky(reruns=3, reruns_delay=15)
def test_ratelimit_enforced_with_pipeline(client):
    """Rate limit is enforced even when PipelinePolicy is present."""
    responses = client.get_many("/get", 2)
    responses.assert_all(status_code=200)
    assert client.get("/get").status_code == 429
