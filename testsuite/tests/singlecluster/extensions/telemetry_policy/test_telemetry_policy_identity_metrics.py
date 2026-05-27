"""
Reproducer for https://github.com/Kuadrant/authorino/issues/607

TelemetryPolicy metric labels using CEL expressions that reference auth identity claims
fail because the wasm-shim serializes the parsed CEL AST (Rust Debug format) instead of
the original expression string. Authorino receives the AST representation and cannot parse
it as valid CEL.

This test uses OIDC/JWT auth with custom claims and metrics=True on AuthPolicy sections,
matching the bug report setup where per-section metrics are enabled.
"""

import pytest

from testsuite.httpx.auth import HttpxOidcClientAuth
from testsuite.kuadrant.extensions.telemetry_policy import TelemetryPolicy
from testsuite.kuadrant.policy.authorization import JsonResponse, ValueFrom
from testsuite.prometheus import has_label

pytestmark = [
    pytest.mark.observability,
    pytest.mark.limitador,
    pytest.mark.extensions,
    pytest.mark.issue("https://github.com/Kuadrant/authorino/issues/607"),
]

PROJECT_ID = "proj-abc123"


@pytest.fixture(scope="module")
def keycloak(keycloak):
    """Configure Keycloak with a custom user attribute mapped to JWT claims"""
    keycloak.realm.add_user_attributes("project_id", "Project ID")
    keycloak.client.add_user_attribute_mapper("project_id", "project_id")
    return keycloak


@pytest.fixture(scope="module")
def user(keycloak, blame):
    """Creates Keycloak user with custom attributes simulating Descope-like JWT claims"""
    return keycloak.realm.create_user(blame("user"), blame("pwd"), attributes={"project_id": [PROJECT_ID]})


@pytest.fixture(scope="module")
def auth(user, keycloak):
    """OIDC authentication"""
    return HttpxOidcClientAuth.from_user(keycloak.get_token, user=user)


@pytest.fixture(scope="module")
def authorization(authorization, keycloak):
    """AuthPolicy with OIDC identity and dynamic metadata response, metrics enabled on all sections"""
    authorization.identity.add_oidc("keycloak", keycloak.well_known["issuer"], metrics=True)
    authorization.responses.add_success_dynamic(
        "identity",
        JsonResponse(
            {
                "userid": ValueFrom("auth.identity.preferred_username"),
                "project_id": ValueFrom("auth.identity.project_id"),
            }
        ),
        metrics=True,
    )
    return authorization


@pytest.fixture(scope="module")
def telemetry_policy(cluster, blame, gateway):
    """TelemetryPolicy with labels referencing auth identity claims via CEL expressions"""
    policy = TelemetryPolicy.create_instance(cluster, blame("tp"), gateway)
    policy.add_label("user", "auth.identity.userid")
    policy.add_label("project_id", "auth.identity.project_id")
    return policy


@pytest.mark.parametrize(
    "metric, expected_value", [("authorized_calls", 3), ("authorized_hits", 3), ("limited_calls", 2)]
)
def test_telemetry_labels_with_identity_metrics(limitador_metrics, route, metric, expected_value, user):
    """
    Verify that TelemetryPolicy CEL-based metric labels referencing auth identity claims
    are correctly parsed and propagated to Limitador metrics when per-section metrics are enabled.
    """
    metrics_on_route = limitador_metrics.filter(has_label("limitador_namespace", f"{route.namespace()}/{route.name()}"))
    filtered = metrics_on_route.filter(has_label("__name__", metric))
    assert len(filtered.metrics) == 1, f"Expected exactly 1 '{metric}' metric, found {len(filtered.metrics)}"

    metric_data = filtered.metrics[0]["metric"]

    assert "user" in metric_data, f"'user' label missing from {metric} metric"
    assert "project_id" in metric_data, f"'project_id' label missing from {metric} metric"

    assert (
        metric_data["user"] == user.properties["username"]
    ), f"Expected user label '{user.properties['username']}', got '{metric_data['user']}'"
    assert (
        metric_data["project_id"] == PROJECT_ID
    ), f"Expected project_id label '{PROJECT_ID}', got '{metric_data['project_id']}'"

    assert filtered.values[0] == expected_value, f"Expected {metric} value {expected_value}, got {filtered.values[0]}"
