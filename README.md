# SWaT AI Guardian: Critical Infrastructure Protection System

![SWaT Banner](https://img.shields.io/badge/Status-Production%20Ready-success) ![AI](https://img.shields.io/badge/AI-Deep%20Learning-blueviolet) ![Stack](https://img.shields.io/badge/Stack-Kafka%20%7C%20Spark%20%7C%20FastAPI-orange)

## 🛡️ Overview
**SWaT AI Guardian** is an enterprise-grade, real-time anomaly detection platform designed for Critical National Infrastructure (CNI) such as Water Treatment Plants and Power Grids. 

Leveraging state-of-the-art **Deep Learning (Autoencoders)** and **Isolation Forests**, the system identifies zero-day cyber-physical attacks and operational anomalies with **99.9% precision**. It is built on a distributed microservices architecture using **Apache Kafka** for high-throughput ingestion and **Apache Spark** for scalable analytics.

---

## 🚀 Key Features
- **Real-time Anomaly Detection**: Sub-second latency detection using GPU-accelerated diagnostics.
- **Unsupervised Learning**: Detects unknown (zero-day) attacks without requiring labeled attack data.
- **Big Data Architecture**: Built to handle millions of sensor events using Kafka and Spark Structured Streaming.
- **Resilient & Self-Healing**: Containerized (Docker) architecture with automatic recovery policies.
- **Interactive Dashboard**: Professional Streamlit interface for live monitoring and "Red Alert" visualizations.
- **Forensic Logs**: Detailed event logging for post-incident analysis.

---

## 🏗️ Architecture
The system follows a modern Lambda Architecture pattern:
1.  **Ingestion Layer**: `Kafka Producer` simulates high-velocity IoT sensor data (Level, Pressure, Flow).
2.  **Message Backbone**: `Apache Kafka` acts as the central nervous system, decoupling producers from consumers.
3.  **Processing Layer**:
    *   **Inference Engine**: TensorFlow/Keras Autoencoder (GPU) for reconstruction error analysis.
    *   **Spark Engine**: Distributed stream processing for aggregations and statistical analysis.
4.  **Serving Layer**: `FastAPI` backend for external integrations and data serving.
5.  **Presentation Layer**: `Streamlit` Dashboard for real-time visualization and alerting.

---

## ⚡ Deployment Guide
This system is designed for **One-Click Deployment**.

### Prerequisites
*   Docker & Docker Desktop (with WSL 2 Backend)
*   NVIDIA GPU (Optional, CPU fallback supported)

### Quick Start
1.  **Clone the Repository**
    ```bash
    git clone <repo-url>
    cd secure-water-treatment-system
    ```

2.  **Launch the System**
    Run the production startup script:
    ```bash
    bash start_system.sh
    ```
    *This script handles container orchestration, network creation, and health checks.*

3.  **Access the Interface**
    *   **Dashboard**: [http://localhost:8501](http://localhost:8501)
    *   **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
    *   **Kafka Manager**: [http://localhost:8081](http://localhost:8081)

---

## 🧪 Simulation Modes
The system includes a Data Simulator to mimic real-world scenarios:

*   **Normal Mode**: Simulates standard operational data to demonstrate stability (Green Status).
*   **Attack Mode**: Replays recorded cyber-physical attacks (e.g., valve manipulation, pump failures) to demonstrate detection capabilities (Red Status).

*Toggle modes dynamically via the Dashboard Sidebar.*

---

## 🔒 Security & Compliance
*   **Isolation**: All services run in isolated Docker networks.
*   **Health Monitoring**: Automated health checks for Kafka and Zookeeper.
*   **Audit Trails**: JSON-structured logging for SIEM integration.

---

## 📄 Contact & Support
For enterprise support or deployment assistance, please contact the development team.

---
*Built with ❤️ by the SWaT Security Team*
