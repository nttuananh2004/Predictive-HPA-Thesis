Kubernetes-Native Predictive Autoscaling

An LSTM-based Predictive Horizontal Pod Autoscaler (HPA) for Kubernetes. Instead of reacting after a CPU threshold is breached, it forecasts near-term traffic and feeds that forecast to the native Kubernetes HPA through the standard External Metrics API, so the cluster provisions capacity ahead of demand.

All time-series storage and heavy computation are offloaded to an external backend (Datadog), so only a lightweight telemetry agent and a small inference loop run inside the cluster. The whole environment is provisioned reproducibly with Terraform, and the framework is evaluated on Google Kubernetes Engine (GKE) against the native reactive HPA under a flash-sale workload generated with k6.

Demo

📹 Demonstration video: https://drive.google.com/file/d/1i5NvWGNc_1vW-w48huaFgqTBP4bhe20M/view?usp=sharing

How it works
Terraform (IaC)  ──▶  GKE cluster + node pool
Node agent (DaemonSet)  ──stream CPU──▶  Datadog (external TSDB)
LSTM inference Pod  ──read history / write forecast──▶  Datadog
Cluster agent (External Metrics API)  ──expose forecast──▶  native HPA  ──▶  scale nginx-web
A lightweight agent streams node/Pod CPU to an external backend (worker-node memory and disk stay free for the app).
An offloaded LSTM reads the recent window, predicts the next value, applies a safety buffer, and publishes it back as a custom metric (k8s.app.predicted_traffic).
A cluster agent registers as the external.metrics.k8s.io provider so the native HPA reads the forecast and scales proactively.
Repository structure
Path	Description
Infrastructure/	Terraform definitions for the GKE cluster and custom node pool
k8s/	Kubernetes manifests: Datadog agents, RBAC, External Metrics APIService, app Deployment, and the predictive HPA
model/	Serialized LSTM artifacts (trained weights + fitted scaler) baked into the inference image
source/	Inference microservice (polling + forecast loop)
training_predictive.ipynb	Offline LSTM training notebook
Dockerfile	Container image for the inference service
loadtest_default.js	k6 script — reactive baseline (five-phase flash-sale pyramid)
loadtest-predictive.js	k6 script — predictive run (identical workload)
sine_wave.js	k6 script — periodic/seasonal workload
Prerequisites
A GCP project with the Kubernetes Engine API enabled, and the gcloud CLI authenticated
Terraform and kubectl
Docker and access to a container registry (e.g. Google Artifact Registry)
A Datadog account with an API key and an Application key
k6 for load testing, and Python 3.10+ (TensorFlow, scikit-learn) to (re)train the model
Quick start
1. Provision the cluster
bash
cd Infrastructure
terraform init
terraform apply
gcloud container clusters get-credentials predictive-hpa-cluster --zone us-central1-a
2. Create the Datadog secret

Do not hardcode API keys in the manifests. The Datadog credentials are read from a Kubernetes Secret, which is created out of band and never committed to the repository.

bash
kubectl create secret generic datadog-secret \
  --from-literal=api-key=<YOUR_DATADOG_API_KEY> \
  --from-literal=app-key=<YOUR_DATADOG_APP_KEY>

The agent manifest references it via secretKeyRef:

yaml
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
3. Deploy the observability stack and app
bash
kubectl apply -f k8s/

This installs the Datadog node agent (DaemonSet) and cluster agent, the RBAC, the External Metrics APIService, the nginx-web Deployment, and the predictive HPA.

4. Build and push the inference image
bash
docker build -t <YOUR_REGISTRY>/predictive-inference:latest .
docker push <YOUR_REGISTRY>/predictive-inference:latest
# update the image reference in the inference Deployment manifest, then re-apply
5. Verify the external metric is exposed
bash
kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1" | jq .
kubectl get hpa
Running the experiments

Run each k6 scenario against the nginx-web load-balancer endpoint:

bash
k6 run loadtest_default.js      # reactive baseline
k6 run loadtest-predictive.js   # predictive HPA
k6 run sine_wave.js             # periodic workload

Client-side percentiles come from the k6 summary; server-side CPU, replica counts, and scaling events are read from the Datadog dashboards.

Retraining the model

Open training_predictive.ipynb and run it end to end. It normalizes the CPU telemetry with a min–max scaler, builds ten-observation supervised windows, trains a single 64-unit LSTM layer (Adam, MSE, 100 epochs), and exports the weights and scaler into model/ for the inference image.

Results (summary)

Under an identical five-phase flash-sale workload (~492,000 requests per run), the predictive HPA reduced HTTP request duration versus the native reactive HPA, with zero HTTP failures on both runs:

Metric	Reactive	Predictive	Δ
Median (P50)	45.21 ms	38.29 ms	−15.31%
P90	71.15 ms	62.13 ms	−12.68%
P95	80.72 ms	71.36 ms	−11.60%
HTTP failures	0	0	—

The trade-off is a small number of cold-start outliers during aggressive scale-up and slightly higher average replica provisioning; see the paper for the full analysis.

Configuration & security notes
Datadog credentials are provided via a Kubernetes Secret (see step 2), not committed to the repo.
terraform.tfstate and any credential files are excluded via .gitignore.
Worker nodes use cost-optimized Spot VMs; the node pool autoscales between 1 and 3 nodes.
Academic context

This repository accompanies the paper "A Kubernetes-Native Predictive Autoscaling Framework: An Empirical Evaluation on Google Kubernetes Engine" (under submission). If you use this work, please cite the paper.
