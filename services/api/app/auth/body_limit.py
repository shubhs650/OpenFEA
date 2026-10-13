"""Bound metadata bytes before JSON parsing, including a falsely declared length."""

import re

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.domain.models import ErrorResponse


class MetadataBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PATCH", "PUT"):
            await self.app(scope, receive, send)
            return
        request = Request(scope)

        async def reject(status: int, code: str, message: str) -> None:
            payload = ErrorResponse(
                code=code, message=message, request_id=scope["state"]["request_id"]
            )
            await JSONResponse(payload.model_dump(mode="json"), status_code=status)(
                scope, receive, send
            )

        length = request.headers.get("content-length")
        if length is None:
            await reject(411, "length_required", "A request size is required")
            return
        if scope["method"] == "PUT" and re.fullmatch(
            r"/api/v1/geometry-uploads/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/content",
            scope["path"],
        ):
            if (
                not length.isascii()
                or not length.isdecimal()
                or len(length) > 10
                or int(length) > 16777216
            ):
                await reject(413, "upload_size", "STEP uploads are limited to 16 MiB")
                return
            await self.app(scope, receive, send)
            return
        if (
            not length.isascii()
            or not length.isdecimal()
            or len(length) > 10
            or int(length) > 65536
        ):
            await reject(413, "request_too_large", "Metadata requests are limited to 64 KiB")
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 65536:
                await reject(413, "request_too_large", "Metadata requests are limited to 64 KiB")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
