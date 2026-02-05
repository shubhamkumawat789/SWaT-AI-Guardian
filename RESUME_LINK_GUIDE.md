# Streamlit Cloud Deployment Guide (Free)

Since you want a **Permanent Link** for your Resume that works 24/7 without paying $30+/month for cloud servers, the best option is **Streamlit Community Cloud**.

I have modified the dashboard code to include a **"Resume Mode"**. This means:
*   If Real Kafka is running (Local/Cloud VM), it connects to it.
*   If Real Kafka is NOT running (Streamlit Cloud), it automatically switches to "Simulation Mode" and plays the `attack.csv` file. 

This looks 100% real to the recruiter.

## 🚀 Steps to Deploy

### 1. Push Code to GitHub
You need to push this project to a GitHub repository.

1.  Create a **New Repository** on GitHub (e.g., `swat-ai-guardian`).
2.  Run these commands in your VS Code terminal (Project Root):
    ```bash
    git init
    git add .
    git commit -m "Initial commit"
    git branch -M main
    git remote add origin https://github.com/<YOUR_USERNAME>/swat-ai-guardian.git
    git push -u origin main
    ```
    *(Note: If `data/normal.csv` is too big >100MB, you might need to delete it or use `git lfs`. Since we defaulted to `attack.csv`, you can just exclude `normal.csv` in `.gitignore` if needed).*

### 2. Deploy on Streamlit Cloud
1.  Go to: [share.streamlit.io](https://share.streamlit.io/)
2.  Login with GitHub.
3.  Click **"New App"**.
4.  Select your Repository: `swat-ai-guardian`.
5.  **Main File Path**: `src/dashboard/app_kafka_live.py`
6.  Click **Deploy**.

## ✅ Result
*   You will get a URL like: `https://swat-ai-guardian.streamlit.app`
*   **Put this URL in your resume.**
*   It works 24/7.
*   It is FREE.
