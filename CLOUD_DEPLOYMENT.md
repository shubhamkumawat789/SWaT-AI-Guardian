
# 🚀 Going Live: Deployment Guide for SWaT AI Guardian

Since you want to share this "live" with recruiters and clients, the best professional approach is using **GitHub + Streamlit Cloud**. This provides a permanent, always-on link without needing your laptop to be running.

We have prepared your code for this deployment:
1.  **Simulation Mode:** The dashboard automatically switches to "Simulation Mode" if Kafka isn't found (which handles the cloud environment limitation).
2.  **Sample Data:** We created a `data/normal_sample.csv` (50k rows) so the app works on the cloud without hitting file size limits.
3.  **Git Configuration:** A `.gitignore` file is set up to exclude the huge original data files.

---

## Step 1: Push to GitHub

You need to push this code to a new GitHub repository.

1.  **Create a New Repository** on [GitHub.com](https://github.com/new).
    *   Name it `swat-ai-guardian`.
    *   Make it **Public** (easier for recruiters to see).
    *   **Do not** initialize with README/gitignore (we already did locally).

2.  **Push your code** (Run these commands in your VS Code terminal):
    ```bash
    # Replace URL with your actual new repo URL
    git remote add origin https://github.com/YOUR_USERNAME/swat-ai-guardian.git
    git branch -M main
    git push -u origin main
    ```

---

## Step 2: Deploy on Streamlit Cloud

1.  Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub.
2.  Click **"New app"**.
3.  Select your repository (`swat-ai-guardian`).
4.  **Main file path:** Enter `src/dashboard/app_kafka_live.py`.
5.  Click **"Deploy!"**.

It typically takes 2-3 minutes to build. Once done, you will get a permanent URL (e.g., `https://swat-ai-guardian.streamlit.app`) to share.

---

## Why this works for Recruiters
*   **Zero Setup:** They just click the link. No Docker/WSL needed.
*   **Automatic Fallback:** The app detects "No Kafka" and uses the CSV data we prepared to simulate the live stream.
*   **Visuals:** They see the same "Live" dashboard effectively.

**Note:** The sophisticated backend (Kafka -> Spark -> GPU Inference) runs on your local machine for deep technical demos, but this Cloud version is perfect for the "front-end experience" shareable link.
