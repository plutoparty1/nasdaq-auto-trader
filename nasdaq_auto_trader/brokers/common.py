from __future__ import annotations

from http.client import HTTPMessage, HTTPResponse
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

JsonObject = dict[str, Any]


class BrokerCredentialError(ValueError):
    pass


class BrokerOrderError(ValueError):
    pass


class BrokerRequestError(RuntimeError):
    pass


class BrokerOrderRejected(BrokerRequestError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"broker_order_rejected:{code}")


class _RejectBrokerRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: HTTPResponse,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> None:
        return None


def broker_urlopen(request: Request, *, timeout: float) -> HTTPResponse:
    return build_opener(_RejectBrokerRedirects()).open(request, timeout=timeout)


def _first_float(payload: JsonObject, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return default


def _first_output_dict(payload: JsonObject, key: str) -> JsonObject:
    output = payload.get(key) or {}
    if isinstance(output, list):
        return output[0] if output and isinstance(output[0], dict) else {}
    return output if isinstance(output, dict) else {}


def _compact_date(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("-", "")[:8]


def _format_price(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"
