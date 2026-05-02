import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

POD_GROUP_ANNOTATION = "scheduler.example.com/pod-group"
PRIORITY_ANNOTATION = "scheduler.example.com/priority"



def pod_priority(pod) -> int:
    annotations = pod.metadata.annotations or {}
    if PRIORITY_ANNOTATION in annotations:
        try:
            return int(annotations[PRIORITY_ANNOTATION])
        except ValueError:
            pass
    return 0


@dataclass
class PodBatch:
    group: str
    pods: List

    def key(self) -> str:
        if self.group:
            return f"group:{self.group}"
        p = self.pods[0]
        return f"pod:{p.metadata.namespace}/{p.metadata.name}"

    def priority(self) -> int:
        return max(pod_priority(p) for p in self.pods)


class Scheduler:
    def __init__(
        self,
        k8s_client,
        scheduler_name: str,
        retry_backoff_seconds: float = 5.0,
        max_retry_backoff_seconds: float = 30.0,
    ):
        self.k8s = k8s_client
        self.scheduler_name = scheduler_name
        self.retry_backoff_seconds = retry_backoff_seconds
        self.max_retry_backoff_seconds = max_retry_backoff_seconds
        self.retry_next_time: Dict[str, Tuple[float, float]] = {}

    def schedule(self) -> None:
        pending = self.k8s.list_pending_pods(self.scheduler_name)
        if not pending:
            return

        running = self.k8s.list_scheduled_pods(self.scheduler_name)
        nodes = self.k8s.list_nodes()

        state = self._build_state(nodes, running)
        batches = self._order_batches(self._group_pending_pods(pending))

        for batch in batches:
            if not self._ready_to_retry(batch):
                continue
            try:
                self._schedule_batch(batch, state)
                self._clear_retry(batch)
            except Exception:
                self._bump_retry(batch)

    def _build_state(self, nodes, scheduled_pods) -> dict:
        occupants = {}
        for pod in scheduled_pods:
            if pod.spec.node_name:
                occupants[pod.spec.node_name] = pod

        free_nodes = []
        for node in nodes:
            if node.metadata.name not in occupants:
                free_nodes.append(node.metadata.name)

        free_nodes.sort()
        return {
            "free_nodes": free_nodes,
            "occupants": occupants,
        }

    def _group_pending_pods(self, pods) -> List[PodBatch]:
        grouped = {}
        out: List[PodBatch] = []

        for pod in pods:
            annotations = pod.metadata.annotations or {}
            group = annotations.get(POD_GROUP_ANNOTATION, "")
            if not group:
                out.append(PodBatch(group="", pods=[pod]))
            else:
                grouped.setdefault(group, []).append(pod)

        for group, group_pods in grouped.items():
            group_pods.sort(key=lambda p: (-pod_priority(p), p.metadata.name))
            out.append(PodBatch(group=group, pods=group_pods))

        return out

    def _order_batches(self, batches: List[PodBatch]) -> List[PodBatch]:
        return sorted(
            batches,
            key=lambda b: (-b.priority(), len(b.pods), b.key()),
        )

    def _schedule_batch(self, batch: PodBatch, state: dict) -> None:
        need = len(batch.pods)
        free_nodes = state["free_nodes"]

        if len(free_nodes) < need:
            preempted_pods = self._choose_preempted_pods(state, batch)
            for preempted_pod in preempted_pods:
                self.k8s.delete_pod(preempted_pod.metadata.namespace, preempted_pod.metadata.name)
                node_name = preempted_pod.spec.node_name
                if node_name in state["occupants"]:
                    del state["occupants"][node_name]
                    free_nodes.append(node_name)
            free_nodes.sort()

        if len(free_nodes) < need:
            raise RuntimeError("insufficient capacity after preemption")

        chosen_nodes = free_nodes[:need]
        for pod, node_name in zip(batch.pods, chosen_nodes):
            self.k8s.bind_pod(pod, node_name)
            pod.spec.node_name = node_name
            state["occupants"][node_name] = pod

        state["free_nodes"] = free_nodes[need:]

    def _choose_preempted_pods(self, state: dict, batch: PodBatch):
        shortage = len(batch.pods) - len(state["free_nodes"])
        if shortage <= 0:
            return []

        incoming_priority = batch.priority()
        preempted_pods = [
            pod
            for pod in state["occupants"].values()
            if pod_priority(pod) < incoming_priority
        ]
        preempted_pods.sort(key=lambda p: (pod_priority(p), p.metadata.name))

        if len(preempted_pods) < shortage:
            raise RuntimeError("not enough lower-priority nodes")

        return preempted_pods[:shortage]

    def _ready_to_retry(self, batch: PodBatch) -> bool:
        next_time = self.retry_next_time.get(batch.key())
        return next_time is None or time.time() >= next_time[0]

    def _bump_retry(self, batch: PodBatch) -> None:
        key = batch.key()
        backoff = self.retry_next_time.get(key, (0.0, 0.0))[1]
        if backoff == 0.0:
            backoff = self.retry_backoff_seconds
        else:
            backoff = min(backoff * 2, self.max_retry_backoff_seconds)
        self.retry_next_time[key] = (time.time() + backoff, backoff)

    def _clear_retry(self, batch: PodBatch) -> None:
        self.retry_next_time.pop(batch.key(), None)
