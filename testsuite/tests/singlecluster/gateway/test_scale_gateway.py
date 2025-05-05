import pytest

from testsuite.kuadrant.policy import CelExpression
from testsuite.kuadrant.policy.rate_limit import RateLimitPolicy, Limit


@pytest.fixture(scope="module")
def rate_limit(blame, gateway, module_label, cluster):
    policy = RateLimitPolicy.create_instance(cluster, blame("authz"), gateway, labels={"app": module_label})
    policy.add_limit("basic", [Limit(5, "60s")], counters=[CelExpression("auth.identity.user")])
    return policy

def test_scale_gateway(gateway, client, auth, rate_limit, authorization):
    responses = client.get_many("/get", 5, auth=auth)
    responses.assert_all(status_code=200)

    assert client.get("/get", auth=auth).status_code == 429

    gateway.model.spec.replicas = 2
    print("STOP")



