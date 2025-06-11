"""
This module contains tests for scaling the gateway deployment by manually increasing the replicas in the deployment spec
"""

import time

import pytest

from testsuite.kuadrant.policy import CelExpression, CelPredicate
from testsuite.kuadrant.policy.rate_limit import RateLimitPolicy, Limit
from testsuite.kubernetes import Selector
from testsuite.kubernetes.deployment import Deployment
from testsuite.kubernetes.horizontal_pod_autoscaler import HorizontalPodAutoscaler

@pytest.fixture(scope="module", autouse=True)
def commit(request, authorization, rate_limit, dns_policy, tls_policy):
    """Commits all important stuff before tests"""
    for component in [dns_policy, tls_policy, authorization, rate_limit]:
        if component is not None:
            request.addfinalizer(component.delete)
            component.commit()
            component.wait_for_ready()

@pytest.fixture(scope="module")
def hpa(request, cluster, blame, gateway):
    """Add hpa to the gateway deployment"""
    hpa = HorizontalPodAutoscaler.create_instance(cluster, blame("hpa"), gateway.deployment,
[{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": 50}}}])
    request.addfinalizer(hpa.delete)
    hpa.commit()


@pytest.fixture(scope="module")
def load_generator(request, cluster, blame, backend, oidc_provider, client):
    labels = {"app" : "load-generator"}
    load_generator = Deployment.create_instance(
        cluster,
        blame("load-generator"),
        container_name="httpbin",
        image="quay.io/acristur/siege:4.1.7",
        selector=Selector(matchLabels=labels),
        labels=labels,
        ports={"http": 8080}, # this is not doing anything, but necessary for the constructor
        command_args=["-H", f"Authorization: Bearer {oidc_provider.get_token()}", "-c", "100", "-t", "5m", f"{client.base_url.scheme}://{client.base_url.host}"],
    )

    request.addfinalizer(load_generator.delete)
    load_generator.commit()
    return load_generator

@pytest.fixture(scope="module")
def rate_limit(blame, gateway, module_label, cluster):
    """Add limit to the policy"""
    policy = RateLimitPolicy.create_instance(cluster, blame("rlp"), gateway, labels={"app": module_label})
    policy.add_limit("basic", [Limit(5, "60s")], when=[CelPredicate("auth.identity.userid.size() != 0")])
    return policy


# pylint: disable=unused-argument
def test_scale_gateway(gateway, client, auth, rate_limit, authorization, hpa, load_generator):
    """This test asserts that the policies are working as expected and this behavior does not change after scaling"""
    responses = client.get_many("/get", 5, auth=auth)
    responses.assert_all(status_code=200)

    assert client.get("/get", auth=auth).status_code == 429

    time.sleep(60)

    assert gateway.deployment.replicas > 1

    responses = client.get_many("/get", 5, auth=auth)
    responses.assert_all(status_code=200)

    assert client.get("/get", auth=auth).status_code == 429
