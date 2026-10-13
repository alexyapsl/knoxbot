"""Tiny internal relay for the Knox AI Builder POC.

AI Builder (internal-only egress) -> this relay (internal host) -> public shop API.

Run:
    py relay.py            # listens on 0.0.0.0:8080 by default
    set RELAY_PORT=80 && py relay.py

Endpoint:
    GET /stock?productCodes=SM-S938BZAKTGY
    -> proxies to https://shop.samsung.com/hk/servicesv2/getSimpleProductsInfo

Corporate proxy: httpx honours HTTP_PROXY / HTTPS_PROXY env vars.
"""

import os

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

UPSTREAM = "https://shop.samsung.com/hk/servicesv2/getSimpleProductsInfo"
PORT = int(os.environ.get("RELAY_PORT", "8080"))

app = FastAPI()
client = httpx.AsyncClient(timeout=15.0, follow_redirects=True, trust_env=True)


@app.get("/stock")
async def stock(request: Request):
    params = dict(request.query_params)
    if not params.get("productCodes"):
        return JSONResponse({"error": "productCodes query param required"}, status_code=400)
    try:
        resp = await client.get(UPSTREAM, params=params)
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"upstream call failed: {e}"}, status_code=502)
    return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
