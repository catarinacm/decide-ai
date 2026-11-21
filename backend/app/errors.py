"""Formato único de erro: {"error": {"code": "...", "message": "...", "details": ...}}."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("ifood_match")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: object | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str) -> AppError:
    return AppError(404, "nao_encontrado", f"{what} não encontrado.")


def forbidden(message: str = "Você não tem permissão para esta ação.") -> AppError:
    return AppError(403, "sem_permissao", message)


def conflict(code: str, message: str, details: object | None = None) -> AppError:
    return AppError(409, code, message, details)


def _body(code: str, message: str, details: object | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
                   for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body("dados_invalidos", "Alguns campos estão inválidos.", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "nao_encontrado", 405: "metodo_nao_permitido", 401: "nao_autenticado"}.get(exc.status_code, "erro")
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("Erro inesperado: %s", exc)
        return JSONResponse(status_code=500, content=_body("erro_interno", "Algo deu errado do nosso lado. Tente de novo."))
