from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, TypeAlias, TypedDict

Json: TypeAlias = str | int | float | bool | None | list["Json"] | dict[str, "Json"]
LiveReview: TypeAlias = Mapping[str, Json]
CONFIRMATION: Final = "실전 위험과 미검증 상태를 확인했습니다"
MODE_TEXT: Final = {
    "local_paper": "LOCAL · 로컬 시뮬레이션 / 실제 주문 없음",
    "kis_paper": "KIS 모의 · 가상 서버 주문 / 접수·체결 확인 필요",
    "live": "LIVE BLOCKED · 실전 차단 / 요청 저장은 승인이 아닙니다",
}


class Position(TypedDict):
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    high_water_price: float | None


class OpsStatus(TypedDict, total=False):
    mode: str
    running: bool
    entries_paused: bool
    message: str
    account_message: str
    no_buy_reasons: list[str]
    updated_at: str
    cash: float
    equity: float
    positions: list[Position]
    pending: list[Json] | int
    version: str
    blockers: list[str]
    details: dict[str, Json]


@dataclass(frozen=True, slots=True)
class WorkerResult:
    status: OpsStatus | None = None
    review: LiveReview | None = None
    error: str = ""


class OpsController(Protocol):
    def start(self, mode: str) -> None: ...
    def pause_entries(self) -> None: ...
    def resume_entries(self) -> None: ...
    def step(self) -> None: ...
    def status(self) -> OpsStatus: ...
    def close(self) -> None: ...
    def live_review(self) -> LiveReview: ...
    def record_live_request(
        self, account: str, allocation_usd: float, loss_stop_pct: float, confirm: str,
    ) -> None: ...
