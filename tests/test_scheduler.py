import unittest
from types import SimpleNamespace

from scheduler.core import Scheduler, POD_GROUP_ANNOTATION


def make_pod(name, priority, group="", namespace="default", node_name="", phase="Pending"):
    annotations = {}
    if group:
        annotations[POD_GROUP_ANNOTATION] = group
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            namespace=namespace,
            annotations=annotations,
        ),
        spec=SimpleNamespace(
            scheduler_name="secondary-scheduler",
            priority=priority,
            node_name=node_name,
        ),
        status=SimpleNamespace(phase=phase),
    )


def make_node(name, unschedulable=False):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        spec=SimpleNamespace(unschedulable=unschedulable),
    )


class FakeK8sClient:
    def __init__(self, pending=None, scheduled=None, nodes=None):
        self.pending = pending or []
        self.scheduled = scheduled or []
        self.nodes = nodes or []
        self.binds = []
        self.deletes = []

    def list_pending_pods(self, scheduler_name):
        return list(self.pending)

    def list_scheduled_pods(self, scheduler_name):
        return list(self.scheduled)

    def list_nodes(self):
        return list(self.nodes)

    def bind_pod(self, pod, node_name):
        self.binds.append(f"{pod.metadata.name}->{node_name}")

    def delete_pod(self, namespace, name):
        self.deletes.append(f"{namespace}/{name}")


class SchedulerTests(unittest.TestCase):
    def test_schedules_single_pod_to_free_node(self):
        c = FakeK8sClient(
            pending=[make_pod("p1", 10)],
            nodes=[make_node("n1"), make_node("n2")],
        )
        s = Scheduler(c, "secondary-scheduler")
        s.schedule()
        self.assertEqual(c.binds, ["p1->n1"])

    def test_gang_scheduling_all_or_none(self):
        c = FakeK8sClient(
            pending=[make_pod("g1-a", 10, "g1"), make_pod("g1-b", 10, "g1")],
            nodes=[make_node("n1")],
        )
        s = Scheduler(c, "secondary-scheduler")
        s.schedule()
        self.assertEqual(c.binds, [])

    def test_gang_scheduling_binds_entire_group(self):
        c = FakeK8sClient(
            pending=[make_pod("g1-a", 10, "g1"), make_pod("g1-b", 10, "g1")],
            nodes=[make_node("n1"), make_node("n2")],
        )
        s = Scheduler(c, "secondary-scheduler")
        s.schedule()
        self.assertEqual(len(c.binds), 2)

    def test_preemption_for_higher_priority_pod(self):
        resident = make_pod("low", 1, node_name="n1", phase="Running")
        c = FakeK8sClient(
            pending=[make_pod("high", 100)],
            scheduled=[resident],
            nodes=[make_node("n1")],
        )
        s = Scheduler(c, "secondary-scheduler")
        s.schedule()
        self.assertEqual(c.deletes, ["default/low"])
        self.assertEqual(c.binds, ["high->n1"])


if __name__ == "__main__":
    unittest.main()
