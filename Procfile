# Render Deployment - SmartBursar (Webhook API)
# Uses gunicorn with uvicorn workers for ASGI support

web: gunicorn main:app -k uvicorn.workers.UvicornWorker --timeout 120 --bind 0.0.0.0:$PORT
