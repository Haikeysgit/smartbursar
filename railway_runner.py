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
    """Run both the webhook API and Streamlit dashboard."""
    
    port = int(os.environ.get("PORT", 8000))
    
    # The webhook API runs on the main PORT (Railway routes to this)
    api_process = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", str(port)
    ])
    
    # Streamlit dashboard runs on port 8501 (internal)
    # Note: In production, you'd use a reverse proxy to expose both
    # For now, only the API is publicly accessible, dashboard runs locally
    dashboard_process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run",
        "dashboard/app.py",
        "--server.port", "8501",
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ])
    
    def signal_handler(signum, frame):
        """Handle shutdown gracefully."""
        print("Shutting down services...")
        api_process.terminate()
        dashboard_process.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"✅ Webhook API running on port {port}")
    print(f"✅ Dashboard running on port 8501")
    
    # Wait for either process to exit
    while True:
        if api_process.poll() is not None:
            print("API process exited, restarting...")
            api_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn",
                "main:app",
                "--host", "0.0.0.0",
                "--port", str(port)
            ])
        
        if dashboard_process.poll() is not None:
            print("Dashboard process exited, restarting...")
            dashboard_process = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run",
                "dashboard/app.py",
                "--server.port", "8501",
                "--server.address", "0.0.0.0",
                "--server.headless", "true"
            ])
        
        time.sleep(5)


if __name__ == "__main__":
    run_services()
