# Configure the Google Cloud Provider for infrastructure deployment
provider "google" {
  project = "predictive-hpa-thesis"                   # Target GCP Project ID
  region  = "us-central1"                             # Main deployment region
}

# Initialize the managed Kubernetes cluster (GKE Control Plane)
resource "google_container_cluster" "primary" {
  name                     = "predictive-hpa-cluster"
  location                 = "us-central1-a"          # Zonal cluster setup to optimize lab budget
  remove_default_node_pool = true                     # Remove default pool for granular custom node management via IaC
  initial_node_count       = 1
  deletion_protection      = false                    # Disable protection to allow seamless 'terraform destroy' cycles during testing
}

# Create a dedicated Node Pool for hosting workloads and ML-driven auto-scaling frameworks
resource "google_container_node_pool" "primary_nodes" {
  name       = "main-node-pool"
  location   = "us-central1-a"
  cluster    = google_container_cluster.primary.name  # Dynamic reference ensuring the cluster initializes first
  
  # FinOps Strategy: Dynamic scaling prevents idle compute expenses when workload is low
  autoscaling {
    min_node_count = 1
    max_node_count = 3                                # Upper boundary to cap maximum infrastructure costs
  }

  # Hardware specifications and access scopes for each Worker Node
  node_config {
    machine_type = "e2-standard-2"                    # 2 vCPUs, 8GB RAM - optimal for running K8s agents and metrics gathering
    disk_size_gb = 30                                 # Storage footprint allocation for OS and ephemeral container volumes
    spot         = true                               # FinOps Strategy: Utilizes Spot VMs to slash compute costs by up to 60-80%
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"] # Full API scope required for predictive metrics tools to interact with GCP APIs
  }
}