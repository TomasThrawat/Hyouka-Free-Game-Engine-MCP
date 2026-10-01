#!/usr/bin/env python3
from __future__ import annotations

import os

import aiohttp
import jwt
from aiohttp import web

TEAM = os.environ.get("VERCEL_OIDC_TEAM_SLUG", "hyouka1")
PROJECT = os.environ.get("VERCEL_OIDC_PROJECT", "hyouka-free-game-engine-mcp")
ENVIRONMENT = os.environ.get("VERCEL_OIDC_ENVIRONMENT", "production")
ISSUER = f"https://oidc.vercel.com/{TEAM}"
AUDIENCE = f"https://vercel.com/{TEAM}"
SUBJECT = f"owner:{TEAM}:project:{PROJECT}:environment:{ENVIRONMENT}"
UPSTREAM = os.environ.get("UPSTREAM_URL", "http://127.0.0.1:9766").rstrip("/")
PORT = int(os.environ.get("PORT", "10002"))
JWKS = jwt.PyJWKClient(f"{ISSUER}/.well-known/jwks")

def validate(token: str) -> None:
    key = JWKS.get_signing_key_from_jwt(token).key
    jwt.decode(
        token,
        key=key,
        algorithms=["RS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
        subject=SUBJECT,
        options={"require": ["iss", "sub", "aud", "exp", "iat"]},
    )

async def mcp(request: web.Request) -> web.StreamResponse:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return web.Response(
            status=401,
            text="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        validate(authorization[7:].strip())
    except Exception:
        return web.Response(
            status=401,
            text="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    body = await request.read()
    headers = {
        k:v for k,v in request.headers.items()
        if k.lower() not in {"authorization","host","content-length","connection"}
    }

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=None, sock_read=None)
    ) as session:
        async with session.request(
            request.method,
            UPSTREAM + request.path_qs,
            headers=headers,
            data=body,
            allow_redirects=False,
        ) as upstream:
            response = web.StreamResponse(
                status=upstream.status,
                headers={
                    k:v for k,v in upstream.headers.items()
                    if k.lower() not in {"content-length","transfer-encoding","connection"}
                },
            )
            await response.prepare(request)
            async for chunk in upstream.content.iter_chunked(65536):
                await response.write(chunk)
            await response.write_eof()
            return response

async def health(_: web.Request) -> web.Response:
    return web.Response(
        status=401,
        text="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )

app = web.Application()
app.router.add_route("*", "/mcp", mcp)
app.router.add_get("/health", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=PORT)
