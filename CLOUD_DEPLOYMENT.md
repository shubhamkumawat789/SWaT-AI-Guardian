# ☁️ Cloud Deployment Guide - SWaT AI Guardian

This guide explains how to deploy the SWaT System to a cloud provider (AWS, Google Cloud, or Azure) so it runs permanently and is accessible to anyone, anywhere.

## ✅ Prerequisites
*   A Cloud Account (AWS, GCP, or Azure).
*   **Cost Warning**: This system requires **8GB+ RAM** and ideally a **GPU**.
    *   **AWS**: `t2.large` (minimum) or `g4dn.xlarge` (recommended for GPU).
    *   **Azure**: `Standard_B2ms` (minimum) or `Standard_NC4as_T4_v3` (GPU).

---

## 🚀 Deployment Steps (AWS Example)

### 1. Launch Instance
1.  Go to **EC2 Dashboard** -> **Launch Instance**.
2.  **Name**: `SWaT-Server`.
3.  **OS**: Ubuntu Server 22.04 LTS.
4.  **Instance Type**: `t2.large` (2 vCPU, 8GB RAM). *Do not use t2.micro, it will crash.*
5.  **Key Pair**: Create or select an existing key pair.
6.  **Network Settings**: Allow HTTP (80), HTTPS (443), and Custom TCP (8501) for the Dashboard.

### 2. Connect & Install Docker
SSH into your new server:
```bash
ssh -i "your-key.pem" ubuntu@<your-server-ip>
```

Run these commands to install Docker and Git:
```bash
# Update System
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Check it works
docker --version
```

### 3. Deploy the Code
Clone your repository (or upload your files).
```bash
# Example: Clone from GitHub (if you pushed it there)
git clone https://github.com/your-username/swat-guardian.git
cd swat-guardian

# OR: Upload files using SCP from your local machine
# scp -i key.pem -r "C:\Users\Shubham\Documents\Secure Water Treatment System" ubuntu@<ip>:~/swat-system
```

### 4. Start the System
```bash
# Build and Start
docker compose up --build -d
```

### 5. Access the Dashboard
The system is now live!
*   **URL**: `http://<your-server-ip>:8501`
*   Share this IP with the recruiter.

---

## 🔒 Security Note
*   The above setup opens port 8501 to the public. For production, consider using Nginx as a reverse proxy with password protection.
