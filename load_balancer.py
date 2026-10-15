"""
EventEase Load Balancer and Reverse Proxy
=========================================
Features:
- Dual-mode: serves HTTP on port 8080 and HTTPS (TLS) on port 8443
- Round-robin load balancing across backend instances (app1: 8001, app2: 8002)
- Automatic health check and failover between backends
- Sliding-window rate limiting per client IP (20 req/s, burst 40)
- Injects standard proxy headers (X-Real-IP, X-Forwarded-For, X-Forwarded-Proto, X-Load-Balancer)
- Preserves backend headers (X-Served-By, Strict-Transport-Security, CSP, etc.)
"""

import argparse
import asyncio
import os
import ssl
import sys
import time
from collections import defaultdict, deque
from typing import List

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

BACKENDS = os.getenv("BACKENDS", "http://127.0.0.1:8001,http://127.0.0.1:8002").split(",")
LB_RATE_LIMIT = float(os.getenv("LB_RATE_LIMIT", "20.0"))  # req/s
LB_BURST = int(os.getenv("LB_BURST", "40"))
HTTPS_PORT = int(os.getenv("HTTPS_PORT", "8443"))
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
FORCE_HTTPS = os.getenv("FORCE_HTTPS", "0") == "1"

_current_index = 0
_lock = asyncio.Lock()
_request_history = defaultdict(deque)  # client_ip -> deque of monotonic timestamps
_client = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )
    return _client

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def check_rate_limit(client_ip: str) -> bool:
    """Sliding-window rate limiter per client IP."""
    now = time.monotonic()
    history = _request_history[client_ip]

    cutoff = now - (LB_BURST / LB_RATE_LIMIT)
    while history and history[0] < cutoff:
        history.popleft()

    if len(history) >= LB_BURST:
        return False

    history.append(now)
    return True


async def get_next_backend() -> str:
    """Round-robin backend selector."""
    global _current_index
    async with _lock:
        backend = BACKENDS[_current_index % len(BACKENDS)]
        _current_index = (_current_index + 1) % len(BACKENDS)
        return backend


app = Starlette()


@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    # Healthz is exempt from rate limiting
    if request.url.path == "/healthz":
        return await call_next(request)

    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "1"},
            content={"detail": "Too many requests at load balancer. Rate limit: 20 req/s. Please slow down."},
        )

    return await call_next(request)


@app.route("/healthz")
async def healthz(request: Request):
    """Exempt health check."""
    return JSONResponse({"status": "ok", "load_balancer": "EventEase-LB"})


@app.route("/lb-status")
async def lb_status(request: Request):
    """Load balancer status endpoint."""
    return JSONResponse({
        "status": "operational",
        "load_balancer": "EventEase-ReverseProxy/1.0",
        "backends": BACKENDS,
        "algorithm": "round-robin",
        "rate_limiting": {
            "rate": f"{LB_RATE_LIMIT} req/s",
            "burst": LB_BURST,
            "status": "active"
        },
        "scheme": request.url.scheme,
        "port": request.url.port,
        "https_available_at": f"https://localhost:{HTTPS_PORT}",
        "http_available_at": f"http://localhost:{HTTP_PORT}",
    })


@app.route("/redirect-to-https")
async def explicit_redirect(request: Request):
    """Demonstrates 301 HTTP -> HTTPS redirect."""
    host = request.headers.get("host", "localhost").split(":")[0]
    target = f"https://{host}:{HTTPS_PORT}/"
    return RedirectResponse(url=target, status_code=301)


@app.route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_handler(request: Request):
    # Optional global HTTP->HTTPS redirection if FORCE_HTTPS is set
    if FORCE_HTTPS and request.url.scheme == "http":
        host = request.headers.get("host", "localhost").split(":")[0]
        target = f"https://{host}:{HTTPS_PORT}{request.url.path}"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(url=target, status_code=301)

    client_ip = request.client.host if request.client else "127.0.0.1"

    # Select backend with automatic failover
    req_body = await request.body()
    retries = len(BACKENDS)

    for attempt in range(retries):
        backend = await get_next_backend()
        target_url = f"{backend}{request.url.path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        # Forwarded headers
        headers = dict(request.headers)
        headers["x-forwarded-proto"] = request.url.scheme
        headers["x-real-ip"] = client_ip
        existing_xff = headers.get("x-forwarded-for")
        headers["x-forwarded-for"] = f"{existing_xff}, {client_ip}" if existing_xff else client_ip
        headers["x-load-balancer"] = "EventEase-LB"

        for h in HOP_BY_HOP:
            headers.pop(h, None)
        headers.pop("host", None)
        headers.pop("content-length", None)

        try:
            client = get_client()
            upstream_resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=req_body,
            )

            resp_headers = {}
            for k, v in upstream_resp.headers.items():
                if k.lower() not in HOP_BY_HOP and k.lower() not in ["content-length", "content-encoding"]:
                    resp_headers[k] = v

            return Response(
                content=upstream_resp.content,
                status_code=upstream_resp.status_code,
                headers=resp_headers,
                media_type=upstream_resp.headers.get("content-type"),
            )

        except (httpx.ConnectError, httpx.ConnectTimeout):
            continue
        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"detail": f"Bad Gateway: upstream communication error ({str(e)})"},
            )

    return JSONResponse(
        status_code=503,
        content={"detail": "All upstream backend instances are currently unavailable."},
    )


async def main():
    parser = argparse.ArgumentParser(description="EventEase Load Balancer")
    parser.add_argument("--http-port", type=int, default=HTTP_PORT)
    parser.add_argument("--https-port", type=int, default=HTTPS_PORT)
    parser.add_argument("--cert", type=str, default="certs/cert.pem")
    parser.add_argument("--key", type=str, default="certs/key.pem")
    args = parser.parse_args()

    configs = []

    # HTTP Server
    http_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=args.http_port,
        log_level="warning",
    )
    configs.append(uvicorn.Server(http_config).serve())

    # HTTPS Server (if cert exists)
    if os.path.exists(args.cert) and os.path.exists(args.key):
        https_config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=args.https_port,
            ssl_certfile=args.cert,
            ssl_keyfile=args.key,
            log_level="warning",
        )
        configs.append(uvicorn.Server(https_config).serve())
        print(f"[LB] HTTPS listening on https://localhost:{args.https_port} (TLS enabled)")
    else:
        print(f"[LB] WARNING: SSL cert/key not found at {args.cert}, skipping HTTPS.")

    print(f"[LB] HTTP listening on http://localhost:{args.http_port}")
    print(f"[LB] Upstream backends: {', '.join(BACKENDS)}")
    await asyncio.gather(*configs)


if __name__ == "__main__":
    asyncio.run(main())
