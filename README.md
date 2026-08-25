# Kubernetes-Native Predictive Autoscaling

An LSTM-based predictive Horizontal Pod Autoscaler for Kubernetes. Instead of waiting for CPU to cross a threshold and then reacting, it forecasts the near-term load and hands that forecast to the native HPA through the standard External Metrics API, so the cluster scales while the trend is still building rather than after the spike has already landed.

## The idea

Reactive autoscaling is always a step behind. By the time CPU crosses its target and new Pods get scheduled, pulled, and started, the burst has already cost you tail latency. The premise here is to scale on a prediction of demand instead of on a metric that has already moved.

A small recurrent model reads the recent CPU history, predicts the next value, and publishes it as a custom metric that the HPA consumes directly. The application does not change and the HPA is not replaced; it simply reads a leading metric instead of a lagging one, and the usual HPA behaviour (rate limiting, gradual convergence, the scale-down window) stays in place. If the forecast ever goes stale, the HPA falls back to its CPU target, so the predictive path only ever adds to a working reactive baseline.

## Design

The main constraint driving the design is that monitoring a system under heavy load costs resources and can disturb the very thing you are trying to measure. So observability is kept off the cluster: time-series storage and the heavy computation live in an external backend (Datadog), and only a lightweight agent and a small inference loop run on the workers. Worker-node memory and disk stay with the application.

Everything is wired through standard, CNCF-conformant interfaces: the External Metrics API, an APIService for aggregation, a DaemonSet for the agent, and the v2 HPA. Because there is no provider-specific coupling on the scaling path, portability is a property of the design rather than of any one cloud. It is evaluated here on GKE; the one vendor-specific piece, the Datadog backend, sits behind the same external-metrics contract and could be swapped for another time-series store without touching anything inside the cluster.

The whole environment is defined as code, so a run can be rebuilt from scratch rather than hand-tuned.

## How the pieces fit

At runtime the flow is a loop. A node agent streams CPU to the external time-series database. The LSTM inference Pod reads the recent window, predicts the next value, applies a small safety buffer, and writes the forecast back. A cluster agent exposes that forecast through the External Metrics API as `k8s.app.predicted_traffic`. The native HPA reads it and scales the `nginx-web` Deployment ahead of demand.

Setup is code and the parts are decoupled, so the order is flexible. Terraform stands up the GKE cluster and a custom node pool. A set of Kubernetes manifests bring up the Datadog agents, the RBAC, the External Metrics provider, the application, and the predictive HPA. The LSTM is trained offline, at whatever point is convenient, into two artifacts (the network weights and the fitted scaler); those are baked into the inference image, which is pushed to a registry and consumed in the cluster. None of these steps depends on a strict sequence beyond the cluster existing before things are deployed onto it.

## Repository layout

- `Infrastructure/` — Terraform for the GKE cluster and custom node pool
- `k8s/` — manifests: Datadog agents, RBAC, the External Metrics APIService, the app Deployment, and the predictive HPA
- `model/` — the trained LSTM weights and the fitted scaler
- `source/` — the inference microservice
- `training_predictive.ipynb` — offline LSTM training
- `Dockerfile` — image for the inference service
- `loadtest_sample.js` — k6 five-phase flash-sale workload (used for both runs)
- `sine_wave.js` — k6 periodic workload

## The model

Trained offline from CPU telemetry. The series is min-max scaled, cut into ten-observation windows that predict the eleventh, and fed to a single 64-unit LSTM layer with a dense output (Adam, mean-squared error, 100 epochs). Training writes the weights and the scaler into `model/`; inference itself does no training. Scaling to `[0, 1]` is what keeps training stable, and the scaler is saved so the same transform can be inverted at serving time.

## Evaluation

The predictive controller is compared against the native reactive HPA on GKE under an identical five-phase flash-sale workload from k6, about 492,000 requests per run. Only the metric the HPA reads differs: native CPU for the baseline, the forecast for the predictive run. Everything else (cluster, machine type, replica bounds, load profile) is held fixed, and the two runs go back to back on the same cluster. Client-side percentiles come from k6; server-side CPU, replica counts, and scaling events come from Datadog.

On the reported run, median, P90, and P95 request duration dropped by 15.31%, 12.68%, and 11.60% respectively, with zero HTTP failures on both configurations. The cost is a handful of cold-start outliers during aggressive scale-up and roughly a quarter more average replica provisioning: the buffer showing up as spend. The full analysis, including the trade-offs, is in the paper.

Demo video: https://drive.google.com/file/d/1i5NvWGNc_1vW-w48huaFgqTBP4bhe20M/view?usp=sharing

## Notes

- Datadog API and application keys are supplied through a Kubernetes Secret and are not committed to the repository.
- `terraform.tfstate` and credential files are excluded via `.gitignore`.
- Worker nodes are Spot VMs; the node pool autoscales between one and three nodes. Spot reclamation also doubles as a small, free test of self-healing.
