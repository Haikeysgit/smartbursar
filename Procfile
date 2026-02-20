# Render Deployment - SmartBursar (Webhook API)
# Uses gunicorn with uvicorn workers for ASGI support

web: gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 1 --preload --bind 0.0.0.0:$PORT
