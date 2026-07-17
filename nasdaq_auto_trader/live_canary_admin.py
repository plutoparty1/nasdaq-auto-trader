from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppConfig, validate_trading_mode
from .live_canary_identity import account_fingerprint, executable_sha256
from .live_canary_paths import CanaryPaths
from .live_canary_policy import CANARY_POLICY
from .live_canary_preflight import PreflightClient, run_preflight
from .live_canary_state import CanaryState, CanaryStateStore, StateMode
from .market_hours import regular_market_session


ARM_CONFIRMATION = "I UNDERSTAND THIS WILL PLACE REAL ORDERS TODAY"


@dataclass(frozen=True, slots=True)
class ArmIssueError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"live-canary arm rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class ArmIssueRequest:
    config: AppConfig
    client: PreflightClient
    paths: CanaryPaths
    executable: Path
    market_date: str
    confirmation: str
    now: datetime
    windows_sid_sha256: str


@dataclass(frozen=True, slots=True)
class ArmIssueResult:
    arm_payload: Mapping[str, str]
    arm_path: Path
    state_path: Path


def issue_arm(
    request: ArmIssueRequest,
    enforce_acl: Callable[[Path], None],
) -> ArmIssueResult:
    if request.confirmation != ARM_CONFIRMATION:
        raise ArmIssueError("exact confirmation phrase required")
    if request.paths.arm.exists() or request.paths.state.exists():
        raise ArmIssueError("authorization or state already exists for market date")
    _validate_live_kis(request.config)
    session = regular_market_session(request.now)
    if not session.opens_at or request.market_date != session.market_time[:10]:
        raise ArmIssueError("market date is not the current NASDAQ session")
    preflight = run_preflight(request.client)
    if not preflight.ready:
        raise ArmIssueError(",".join(preflight.blockers))
    enforce_acl(request.paths.root)
    nonce = uuid.uuid4().hex
    executable_digest = executable_sha256(request.executable)
    fingerprint = account_fingerprint(
        request.config.kis.account_no,
        request.config.kis.account_product_code,
    )
    expires_at = datetime.fromisoformat(session.closes_at).astimezone(UTC)
    payload = {
        "schema_version": "1",
        "market_date": request.market_date,
        "account_fingerprint": fingerprint,
        "product": "kis-real",
        "base_url": "https://openapi.koreainvestment.com:9443",
        "executable_sha256": executable_digest,
        "policy_digest": CANARY_POLICY.digest,
        "windows_sid_sha256": request.windows_sid_sha256,
        "state_nonce": nonce,
        "issued_at": request.now.astimezone(UTC).isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    state = CanaryState(
        market_date=request.market_date,
        nonce=nonce,
        account_fingerprint=fingerprint,
        executable_sha256=executable_digest,
        mode=StateMode.ARMED,
        owned_symbol=None,
        max_owned_quantity=0,
        round_trips=0,
        entry_attempts=0,
        exit_attempts=0,
        intent=None,
    )
    CanaryStateStore(request.paths.state).save(state)
    _atomic_json(request.paths.arm, payload)
    return ArmIssueResult(payload, request.paths.arm, request.paths.state)


def windows_sid_sha256() -> str:
    return hashlib.sha256(_current_windows_sid().encode("utf-8")).hexdigest()


def _current_windows_sid() -> str:
    completed = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    match = re.search(r"S-\d+(?:-\d+)+", completed.stdout)
    if match is None:
        raise ArmIssueError("Windows SID lookup failed")
    return match.group(0)


def enforce_private_windows_acl(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    sid = _current_windows_sid()
    commands = (
        [
            "icacls", str(root), "/inheritance:r", "/grant:r",
            f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F",
        ],
        ["icacls", str(root / "*"), "/reset", "/T"],
    )
    for command in commands:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            raise ArmIssueError("private ACL application failed")


def _validate_live_kis(config: AppConfig) -> None:
    validate_trading_mode(config)
    if config.broker != "kis" or config.mode != "live":
        raise ArmIssueError("live KIS configuration required")
    if config.kis.paper:
        raise ArmIssueError("real KIS account required")
    if config.kis.currency.upper() != "USD":
        raise ArmIssueError("USD account required")


def _atomic_json(path: Path, payload: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ArmIssueError("atomic arm write failed") from error
