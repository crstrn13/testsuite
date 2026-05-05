"""Configure all the components through Kuadrant,
all methods are placeholders for now since we do not work with Kuadrant"""

import logging

import pytest
from dynaconf import ValidationError
from openshift_client import selector

from testsuite.backend.httpbin import Httpbin
from testsuite.config import settings
from testsuite.gateway import GatewayRoute, Gateway, Hostname, GatewayListener
from testsuite.gateway.envoy import Envoy
from testsuite.gateway.envoy.route import EnvoyVirtualRoute
from testsuite.gateway.gateway_api.gateway import KuadrantGateway
from testsuite.gateway.gateway_api.route import HTTPRoute
from testsuite.httpx import KuadrantClient
from testsuite.kuadrant import KuadrantCR
from testsuite.kuadrant.policy.authorization.auth_policy import AuthPolicy
from testsuite.kuadrant.policy.rate_limit import RateLimitPolicy
from testsuite.kubernetes.api_key import APIKey
from testsuite.kubernetes.client import KubernetesClient
from testsuite.tracing.jaeger import JaegerClient
from testsuite.tracing.tempo import RemoteTempoClient

logger = logging.getLogger(__name__)


def _get_tracing_client(config):
    """Get or create a cached tracing client for upstream leak detection"""
    stash = config.stash
    key = pytest.StashKey[object]()

    cached = stash.get(key, None)
    if cached is not None:
        return cached if cached else None

    try:
        settings.validators.validate(only=["tracing"])
        cls = JaegerClient if settings["tracing"]["backend"] == "jaeger" else RemoteTempoClient
        client = KuadrantClient(verify=False)
        tracing = cls(settings["tracing"]["collector_url"], settings["tracing"]["query_url"], client)
        stash[key] = tracing
        return tracing
    except (KeyError, ValidationError):
        logger.debug("Tracing not configured, upstream leak detection disabled")
        stash[key] = False
        return None


def _check_upstream_leak(client, tracing_client):
    """Verify rejected requests did not leak to the upstream httpbin backend"""
    for req_id in getattr(client, "rejected_request_ids", []):
        traces = tracing_client.get_traces(service="wasm-shim", tags={"request_id": req_id})
        for trace in traces:
            services = trace.get_process_services()
            assert "httpbin" not in services, (
                f"Upstream leak detected: rejected request {req_id} reached "
                f"upstream 'httpbin'. Services in trace: {services}"
            )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    """Clear rejected request tracking for data_plane tests after setup completes"""
    yield
    marker = item.get_closest_marker("data_plane")
    if not marker:
        return
    client = item.funcargs.get("client")
    if client and hasattr(client, "rejected_request_ids"):
        client.rejected_request_ids.clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):  # pylint: disable=unused-argument
    """Check data_plane tests for upstream leaks via tracing before fixture cleanup"""
    marker = item.get_closest_marker("data_plane")
    if marker:
        client = item.funcargs.get("client")
        rejected_ids = getattr(client, "rejected_request_ids", []) if client else []
        if rejected_ids:
            tracing_client = _get_tracing_client(item.config)
            if tracing_client:
                _check_upstream_leak(client, tracing_client)

    yield


@pytest.fixture(scope="session")
def second_namespace(testconfig, skip_or_fail) -> KubernetesClient:
    """Kubernetes client for the secondary namespace located on the same cluster as primary cluster"""
    project = testconfig["service_protection"]["project2"]
    client = testconfig["control_plane"]["cluster"].change_project(testconfig["service_protection"]["project2"])
    if client is None:
        skip_or_fail("Tests requires second_project but service_protection.project2 is not set")
    if not client.connected:
        pytest.fail(f"You are not logged into Kubernetes or the namespace for {project} doesn't exist")
    return client


@pytest.fixture(scope="module")
def authorization_name(blame):
    """Name of the Authorization resource, can be overriden to include more dependencies"""
    return blame("authz")


@pytest.fixture(scope="module")
def authorization(request, kuadrant, route, gateway, blame, cluster, label):  # pylint: disable=unused-argument
    """Authorization object (In case of Kuadrant AuthPolicy)"""
    target_ref = request.getfixturevalue(getattr(request, "param", "route"))

    if kuadrant:
        return AuthPolicy.create_instance(cluster, blame("authz"), target_ref, labels={"testRun": label})
    return None


