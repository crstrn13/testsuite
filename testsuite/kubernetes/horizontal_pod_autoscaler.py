from testsuite.kubernetes import KubernetesObject
from testsuite.kubernetes.deployment import Deployment


class HorizontalPodAutoscaler(KubernetesObject):
    """Kubernetes Horizontal Pod Autoscaler object"""

    @classmethod
    def create_instance(
        cls,
        cluster,
        name,
        deployment: Deployment,
        metric: list[dict],
        min_replicas: int = 1,
        max_replicas: int = 10,
    ):
        model: dict = {
            "kind": "HorizontalPodAutoscaler",
            "apiVersion": "autoscaling/v2",
            "metadata": {
                "name": name,
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": deployment.name(),
                },
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
            },
            "metrics": metric
        }
        return cls(model, context=cluster.context)

