from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import isclose
from pathlib import Path
from typing import Final, Literal, assert_never

from .backtest_costs import BacktestCosts
from .data import load_bars_csv
from .exit_experiment_config import CostScenario, ExperimentInputError
from .experimental_exit_state import valid_atr
from .models import Bar

CsvRow = Mapping[str, str]
Group = tuple[str, ...]
Policy = Literal["C", "fixed_8", "fixed_10", "entry_atr14x3_1day"]
GROUP_FIELDS: Final = ("split", "profile", "policy", "risk_pct", "cost_scenario")
POLICIES: Final[Mapping[str, Policy]] = {name: name for name in
    ("C", "fixed_8", "fixed_10", "entry_atr14x3_1day")}


@dataclass(frozen=True, slots=True)
class RiskWindow:
    group: Group
    symbol: str
    start: str
    end: str | None
    risk: float
    pending: bool
    end_after_evaluation: bool = False


@dataclass(frozen=True, slots=True)
class SavedTables:
    constraints: list[CsvRow]
    orders: list[CsvRow]
    fills: list[CsvRow]
    rejections: list[CsvRow]
    equity: list[CsvRow]


def _read(path: Path) -> list[CsvRow]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _group(row: CsvRow) -> Group:
    return tuple(row[field] for field in GROUP_FIELDS)


def _identity(row: CsvRow, *, signal: bool = False) -> tuple[Group, str, str]:
    return _group(row), row["signal_timestamp" if signal else "timestamp"], row["symbol"]


def _stop(policy: Policy, price: float, volatility: float | None) -> float | None:
    match policy:
        case "C":
            return price - min(price * 0.03, volatility * 3) if volatility else price * 0.97
        case "fixed_8":
            return price * 0.92
        case "fixed_10":
            return price * 0.90
        case "entry_atr14x3_1day":
            return (price - volatility * 3 if volatility is not None
                    and 0.005 <= volatility * 3 / price <= 0.10 else None)
        case unreachable:
            assert_never(unreachable)


def _volatility(bars: Mapping[str, list[Bar]], symbol: str, timestamp: str) -> float | None:
    return valid_atr([bar for bar in bars[symbol] if bar.timestamp <= timestamp], 14)


def _verify_fill(order: CsvRow, fill: CsvRow, bars: Mapping[str, list[Bar]], costs: BacktestCosts) -> None:
    signal_price, fill_price, planned = (float(row[field]) for row, field in
        ((order, "price"), (fill, "price"), (order, "planned_risk")))
    if float(order["qty"]) != 1 or float(fill["qty"]) != 1 or fill_price > signal_price + 1e-10:
        raise ExperimentInputError("fill violates the frozen one-share limit invariant")
    observed = next((bar for bar in bars[fill["symbol"]] if bar.timestamp == fill["timestamp"]), None)
    if observed is None or observed.volume <= 0 or not isclose(
            fill_price, observed.open * (1 + costs.adverse_fraction), abs_tol=1e-8):
        raise ExperimentInputError("saved fill does not match the admissible next-open model")
    volatility = _volatility(bars, order["symbol"], order["timestamp"])
    policy = POLICIES.get(order["policy"])
    if policy is None:
        raise ExperimentInputError("unknown frozen policy in saved orders")
    signal_stop, fill_stop = _stop(policy, signal_price, volatility), _stop(policy, fill_price, volatility)
    if signal_stop is None or fill_stop is None:
        raise ExperimentInputError("saved fill has no permitted initial stop")
    expected = (signal_price - signal_stop + costs.fee(signal_price) + costs.fee(signal_stop)
                + (signal_price + signal_stop) * costs.adverse_fraction)
    fill_risk = (fill_price - fill_stop + costs.fee(fill_price) + costs.fee(fill_stop)
                 + fill_stop * costs.adverse_fraction)
    if not isclose(expected, planned, abs_tol=1e-8) or fill_risk > planned + 1e-8:
        raise ExperimentInputError("retained planned risk invariant failed at the saved fill")


