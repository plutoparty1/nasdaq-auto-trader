from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .file_lock import FileLockTimeout, exclusive_file_lock
from .models import OrderSide


@dataclass(frozen=True, slots=True)
class BrokerLeaseError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class BrokerLiveLease:
    path: Path
    account_fingerprint: str
    allowed_sides: frozenset[OrderSide]
    _witness: _LeaseWitness

    @classmethod
    @contextmanager
    def acquire(
        cls,
        path: Path,
        account_fingerprint: str,
        allowed_sides: frozenset[OrderSide],
    ) -> Iterator[BrokerLiveLease]:
        if not account_fingerprint:
            raise BrokerLeaseError("broker_live_account_missing")
        if not allowed_sides:
            raise BrokerLeaseError("broker_live_sides_missing")
        witness = _LeaseWitness()
        try:
            with exclusive_file_lock(path, 0.05):
                try:
                    yield cls(path, account_fingerprint, allowed_sides, witness)
                finally:
                    witness.active = False
        except FileLockTimeout as exc:
            raise BrokerLeaseError("broker_live_owner_active") from exc

    def assert_allowed(
        self,
        path: Path,
        account_fingerprint: str,
        side: OrderSide,
    ) -> None:
        if not self._witness.active:
            raise BrokerLeaseError("broker_live_lease_inactive")
        if path != self.path:
            raise BrokerLeaseError("broker_live_lease_path_mismatch")
        if account_fingerprint != self.account_fingerprint:
            raise BrokerLeaseError("broker_live_account_mismatch")
        if side not in self.allowed_sides:
            raise BrokerLeaseError("broker_live_side_not_allowed")


class _LeaseWitness:
    __slots__ = ("active",)

    def __init__(self) -> None:
        self.active = True


@contextmanager
def broker_submission_guard(
    path: Path,
    account_fingerprint: str,
    side: OrderSide,
    lease: BrokerLiveLease | None = None,
) -> Iterator[None]:
    if lease is not None:
        lease.assert_allowed(path, account_fingerprint, side)
        yield
        return
    try:
        with exclusive_file_lock(path, 0.05):
            yield
    except FileLockTimeout as exc:
        raise BrokerLeaseError("broker_live_owner_active") from exc
