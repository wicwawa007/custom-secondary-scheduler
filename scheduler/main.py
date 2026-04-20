import os
import time

from scheduler.client import K8sClient
from scheduler.core import Scheduler


def main() -> int:
    scheduler_name = os.getenv("SCHEDULER_NAME", "secondary-scheduler")

    k8s = K8sClient()
    scheduler = Scheduler(
        k8s_client=k8s,
        scheduler_name=scheduler_name,
        retry_backoff_seconds=5,
        max_retry_backoff_seconds=30,
    )

    while True:
        try:
            scheduler.schedule()
        except Exception as exc:
            print(f"schedule failed: {exc}", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
