"""Tests TTL for metadata caching"""

from time import sleep

import pytest

from testsuite.kuadrant.policy.authorization import ValueFrom, Cache
from testsuite.utils import extract_response

pytestmark = [pytest.mark.authorino]

CACHE_TTL = 5


@pytest.fixture(scope="module")
def authorization(authorization, module_label, expectation_path):
    """Adds Cached Metadata to the AuthConfig"""
    meta_cache = Cache(CACHE_TTL, ValueFrom("context.request.http.path"))
    authorization.metadata.add_http(module_label, expectation_path, "GET", cache=meta_cache)
    return authorization


def test_cached_ttl(client, auth, module_label, mockserver):
    """Tests that cached value expires after ttl"""
    response = client.get("/get", auth=auth)
    data = extract_response(response)[module_label]["uuid"] % None
    assert data is not None

    sleep(CACHE_TTL)

    response = client.get("/get", auth=auth)
    cached_data = extract_response(response)[module_label]["uuid"] % None
    assert cached_data is not None

    assert data != cached_data
    assert len(mockserver.retrieve_requests(module_label)) == 2
