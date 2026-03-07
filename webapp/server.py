"""
Minimal WebApp server — serves the wallet_connect.html mini-app over HTTPS.

Usage:
    pip install fastapi uvicorn[standard]
    uvicorn webapp.server:app --host 0.0.0.0 --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem

For local dev/testing with a tunnel (e.g. ngrok):
    uvicorn webapp.server:app --host 0.0.0.0 --port 8080
    ngrok http 8080
    # Set WEBAPP_URL=https://<ngrok-id>.ngrok.io/wallet in .env

Telegram WebApps REQUIRE HTTPS. Use a reverse proxy (nginx, Caddy) or
a managed platform (Railway, Render, Fly.io) in production.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

app = FastAPI(docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.telegram.org", "https://telegram.org"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_HERE = Path(__file__).parent


@app.get("/wallet")
async def wallet_connect():
    """Serve the wallet connect mini-app."""
    html_path = _HERE / "wallet_connect.html"
    return FileResponse(html_path, media_type="text/html")


@app.get("/health")
async def health():
    return {"status": "ok"}
