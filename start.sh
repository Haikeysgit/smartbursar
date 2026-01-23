#!/bin/bash
# Start both services

# Start the webhook API in the background
uvicorn services.whatsapp_agent.webhook_handler:app --host 0.0.0.0 --port ${PORT:-8000} &

# Start the Streamlit dashboard on port 8501 (Railway will route to it)
streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
