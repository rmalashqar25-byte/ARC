"""Bound requests before JSON parsing; keep limits independent of session IDs."""

import asyncio
import json
import time
from collections import Counter, OrderedDict, deque
from threading import Lock

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 1_000_000


class SecurityBoundaryMiddleware:
    def __init__(self, app):
        self.app = app
        self._lock = Lock()
        self._requests = OrderedDict()
        self._active = Counter()

    def _admit(self, peer, kind):
        now = time.monotonic()
        with self._lock:
            for key in list(self._requests):
                entries = self._requests[key]
                while entries and entries[0] <= now - 60:
                    entries.popleft()
                if not entries:
                    del self._requests[key]
            # Global ceilings prevent rotating IPs/session tokens from bypassing limits.
            keys = [(peer, "http", 600), ("*", "http", 2400)]
            if kind == "work":
                keys.extend([(peer, "work", 30), ("*", "work", 60)])
            if len(self._requests) >= 5000 and (peer, "http") not in self._requests:
                return False
            if any(
                len(self._requests.get((owner, bucket), ())) >= limit
                for owner, bucket, limit in keys
            ):
                return False
            cap = 4 if kind == "work" else 64 if kind == "stream" else 128
            if self._active[("*", kind)] >= cap or self._active[(peer, kind)] >= (
                4 if kind != "http" else 32
            ):
                return False
            for owner, bucket, _ in keys:
                self._requests.setdefault((owner, bucket), deque()).append(now)
            self._active[("*", kind)] += 1
            self._active[(peer, kind)] += 1
            return True

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or scope["path"] == "/health/live"
        ):
            return await self.app(scope, receive, send)
        peer = (scope.get("client") or ("unknown", 0))[0]
        path = scope["path"]
        kind = (
            "stream"
            if path.endswith("/stream")
            else "work"
            if (
                path.endswith("/run")
                or "/approvals/" in path
                or "/approval-requests/" in path
            )
            and scope["method"] == "POST"
            else "http"
        )
        if not self._admit(peer, kind):
            return await JSONResponse(
                {"detail": "Request capacity reached; retry later"},
                429,
                headers={"Retry-After": "60", "Cache-Control": "no-store"},
            )(scope, receive, send)
        try:
            headers = dict(scope["headers"])
            content_length = headers.get(b"content-length")
            if content_length is not None:
                try:
                    length = int(content_length)
                    if length < 0:
                        raise ValueError()
                except ValueError:
                    return await JSONResponse(
                        {"detail": "Invalid Content-Length"}, 400
                    )(scope, receive, send)
                if length > MAX_REQUEST_BYTES:
                    return await JSONResponse(
                        {"detail": "Request body exceeds 1 MB"}, 413
                    )(scope, receive, send)
            # Bound chunked requests too. Only retain one capped buffer, never an
            # unbounded list of chunks. Limit slow uploads independently of model calls.
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                            return await JSONResponse(
                                {"detail": "Request body exceeds 1 MB"}, 413
                            )(scope, receive, send)
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await JSONResponse({"detail": "Request upload timed out"}, 408)(
                    scope, receive, send
                )
            if (
                body
                and b"application/json" in headers.get(b"content-type", b"").lower()
            ):
                try:
                    json.loads(body)
                except (ValueError, RecursionError, UnicodeError):
                    return await JSONResponse({"detail": "Invalid JSON body"}, 400)(
                        scope, receive, send
                    )
            delivered = False

            async def capped_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return await receive()

            await self.app(scope, capped_receive, send)
        finally:
            with self._lock:
                for key in (("*", kind), (peer, kind)):
                    self._active[key] -= 1
                    if not self._active[key]:
                        del self._active[key]
