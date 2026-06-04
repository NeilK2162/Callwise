# Callwise — Infrastructure

Kubernetes topology (PRD §15.1). Independently autoscaled deployments + managed stateful
services.

| Component | Manifest | Scaling |
|---|---|---|
| control-api | `k8s/control-api.yaml` | HPA on CPU, 2–10 |
| webhook-ingest | `k8s/webhook-ingest.yaml` | HPA on CPU/RPS, 2–20 |
| dialer-worker | `k8s/dialer-worker.yaml` | KEDA on `dial:stream` lag, 3–100 |
| verification-worker | `k8s/verification-worker.yaml` | KEDA on `verify:stream` lag, 2–40 |
| reconciler | `k8s/reconciler.yaml` | fixed 2, leader-elected |
| migrate (pre-deploy) | `k8s/migrate-job.yaml` | Job |

Managed / stateful (provisioned outside these manifests): Postgres (RDS primary + read
replica, Multi-AZ), Redis (ElastiCache cluster mode, AOF on), S3 (+ lifecycle to Glacier),
PgBouncer (`pgbouncer/pgbouncer.ini`, transaction mode).

## Apply order

```bash
kubectl apply -f k8s/config.example.yaml      # ConfigMap + Secret (use real secrets!)
kubectl apply -f k8s/migrate-job.yaml         # run migrations first
kubectl apply -f k8s/control-api.yaml
kubectl apply -f k8s/webhook-ingest.yaml
kubectl apply -f k8s/dialer-worker.yaml       # requires KEDA installed in-cluster
kubectl apply -f k8s/verification-worker.yaml
kubectl apply -f k8s/reconciler.yaml
```

KEDA must be installed (`https://keda.sh`) for the `redis-streams` triggers.

## Local dev

Use the root `docker-compose.yml` instead — it brings up Postgres, PgBouncer, Redis,
MinIO, both APIs, all workers, and the frontend with mock providers.
