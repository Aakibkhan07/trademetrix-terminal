from typing import Any

from fastapi.responses import JSONResponse


def api_response(data: Any = None, message: str = "Success", status: int = 200, meta: dict | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "success": True,
        "message": message,
        "data": data,
    }
    if meta:
        body["meta"] = meta
    return JSONResponse(content=body, status_code=status)


def error_response(message: str, code: str = "INTERNAL_ERROR", status: int = 500, details: dict | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(content=body, status_code=status)
