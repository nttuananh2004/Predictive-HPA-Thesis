# Kubernetes-Native Predictive Autoscaling

An LSTM-based predictive Horizontal Pod Autoscaler (HPA) for Kubernetes. It forecasts near-term traffic and feeds the forecast to the native HPA through the standard External Metrics API, so the cluster scales ahead of demand instead of after a CPU threshold is crossed.

Time-series storage and heavy computation are offloaded to an external backend (Datadog); only a lightweight agent and an inference loop run in the cluster. The environment is provisioned with Terraform and evaluated on Google Kubernetes Engine (GKE) against the native reactive HPA using k6.

Demo video: https://drive.google.com/file/d/1i5NvWGNc_1vW-w48huaFgqTBP4bhe20M/view?usp=sharing

## Architecture

```
Terraform            -> GKE cluster + node pool
Node agent           -> streams CPU to Datadog (external TSDB)
LSTM inference Pod    -> reads history, writes forecast to Datadog
Cluster agent         -> exposes forecast via External Metrics API
native HPA            -> reads forecast, scales nginx-web
```

The inference service reads the recent CPU window, predicts the next value, applies a safety buffer, and publishes it as the custom metric `k8s.app.predicted_traffic`. The cluster agent registers as the `external.metrics.k8s.io` provider so the HPA can consume it.

## Repository structure

| Path | Description |
| --- | --- |
| `Infrastructure/` | Terraform for the GKE cluster and custom node pool |
| `k8s/` | Manifests: Datadog agents, RBAC, External Metrics APIService, app Deployment, predictive HPA |
| `model/` | Trained LSTM weights and fitted scaler |
| `source/` | Inference microservice |
| `training_predictive.ipynb` | Offline LSTM training notebook |
| `Dockerfile` | Image for the inference service |
| `loadtest_default.js` | k6 reactive baseline (five-phase pyramid) |
| `loadtest-predictive.js` | k6 predictive run |
| `sine_wave.js` | k6 periodic workload |

## Prerequisites

- GCP project with the Kubernetes Engine API enabled, `gcloud` authenticated
- Terraform and `kubectl`
- Docker and a container registry (e.g. Google Artifact Registry)
- Datadog account with an API key and an Application key
- k6, and Python 3.10+ (TensorFlow, scikit-learn) to retrain the model

## Setup

Provision the cluster:

```bash
cd Infrastructure
terraform init
terraform apply
gcloud container clusters get-credentials predictive-hpa-cluster --zone us-central1-a
```

Create the Datadog secret (keys are not committed to the repo):

```bash
kubectl create secret generic datadog-secret \
  --from-literal=api-key=<DATADOG_API_KEY> \
  --from-literal=app-key=<DATADOG_APP_KEY>
```

The manifest reads it via `secretKeyRef`:

```yaml
- name: DD_API_KEY
  valueFrom:
    secretKeyRef:
      name: datadog-secret
      key: api-key
- name: DD_APP_KEY
  valueFrom:
    secretKeyRef:
      name: datadog-secret
      key: app-key
```

Deploy the stack and app:

```bash
kubectl apply -f k8s/
```

Build and push the inference image, then update the image reference in the Deployment and re-apply:

```bash
docker build -t <REGISTRY>/predictive-inference:latest .
docker push <REGISTRY>/predictive-inference:latest
```

Verify the external metric:

```bash
kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1" | jq .
kubectl get hpa
```

## Load tests

Run each scenario against the nginx-web endpoint:

```bash
k6 run loadtest_default.js      # reactive baseline
k6 run loadtest-predictive.js   # predictive HPA
k6 run sine_wave.js             # periodic workload
```

Client-side percentiles come from k6; server-side CPU, replica counts, and scaling events come from the Datadog dashboards.

## Retraining

Run `training_predictive.ipynb` end to end. It min-max scales the CPU telemetry, builds ten-observation supervised windows, trains a single 64-unit LSTM layer (Adam, MSE, 100 epochs), and exports the weights and scaler into `model/`.

## Results

Identical five-phase flash-sale workload, about 492,000 requests per run, zero HTTP failures on both:

| Metric | Reactive | Predictive | Delta |
| --- | --- | --- | --- |
| Median (P50) | 45.21 ms | 38.29 ms | -15.31% |
| P90 | 71.15 ms | 62.13 ms | -12.68% |
| P95 | 80.72 ms | 71.36 ms | -11.60% |
| HTTP failures | 0 | 0 | - |

Trade-off: a few cold-start outliers during aggressive scale-up and higher average replica provisioning. Full analysis is in the paper.

## Notes

- Datadog keys are provided via a Kubernetes Secret, not committed to the repo.
- `terraform.tfstate` and credential files are excluded via `.gitignore`.
- Worker nodes are Spot VMs; the node pool autoscales between 1 and 3 nodes.
