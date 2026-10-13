from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol, TypeAlias
from urllib.parse import parse_qs, urlsplit

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonMap: TypeAlias = dict[str, JsonValue]
HOST: Final = "openapi.koreainvestment.com"
PORT: Final = 9443
AUTH: Final = "/oauth2/tokenP"
DAILY: Final = "/uapi/overseas-price/v1/quotations/dailyprice"
HISTORY: Final = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
MINUTE: Final = "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
SYMBOLS: Final = {"CMCSA": "NAS", "KDP": "NAS", "HIVE": "NAS", "SPY": "AMS"}


class ResearchError(RuntimeError):
    """Only static sanitized error codes cross this boundary."""


@dataclass(frozen=True, slots=True, repr=False)
class Credentials:
    app_key: str
    app_secret: str
    account: str
    product: str


@dataclass(frozen=True, slots=True, repr=False)
class Query:
    path: str
    tr_id: str
    params: Mapping[str, str]
    continuation: str = ""


@dataclass(frozen=True, slots=True, repr=False)
class WireRequest:
    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True, slots=True)
class WireResponse:
    status: int
    content: bytes = field(repr=False)
    continuation: str = ""


class Wire(Protocol):
    def __call__(self, request: WireRequest) -> WireResponse: ...


def validate_wire(request: WireRequest) -> None:
    parts = urlsplit(request.path)
    if parts.scheme or parts.netloc or parts.fragment:
        raise ResearchError("absolute_url_denied")
    if request.method == "POST" and request.path == AUTH:
        if request.body is None or set(json.loads(request.body)) != {
            "grant_type",
            "appkey",
            "appsecret",
        }:
            raise ResearchError("auth_body_invalid")
        if json.loads(request.body)["grant_type"] != "client_credentials":
            raise ResearchError("auth_body_invalid")
        return
    if request.method != "GET" or request.body is not None:
        raise ResearchError("method_not_allowed")
    params = parse_qs(parts.query, keep_blank_values=True)
    if any(len(values) != 1 for values in params.values()):
        raise ResearchError("duplicate_query_key")
    flat = {key: values[0] for key, values in params.items()}
    credentials = Credentials(
        "", "", flat.get("CANO", ""), flat.get("ACNT_PRDT_CD", "")
    )
    validate_query(
        Query(
            parts.path,
            request.headers.get("tr_id", ""),
            flat,
            request.headers.get("tr_cont", ""),
        ),
        credentials,
    )


def validate_query(query: Query, credentials: Credentials) -> None:
    specs = {
        DAILY: ("HHDFS76240000", {"AUTH", "EXCD", "SYMB", "GUBN", "BYMD", "MODP"}),
        HISTORY: (
            "TTTS3035R",
            {
                "CANO",
                "ACNT_PRDT_CD",
                "PDNO",
                "ORD_STRT_DT",
                "ORD_END_DT",
                "SLL_BUY_DVSN",
                "CCLD_NCCS_DVSN",
                "OVRS_EXCG_CD",
                "SORT_SQN",
                "ORD_DT",
                "ORD_GNO_BRNO",
                "ODNO",
                "CTX_AREA_FK200",
                "CTX_AREA_NK200",
            },
        ),
        MINUTE: (
            "HHDFS76950200",
            {"AUTH", "EXCD", "SYMB", "NMIN", "PINC", "NEXT", "NREC", "FILL", "KEYB"},
        ),
    }
    spec = specs.get(query.path)
    if spec is None or query.tr_id != spec[0] or set(query.params) != spec[1]:
        raise ResearchError("endpoint_not_allowed")
    if query.continuation not in {"", "N"}:
        raise ResearchError("continuation_not_allowed")
    p = query.params
    if query.path == HISTORY:
        exact = {
            "CANO": credentials.account,
            "ACNT_PRDT_CD": credentials.product,
            "PDNO": "%",
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "00",
            "OVRS_EXCG_CD": "NASD",
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
        }
        dates = (p["ORD_STRT_DT"], p["ORD_END_DT"])
        if any(len(p[key]) > 200 for key in ("CTX_AREA_FK200", "CTX_AREA_NK200")):
            raise ResearchError("continuation_size_limit")
    else:
        if p["SYMB"] not in SYMBOLS or p["EXCD"] != SYMBOLS[p["SYMB"]]:
            raise ResearchError("symbol_not_allowed")
        exact = {"AUTH": ""}
        dates = ()
        if query.path == DAILY:
            exact.update({"GUBN": "0", "MODP": "1"})
            dates = (p["BYMD"],)
        else:
            exact.update({"NMIN": "5", "PINC": "1", "NREC": "120", "FILL": ""})
            if p["NEXT"] not in {"", "1"} or (
                p["KEYB"] and not re.fullmatch(r"[0-9]{14}", p["KEYB"])
            ):
                raise ResearchError("minute_cursor_invalid")
    if any(p[key] != value for key, value in exact.items()):
        raise ResearchError("query_value_not_allowed")
    if any(not re.fullmatch(r"[0-9]{8}", value) for value in dates):
        raise ResearchError("date_invalid")


def rows_of(payload: JsonMap, field: str) -> list[JsonMap]:
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise ResearchError("row_shape_invalid")
    parsed: list[JsonMap] = []
    for row in value:
        if not isinstance(row, dict):
            raise ResearchError("row_shape_invalid")
        parsed.append(row)
    return parsed
