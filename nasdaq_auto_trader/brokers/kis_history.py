from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo

from .common import JsonObject, _first_float

_US_EXCHANGES: Final = frozenset({"NASD", "NAS", "NYSE", "AMEX"})
_EASTERN: Final = ZoneInfo("America/New_York")


def is_original_order(row: JsonObject) -> bool:
    return (
        str(row.get("rvse_cncl_dvsn") or "").strip() in {"", "00"}
        and not str(row.get("orgn_odno") or "").strip().strip("0")
    )


def history_status(
    row: JsonObject, rows: Sequence[JsonObject], quantity: float, filled: float,
) -> str:
    if not is_original_order(row):
        return "unknown"
    if quantity > 0 and filled == quantity:
        return "filled"
    if str(row.get("prcs_stat_name") or "").strip() == "거부":
        return "rejected"
    if _has_completed_full_cancel(row, rows, quantity - filled):
        return "canceled"
    return "unknown"


def _has_completed_full_cancel(
    original: JsonObject, rows: Sequence[JsonObject], remaining: float,
) -> bool:
    order_id = str(original.get("odno") or "").strip()
    children = [row for row in rows if str(row.get("orgn_odno") or "").strip() == order_id]
    if len(children) != 1 or remaining <= 0:
        return False
    child = children[0]
    child_id = str(child.get("odno") or "").strip()
    if not child_id or child_id == order_id:
        return False
    if any(sum(str(row.get("odno") or "").strip() == identifier for row in rows) != 1
           for identifier in (order_id, child_id)):
        return False
    identity = ("pdno", "sll_buy_dvsn_cd", "ord_dt", "ovrs_excg_cd")
    if any(not original.get(key) or original.get(key) != child.get(key) for key in identity):
        return False
    return (
        str(child.get("rvse_cncl_dvsn") or "").strip() == "02"
        and str(child.get("prcs_stat_name") or "").strip() == "완료"
        and _first_float(child, "ft_ord_qty", "ord_qty", default=-1.0) == remaining
        and _first_float(child, "ft_ccld_qty", "ccld_qty", default=-1.0) == 0
    )


def history_submitted_at(row: JsonObject) -> datetime | None:
    if str(row.get("ovrs_excg_cd") or "").strip() not in _US_EXCHANGES:
        return None
    date = str(row.get("ord_dt") or "").strip()
    time = str(row.get("ord_tmd") or "").strip()
    if len(date) != 8 or len(time) != 6 or not (date + time).isascii() or not (date + time).isdigit():
        return None
    try:
        local = datetime.strptime(date + time, "%Y%m%d%H%M%S").replace(tzinfo=_EASTERN)
    except ValueError:
        return None
    if local.utcoffset() != local.replace(fold=1).utcoffset():
        return None
    utc = local.astimezone(UTC)
    return utc if utc.astimezone(_EASTERN) == local else None
