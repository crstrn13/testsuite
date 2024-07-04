"""Service related objects"""

from dataclasses import dataclass, asdict
from typing import Literal

from openshift_client import timeout

from testsuite.kubernetes import KubernetesObject


@dataclass
class ServicePort:
    """Kubernetes Service Port object"""

    name: str
    port: int
    targetPort: int | str  # pylint: disable=invalid-name


class Service(KubernetesObject):
    """Kubernetes Service object"""

    @classmethod
    def create_instance(
        cls,
        cluster,
        name,
        selector: dict[str, str],
        ports: list[ServicePort],
        labels: dict[str, str] = None,
        service_type: Literal["ClusterIP", "LoadBalancer", "NodePort", "ExternalName"] = None,
    ):
        """Creates new Service"""
        model: dict = {
            "kind": "Service",
            "apiVersion": "v1",
            "metadata": {
                "name": name,
                "labels": labels,
            },
            "spec": {"ports": [asdict(port) for port in ports], "selector": selector},
        }

        if service_type is not None:
            model["spec"]["type"] = service_type

        return cls(model, context=cluster.context)

    def get_port(self, name):
        """Returns port definition for a port with said name"""
        for port in self.model.spec.ports:
            if port["name"] == name:
                return port
        raise KeyError(f"No port with name {name} exists")

    @property
    def external_ip(self):
        """Returns LoadBalancer IP for this service"""
        if self.model.spec.type != "LoadBalancer":
            raise AttributeError("External IP can be only used with LoadBalancer services")
        return self.model.status.loadBalancer.ingress[0].ip

    def delete(self, ignore_not_found=True, cmd_args=None):
        """Deletes Service, introduces bigger waiting times due to LoadBalancer type"""
        with timeout(10 * 60):
            deleted = super(KubernetesObject, self).delete(ignore_not_found, cmd_args)
            return deleted
