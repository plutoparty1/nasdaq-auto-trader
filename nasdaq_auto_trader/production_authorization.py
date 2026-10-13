from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, final

from .ai_quant_lab.types import JsonObject, JsonValue
from .config import AppConfig
from .config_settings import TradingSettings
from .live_authorization import broker_authorization_digest
from .live_authorization_store import (
    LiveAuthorizationStore,
    LiveAuthorizationStoreError,
)
from .live_session_authorization import (
    SessionAuthorizationRequest,
    authorize_live_session,
)
from .market_hours import EASTERN, regular_market_session
from .models import OrderRequest


@dataclass(frozen=True, slots=True)
class ProductionBinding:
    executable_sha256: str
    account_digest: str
    config_digest: str
    settings_digest: str
    artifacts_digest: str

    @classmethod
    def capture(
        cls, executable: Path, config: AppConfig, settings: TradingSettings | None,
        *, artifacts: tuple[Path, ...] = (),
    ) -> ProductionBinding:
        with executable.open("rb") as source:
            executable_digest = hashlib.file_digest(source, "sha256").hexdigest()
        return cls(
            executable_digest,
            broker_authorization_digest(config),
            hashlib.sha256(json.dumps(
                asdict(config), sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                asdict(settings) if settings is not None else None,
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode()).hexdigest(),
            hashlib.sha256(b"".join(
                path.resolve().as_posix().encode() + b"\0"
                + (path.read_bytes() if path.exists() else b"MISSING") + b"\0"
                for path in artifacts
            )).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class ProductionReceipt:
    binding: ProductionBinding
    authorization_id: str
    market_date: str


class ProductionApprovalError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(reason)


def write_production_receipt(path: Path, receipt: ProductionReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {**asdict(receipt.binding),
               "authorization_id": receipt.authorization_id,
               "market_date": receipt.market_date}
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(payload, output, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


_RECEIPT_KEYS: Final = (
    "executable_sha256", "account_digest", "config_digest", "settings_digest",
    "artifacts_digest", "authorization_id", "market_date",
)


def _read_receipt(path: Path) -> ProductionReceipt:
    try:
        payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProductionApprovalError("production_approval_required") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionApprovalError("production_approval_corrupt") from exc
    if not isinstance(payload, dict) or set(payload) != set(_RECEIPT_KEYS):
        raise ProductionApprovalError("production_approval_corrupt")
    values: list[str] = []
    for key in _RECEIPT_KEYS:
        value = payload[key]
        if not isinstance(value, str) or not value:
            raise ProductionApprovalError("production_approval_corrupt")
        values.append(value)
    return ProductionReceipt(ProductionBinding(*values[:5]), values[5], values[6])


@final
class ProductionOrderGate:
    def __init__(
        self, executable: Path, receipt_path: Path,
        authorization_store: LiveAuthorizationStore,
        *, current_binding: Callable[[], ProductionBinding] | None = None,
        artifacts: tuple[Path, ...] = (),
        order_checker: Callable[[OrderRequest], str] | None = None,
    ) -> None:
        self.executable = executable
        self.receipt_path = receipt_path
        self.authorization_store = authorization_store
        self.current_binding = current_binding
        self.artifacts = artifacts
        self.order_checker = order_checker
        self.submission_enabled = False
        self.entries_enabled = True

    def set_submission_enabled(self, enabled: bool) -> None:
        self.submission_enabled = enabled

    def set_entries_enabled(self, enabled: bool) -> None:
        self.entries_enabled = enabled

    def operating_reason(self, side: str) -> str:
        if not self.submission_enabled:
            return "production_start_required"
        if side == "buy" and not self.entries_enabled:
            return "production_entries_paused"
        return ""

    def order_reason(self, order: OrderRequest) -> str:
        reason = self.operating_reason(order.side)
        if reason or self.order_checker is None:
            return reason
        return self.order_checker(order)

    def reason(
        self, config: AppConfig, settings: TradingSettings | None, now: datetime,
    ) -> str:
        if now.tzinfo is None or now.utcoffset() is None:
            return "market_time_timezone_required"
        try:
            receipt = _read_receipt(self.receipt_path)
            current = ProductionBinding.capture(
                self.executable, config, settings, artifacts=self.artifacts,
            )
            file_binding = self.current_binding() if self.current_binding is not None else current
            stored = self.authorization_store.load()
        except ProductionApprovalError as exc:
            return exc.reason
        except LiveAuthorizationStoreError as exc:
            return exc.reason
        except (OSError, ValueError, RuntimeError):
            return "production_binding_read_failed"
        checks = (
            (receipt.binding.executable_sha256 == current.executable_sha256,
             "production_build_mismatch"),
            (receipt.binding.account_digest == current.account_digest,
             "production_account_mismatch"),
            (receipt.binding.config_digest == current.config_digest,
             "production_config_mismatch"),
            (receipt.binding.settings_digest == current.settings_digest,
             "production_settings_mismatch"),
            (receipt.binding.artifacts_digest == current.artifacts_digest,
             "production_strategy_artifacts_mismatch"),
            (receipt.market_date == now.astimezone(EASTERN).date().isoformat(),
             "production_approval_expired"),
        )
        for matches, reason in checks:
            if not matches:
                return reason
        if file_binding != receipt.binding:
            return "production_config_source_changed"
        if stored is None:
            return "production_authorization_required"
        if (stored.envelope.authorization_id != receipt.authorization_id
            or stored.envelope.market_date.isoformat() != receipt.market_date
            or stored.envelope.broker_authorization_digest != current.account_digest):
            return "production_authorization_mismatch"
        if not regular_market_session(now).is_open:
            return "outside_regular_session"
        return ""


@dataclass(frozen=True, slots=True)
class ProductionApprovalRequest:
    session: SessionAuthorizationRequest
    executable: Path
    receipt_path: Path
    settings: TradingSettings | None = None
    artifacts: tuple[Path, ...] = ()


def authorize_production_session(request: ProductionApprovalRequest) -> JsonObject:
    """Issue a build-bound receipt only after the existing approval procedure succeeds."""
    try:
        binding = ProductionBinding.capture(
            request.executable, request.session.config, request.settings,
            artifacts=request.artifacts,
        )
    except (OSError, ValueError):
        return {"status": "blocked", "reason": "production_binding_read_failed"}
    result = authorize_live_session(request.session)
    if result.get("status") != "authorized":
        return result
    try:
        stored = request.session.store.load()
        if stored is None:
            return {"status": "blocked", "reason": "production_authorization_required"}
        write_production_receipt(request.receipt_path, ProductionReceipt(
            binding, stored.envelope.authorization_id,
            stored.envelope.market_date.isoformat(),
        ))
    except (LiveAuthorizationStoreError, OSError):
        return {"status": "blocked", "reason": "production_receipt_write_failed"}
    return {**result, "executable_sha256": binding.executable_sha256,
            "config_digest": binding.config_digest,
            "settings_digest": binding.settings_digest}
