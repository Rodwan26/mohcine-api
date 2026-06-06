#!/bin/bash
set -e

echo "[start.sh] Starting Mohcine API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
