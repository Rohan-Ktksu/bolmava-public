from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def _body(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": jsonable_encoder(details)}},
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def app_error(_: Request, e: AppError):
        return _body(e.status, e.code, e.message, e.details)

    @app.exception_handler(RequestValidationError)
    def validation_error(_: Request, e: RequestValidationError):
        details = [{"loc": err["loc"], "msg": err["msg"]} for err in e.errors()]
        return _body(400, "validation_error", "Some fields are missing or invalid.", details)

    @app.exception_handler(HTTPException)
    def http_error(_: Request, e: HTTPException):
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(e.status_code, "error")
        return _body(e.status_code, code, str(e.detail))

    @app.exception_handler(IntegrityError)
    def integrity_error(_: Request, e: IntegrityError):
        if getattr(e.orig, "sqlstate", None) == "23505":
            return _body(409, "conflict", "A record with this value already exists.")
        raise e
