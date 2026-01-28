import os
import typing
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

FONT_MIME_TYPES = {
    "woff": "application/font-woff",
    "woff2": "font/woff2",
    "ttf": "application/x-font-ttf",
    "otf": "application/x-font-opentype",
    "eot": "application/vnd.ms-fontobject",
    "svg": "image/svg+xml"
}


class CustomStaticFiles(StaticFiles):

    def lookup_path(self, path: str) -> tuple[str, typing.Optional[os.stat_result]]:
        return super().lookup_path(path)

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)

        ext = path.split(".")[-1].lower()

        if ext in FONT_MIME_TYPES:
            response.headers["Content-Type"] = FONT_MIME_TYPES[ext]

            response.headers["Access-Control-Allow-Origin"] = "*"

            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

        return response