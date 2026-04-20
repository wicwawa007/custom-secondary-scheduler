# How to run

## Run tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Run cluster, build scheduler image and deploy

```bash
minikube start --nodes 3
docker build -t secondary-scheduler:latest .
minikube image load secondary-scheduler:latest
./scripts/deploy.sh scheduler-system secondary-scheduler:latest
kubectl rollout status deployment/secondary-scheduler -n scheduler-system
```

## Run workflow

```bash
kubectl apply -f examples/pod-single.yaml
kubectl apply -f examples/pod-gang.yaml
kubectl get pods -o wide
kubectl get nodes -o wide
```


# Extra point discussions

## Implemented Retry mechanism

Unschedulable Pods or gangs are retried with exponential backoff:

- initial backoff: 5 seconds
- doubles on each failure
- capped at 30 seconds

This avoids hot-looping on workloads that cannot yet fit.

## Scalability discussion

This implementation intentionally uses polling for simplicity. If extended for large clusters, likely improvements would be:

- replace polling with watch-based updates and maintain node cache freshness with seperate threads
- use priority queues for node selections instead of keeping runnig sort()
- add metrics and tracing

