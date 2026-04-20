from typing import List, Optional

from kubernetes import client, config


class K8sClient:
    def __init__(self):
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.core = client.CoreV1Api()

    def list_pending_pods(self, scheduler_name: str) -> List[client.V1Pod]:
        field_selector = (
            f"spec.schedulerName={scheduler_name},"
            "spec.nodeName=,"
            "status.phase=Pending"
        )
        resp = self.core.list_pod_for_all_namespaces(
            field_selector=field_selector,
        )
        return resp.items

    def list_scheduled_pods(self, scheduler_name: str) -> List[client.V1Pod]:
        field_selector = f"spec.schedulerName={scheduler_name}"
        resp = self.core.list_pod_for_all_namespaces(
            field_selector=field_selector,
        )
        out = []
        for pod in resp.items:
            if pod.spec.node_name and pod.status.phase not in ("Succeeded", "Failed"):
                out.append(pod)
        return out

    def list_nodes(self) -> List[client.V1Node]:
        resp = self.core.list_node()
        return [n for n in resp.items if not n.spec.unschedulable]

    def bind_pod(self, pod: client.V1Pod, node_name: str) -> None:
        body = client.V1Binding(
            metadata=client.V1ObjectMeta(name=pod.metadata.name),
            target=client.V1ObjectReference(
                api_version="v1",
                kind="Node",
                name=node_name,
            ),
        )
        # Depending on kubernetes-client version, create_namespaced_pod_binding is the
        # most reliable helper for the /binding subresource.
        self.core.create_namespaced_pod_binding(
            name=pod.metadata.name,
            namespace=pod.metadata.namespace,
            body=body,
        )

    def delete_pod(self, namespace: str, name: str) -> None:
        self.core.delete_namespaced_pod(
            name=name,
            namespace=namespace,
        )
