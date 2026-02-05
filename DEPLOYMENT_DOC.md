# SWaT AI Guardian - Enterprise Deployment Manual

## 📖 Introduction
This document outlines the deployment, monitoring, and maintenance procedures for the **SWaT AI Guardian** system. This solution provides military-grade anomaly detection for Critical National Infrastructure (CNI) networks using advanced Unsupervised Deep Learning.

## 🌟 Solution Characteristics
Our solution is distinguished by the following enterprise-grade characteristics:

### 1. Zero-Trust Architecture
Unlike rule-based systems that look for *known* threats, our AI engine (Autoencoder) learns the **Physics of the Plant**. It trusts no one—any deviation from the laws of physics (e.g., tank level rising without pump activation) is flagged as an anomaly.

### 2. High Availability & Fault Tolerance
*   **Self-Healing**: Services are configured with `restart: always` policies. If a component (e.g., the Inference Engine) crashes, the orchestrator automatically restarts it without human intervention.
*   **Decoupled Design**: Using Apache Kafka ensures that temporary failures in the processing layer do not result in data loss; messages are buffered until services recover.

### 3. Scalable "Big Data" Foundation
*   **Horizontal Scalability**: The use of Apache Spark allows the analytics layer to scale horizontally across multiple nodes to handle millions of events per second.
*   **Containerization**: Docker-based deployment ensures "Write Once, Run Anywhere" capability, from local edge devices to Cloud Kubernetes clusters (EKS/GKE).

---

## 🛠️ Deployment Instructions

### System Requirements
*   **OS**: Windows 10/11 (WSL2), Linux (Ubuntu 20.04+), or macOS.
*   **RAM**: Minimum 8GB (16GB Recommended).
*   **GPU**: NVIDIA RTX Series (Recommended for training/inference speedup).

### Step-by-Step Installation

#### 1. Environment Setup
Ensure Docker Desktop is running and configured for WSL2 (on Windows).

#### 2. Clean Installation
Run the following commands to perform a fresh install:
```bash
# Stop any existing services
docker compose down --volumes

# Build and Start the stack
docker compose up --build -d
```
*Wait approximately 30-60 seconds for Kafka to stabilize.*

#### 3. Verification
Run `docker ps` to ensure the following containers are **Up**:
*   `swat-dashboard` (Port 8501)
*   `swat-api` (Port 8000)
*   `swat-inference`
*   `swat-kafka`
*   `swat-zookeeper`

---

## 🖥️ User Guide: The Dashboard

### Access
Open your browser to: **[http://localhost:8501](http://localhost:8501)**

### Controlling operations
1.  **Start/Stop**: Use the "RUN SYSTEM" toggle in the sidebar to pause/resume analytics.
2.  **Simulation Mode**:
    *   Select **"Normal Data"** to see the system validate standard operations.
    *   Select **"Attack Data"** to witness the AI detecting cyber-attacks in real-time.
3.  **Sensitivity**: Adjust the "DL Threshold Mult" slider.
    *   **1.0**: Standard Scientific Threshold (99.9th Percentile).
    *   **< 1.0**: Higher Sensitivity (More Alerts).
    *   **> 1.0**: Lower Sensitivity (Fewer False Positives).

---

## 🔧 Troubleshooting

| Symptom | Probable Cause | Resolution |
| :--- | :--- | :--- |
| **Dashboard shows "Connecting..." forever** | Kafka is not ready. | Wait 30s or restart: `docker restart swat-dashboard`. |
| **"System Status: Stopped"** | Docker containers down. | Run `bash start_system.sh` again. |
| **No alerts on Attack Data** | Threshold too high. | Lower the "Sensitivity" slider to 0.8 or 0.5. |
| **System feels slow** | Resource limits. | Increase Docker resource allocation (CPUs/RAM). |

---

## 📞 Support Escalation
For L3 Support, please route logs (`logs/system.log`) to the engineering team.

**Version**: 2.0.0-Production
**Build**: Stable