def _windows(tables: SavedTables, bars: Mapping[str, list[Bar]], costs: Mapping[str, BacktestCosts]) -> list[RiskWindow]:
    orders = {_identity(row): row for row in tables.orders}
    buys = {_identity(row, signal=True): row for row in tables.fills if row["side"] == "buy"}
    rejected = {_identity(row, signal=True): row for row in tables.rejections}
    if len(orders) != len(tables.orders) or len(buys) != sum(row["side"] == "buy" for row in tables.fills):
        raise ExperimentInputError("duplicate saved order or buy-fill identity")
    windows: list[RiskWindow] = []
    for identity, order in orders.items():
        fill, rejection = buys.get(identity), rejected.get(identity)
        if (fill is None) == (rejection is None):
            raise ExperimentInputError("every saved buy candidate needs exactly one fill or rejection")
        outcome = fill if fill is not None else rejection
        if outcome is None:
            raise ExperimentInputError("missing order outcome")
        end_after = outcome.get("reason") == "end_of_data_unfilled"
        if outcome["timestamp"] == order["timestamp"] and not end_after:
            continue
        windows.append(RiskWindow(_group(order), order["symbol"], order["timestamp"],
                                   outcome["timestamp"], float(order["planned_risk"]), True, end_after))
    active: dict[tuple[Group, str], RiskWindow] = {}
    for fill in sorted(tables.fills, key=lambda row: (_group(row), row["timestamp"], row["symbol"])):
        identity = (_group(fill), fill["symbol"])
        if fill["side"] == "buy":
            order = orders.get(_identity(fill, signal=True))
            if order is None or identity in active:
                raise ExperimentInputError("buy fill lacks a unique unheld accepted order")
            _verify_fill(order, fill, bars, costs[fill["cost_scenario"]])
            active[identity] = RiskWindow(_group(fill), fill["symbol"], fill["timestamp"],
                                          None, float(order["planned_risk"]), False)
        else:
            if identity not in active or float(fill["qty"]) != 1:
                raise ExperimentInputError("saved sell does not close one matched held share")
            windows.append(replace(active.pop(identity), end=fill["timestamp"]))
    return windows + list(active.values())


def _used(windows: list[RiskWindow], timestamp: str, symbol: str) -> float:
    return sum(window.risk for window in windows
               if (window.start < timestamp or (window.start == timestamp
                   and (not window.pending or window.symbol < symbol)))
               and (window.end is None or timestamp < window.end
                    or (window.end_after_evaluation and timestamp == window.end)))


