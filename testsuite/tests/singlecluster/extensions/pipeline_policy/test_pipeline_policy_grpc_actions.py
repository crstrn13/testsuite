"""Tests for PipelinePolicy with gRPC action method and conditional response headers."""

import pytest

from testsuite.kubernetes import Selector
from testsuite.kubernetes.deployment import Deployment
from testsuite.kubernetes.service import Service, ServicePort

pytestmark = [pytest.mark.kuadrant_only, pytest.mark.extensions]


@pytest.fixture(scope="module")
def threat_assessment_service(request, cluster, blame, module_label):
    """Deploys the ThreatAssessmentService gRPC backend"""
    name = blame("threat")
    match_labels = {"app": module_label, "deployment": name}

    deployment = Deployment.create_instance(
        cluster,
        name,
        container_name="threat-assessment",
        image="quay.io/kuadrant/threat-assessment-service:latest",
        ports={"grpc": 8080},
        selector=Selector(matchLabels=match_labels),
        labels={"app": module_label},
    )
    request.addfinalizer(deployment.delete)
    deployment.commit()
    deployment.wait_for_ready()

    service = Service.create_instance(
        cluster,
        name,
        selector=match_labels,
        ports=[ServicePort(name="grpc", port=8080, targetPort="grpc")],
        labels={"app": module_label},
    )
    request.addfinalizer(service.delete)
    service.commit()
    return service


THREAT_THRESHOLD = 50


@pytest.fixture(scope="module")
def pipeline_policy(pipeline_policy, threat_assessment_service):  # pylint: disable=unused-argument
    """Configure PipelinePolicy with gRPC call and response headers referencing the result."""
    svc_url = (
        f"grpc://{threat_assessment_service.name()}.{threat_assessment_service.namespace()}.svc.cluster.local:8080"
    )
    pipeline_policy.add_action_method(
        name="assess-threat",
        url=svc_url,
        service="threat.v1.ThreatAssessmentService",
        method="AssessRequest",
        message_template="threat.v1.ThreatRequest{uri: request.path, source_ip: source.address}",
    )

    pipeline_policy.add_request_grpc_method(
        method="assess-threat",
        var="threatResponse",
    )

    pipeline_policy.add_response_headers(
        [["x-threat-assessed", "true"]],
        predicate=f"threatResponse.threat_level < {THREAT_THRESHOLD}",
    )
    pipeline_policy.add_response_headers(
        [["x-threat-threshold", str(THREAT_THRESHOLD)]],
        predicate=f"threatResponse.threat_level < {THREAT_THRESHOLD}",
    )

    return pipeline_policy


def test_request_allowed(client):
    """Request with low threat level passes and gets response headers."""
    response = client.get("/get")
    assert response.status_code == 200
    assert response.headers.get("x-threat-assessed") == "true"
    assert response.headers.get("x-threat-threshold") == str(THREAT_THRESHOLD)


def test_threat_response_headers(client):
    """Response headers reflect threat assessment result on different paths."""
    response = client.get("/anything")
    assert response.status_code == 200
    assert response.headers.get("x-threat-assessed") == "true"