@pytest.fixture(scope="module")
def rate_limit(kuadrant, cluster, blame, request, module_label, route, gateway):  # pylint: disable=unused-argument
    """
    Rate limit object.
    Request is used for indirect parametrization, with two possible parameters:
        1. `route` (default)
        2. `gateway`
    """
    target_ref = request.getfixturevalue(getattr(request, "param", "route"))

    if kuadrant:
        return RateLimitPolicy.create_instance(cluster, blame("limit"), target_ref, labels={"testRun": module_label})
    return None


@pytest.fixture(scope="module", autouse=True)
def commit(request, authorization, rate_limit):
    """Commits all important stuff before tests"""
    for component in [authorization, rate_limit]:
        if component is not None:
            request.addfinalizer(component.delete)
            component.commit()
            component.wait_for_ready()


@pytest.fixture(scope="session")
def kuadrant(request, system_project):
    """Returns Kuadrant instance if exists, or None"""
    if request.config.getoption("--standalone"):
        return None

    with system_project.context:
        kuadrant = selector("kuadrant").object(cls=KuadrantCR)

    return kuadrant


@pytest.fixture(scope="session")
def otel_env(testconfig):
    """Returns OTEL environment variables for backends if tracing is configured"""
    try:
        testconfig.validators.validate(only=["tracing"])
        collector_url = testconfig["tracing"]["collector_url"]
    except (KeyError, ValidationError):
        return None

    host = collector_url.split("://")[-1].rsplit(":", 1)[0]
    return [
        {"name": "OTEL_TRACING_ENABLED", "value": "true"},
        {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": f"grpc://{host}:4317"},
        {"name": "OTEL_EXPORTER_OTLP_INSECURE", "value": "true"},
    ]


@pytest.fixture(scope="session")
def backend(request, cluster, blame, label, testconfig, otel_env):
    """Deploys Httpbin backend"""
    image = testconfig["httpbin"]["image"]
    httpbin = Httpbin(cluster, blame("httpbin"), label, image, env=otel_env)
    request.addfinalizer(httpbin.delete)
    httpbin.commit()
    return httpbin


@pytest.fixture(scope="session")
def gateway(request, kuadrant, cluster, blame, label, testconfig, wildcard_domain) -> Gateway:
    """Deploys Gateway that wires up the Backend behind the reverse-proxy and Authorino instance"""
    if kuadrant:
        gw = KuadrantGateway.create_instance(cluster, blame("gw"), {"app": label})
        gw.add_listener(GatewayListener(hostname=wildcard_domain))
    else:
        authorino = request.getfixturevalue("authorino")
        gw = Envoy(
            cluster,
            blame("gw"),
            authorino,
            testconfig["service_protection"]["envoy"]["image"],
            labels={"app": label},
        )
    request.addfinalizer(gw.delete)
    gw.commit()
    gw.wait_for_ready()
    return gw


@pytest.fixture(scope="module")
def domain_name(blame) -> str:
    """Domain name"""
    return blame("hostname")


@pytest.fixture(scope="module")
def hostname(gateway, exposer, domain_name) -> Hostname:
    """Exposed Hostname object"""
    hostname = exposer.expose_hostname(domain_name, gateway)
    return hostname


@pytest.fixture(scope="module")
def route(request, kuadrant, gateway, blame, hostname, backend, module_label) -> GatewayRoute:
    """Route object"""
    if kuadrant:
        route = HTTPRoute.create_instance(gateway.cluster, blame("route"), gateway, {"app": module_label})
    else:
        route = EnvoyVirtualRoute.create_instance(gateway.cluster, blame("route"), gateway)
    route.add_hostname(hostname.hostname)
    route.add_backend(backend)
    request.addfinalizer(route.delete)
    route.commit()
    return route


@pytest.fixture(scope="module")
def client(route, hostname):  # pylint: disable=unused-argument
    """Returns httpx client to be used for requests"""
    client = hostname.client()
    yield client
    client.close()


@pytest.fixture(scope="module")
def create_api_key(blame, request, cluster):
    """Creates API key Secret"""

    def _create_secret(
        name, label_selector, api_key, ocp: KubernetesClient = cluster, annotations: dict[str, str] = None
    ):
        secret_name = blame(name)
        secret = APIKey.create_instance(ocp, secret_name, label_selector, api_key, annotations)
        request.addfinalizer(lambda: secret.delete(ignore_not_found=True))
        secret.commit()
        return secret

    return _create_secret