def audit_saved_constraints(result_dir: Path, bars_path: Path, output_dir: Path) -> Path:
    """Enrich fixed saved results; never rerun strategies or rewrite their numeric outputs."""
    if output_dir.exists():
        raise ExperimentInputError("audit output must be a fresh directory")
    names = ("constraints", "orders", "fills", "order_rejections", "equity")
    paths = [result_dir / f"{name}.csv" for name in names] + [result_dir / "protocol.json"]
    source_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    protocol = json.loads((result_dir / "protocol.json").read_text(encoding="utf-8"))
    bars_hash = hashlib.sha256(bars_path.read_bytes()).hexdigest()
    if bars_hash != protocol["manifest"]["bars_sha256"]:
        raise ExperimentInputError("public bar source differs from the saved experiment")
    scenarios = [CostScenario(**item) for item in protocol["costs"]]
    costs = {item.name: BacktestCosts(item.commission_pct, item.minimum_commission,
                                    item.spread_bps, item.slippage_bps, 1) for item in scenarios}
    tables = SavedTables(*(_read(path) for path in paths[:5]))
    bars = load_bars_csv(bars_path)
    by_group: dict[Group, list[RiskWindow]] = defaultdict(list)
    for window in _windows(tables, bars, costs):
        by_group[window.group].append(window)
    immediate = {_identity(row, signal=True): row["reason"] for row in tables.rejections
                 if row["timestamp"] == row["signal_timestamp"] and row["reason"] != "end_of_data_unfilled"}
    output: list[Mapping[str, str | float | bool | None]] = []
    counts: Counter[tuple[Group, str]] = Counter()
    for row in tables.constraints:
        group = _group(row)
        equity = float(row["risk_budget"]) / float(row["risk_pct"])
        used = _used(by_group[group], row["timestamp"], row["symbol"])
        planned = float(row["planned_risk"]) if row["planned_risk"] else None
        blocked = None if planned is None else used + planned > equity * 0.06 + 1e-10
        conditions = re.findall(r"'([^']+)'", row["blocking_conditions"])
        enriched = list(conditions)
        atr_reason = ""
        if "invalid_initial_stop_or_atr" in conditions and row["policy"] == "entry_atr14x3_1day":
            volatility = _volatility(bars, row["symbol"], row["timestamp"])
            atr_reason = "invalid_or_missing_entry_atr" if volatility is None else "entry_stop_outside_bounds"
            if volatility is not None and 0.005 <= volatility * 3 / float(row["price"]) <= 0.10:
                raise ExperimentInputError("saved invalid ATR block contradicts available daily bars")
            enriched.append(atr_reason)
        if blocked:
            enriched.append("portfolio_risk_limit")
        actual_rejection = immediate.get(_identity(row), "")
        first = actual_rejection if row["first_reason"] == "accepted" and actual_rejection else row["first_reason"]
        if blocked and row["first_reason"] == "accepted" and actual_rejection != "portfolio_risk_limit":
            raise ExperimentInputError("portfolio reconstruction contradicts saved submission outcome")
        output.append({**{field: row[field] for field in GROUP_FIELDS}, "timestamp": row["timestamp"],
            "symbol": row["symbol"], "source_first_reason": row["first_reason"],
            "source_blocking_conditions": row["blocking_conditions"], "enriched_first_reason": first,
            "enriched_blocking_conditions": json.dumps(enriched), "diagnostic_only": True,
            "portfolio_used_risk_usd": used, "portfolio_cap_usd": equity * 0.06,
            "equity_usd": equity, "planned_risk_usd": planned,
            "counterfactual_portfolio_block": blocked, "actual_submission_rejection": actual_rejection,
            "entry_atr_diagnostic": atr_reason})
        counts[(group, "rows")] += 1
        counts[(group, "portfolio_co_block_count")] += bool(blocked)
        counts[(group, "portfolio_unknown_invalid_stop_count")] += blocked is None
        if atr_reason:
            counts[(group, atr_reason)] += 1
    maxima: dict[Group, float] = defaultdict(float)
    for row in tables.equity:
        group = _group(row)
        maxima[group] = max(maxima[group], 100 * _used(by_group[group], row["timestamp"], "\uffff") / float(row["equity"]))
    groups = sorted({_group(row) for row in tables.constraints})
    summary = {"diagnostic_only": True, "strategy_rerun": False, "source_sha256": source_hashes,
        "bars_sha256": bars_hash, "buy_fill_invariants_verified": sum(row["side"] == "buy" for row in tables.fills),
        "max_risk_sampling": "daily_close_after_all_orders_including_pending_original_planned_losses",
        "rows": [{**dict(zip(GROUP_FIELDS, group, strict=True)),
                  **{name: count for (key, name), count in counts.items() if key == group},
                  "max_actual_used_risk_pct": maxima[group]} for group in groups]}
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != source_hashes[path.name] for path in paths):
        raise ExperimentInputError("source results changed during audit")
    output_dir.mkdir(parents=True)
    with (output_dir / "portfolio-constraints.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]) if output else ["diagnostic_only"])
        writer.writeheader()
        writer.writerows(output)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return output_dir
