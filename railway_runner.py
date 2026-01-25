"""
Combined Railway Runner - Runs both WhatsApp webhook API and Streamlit dashboard.
For Railway deployment where we need both services in one process.
"""
import subprocess
import os
import sys
import time
import signal

def run_services():
    """
    Run services based on environment and configuration.
    
    Modes:
    1. Local Development (default if no specific env vars): Runs BOTH API and Dashboard.
    2. Production API: Runs users `SERVICE_TYPE=api` (or default).
    3. Production Dashboard: Runs when `SERVICE_TYPE=dashboard`.
    """
    port = int(os.environ.get("PORT", 8000))
    service_type = os.environ.get("SERVICE_TYPE", "api").lower()
    environment = os.environ.get("ENVIRONMENT", "development")
    
    # ---------------------------------------------------------
    # MODE 1: PRODUCTION DASHBOARD
    # ---------------------------------------------------------
    if service_type == "dashboard":
        print(f"🚀 Starting DASHBOARD on port {port}")
        # Validates that we are in a production-like env or explicitly asked for dashboard
        cmd = [
            sys.executable, "-m", "streamlit", "run",
            "dashboard/app.py",
            "--server.port", str(port),
            "--server.address", "0.0.0.0",
            "--server.headless", "true"
        ]
        return subprocess.run(cmd).returncode

    # ---------------------------------------------------------
    # MODE 2: PRODUCTION API (Default)
    # ---------------------------------------------------------
    # If we are in production (Railway) and NOT dashboard, we run just the API
    # We detect production by "RAILWAY_PUBLIC_DOMAIN" or similar, or just assumption if not local
    is_railway = "RAILWAY_PUBLIC_DOMAIN" in os.environ or "RAILWAY_STATIC_URL" in os.environ
    
    if is_railway and service_type != "local":
        print(f"🚀 Starting API on port {port}")
        cmd = [
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "0.0.0.0",
            "--port", str(port)
        ]
        return subprocess.run(cmd).returncode

    # ---------------------------------------------------------
    # MODE 3: LOCAL DEVELOPMENT (Run BOTH)
    # ---------------------------------------------------------
    print("🛠️  Starting LOCAL DEVELOPMENT (API + Dashboard)")
    
    # API on Port 8000
    api_process = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", "8000"
    ])
    
    # Dashboard on Port 8501
    dashboard_process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run",
        "dashboard/app.py",
        "--server.port", "8501",
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ])
    
    def signal_handler(signum, frame):
        print("Shutting down services...")
        api_process.terminate()
        dashboard_process.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"✅ Webhook API running on http://localhost:8000")
    print(f"✅ Dashboard running on http://localhost:8501")
    
    # Keep alive
    api_process.wait()
    dashboard_process.wait()

if __name__ == "__main__":
    run_services()


if __name__ == "__main__":
    run_services()
