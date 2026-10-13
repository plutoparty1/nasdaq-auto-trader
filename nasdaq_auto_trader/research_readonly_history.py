from __future__ import annotations

import math
from collections import defaultdict

from .research_readonly import JsonMap, JsonValue


def summarize_history(rows: list[JsonMap]) -> JsonMap:
    unique = {
        (
            str(row.get("ovrs_excg_cd")),
            str(row.get("ord_dt")),
            str(row.get("odno")),
        ): row
        for row in rows
    }
    statuses = {
        "filled": 0,
        "partially_filled": 0,
        "accepted_or_unknown_unfilled": 0,
        "cancel_or_revision_record": 0,
        "invalid": 0,
    }
    inventory: dict[str, tuple[float, float, float]] = {}
    finished = 0
    matched_gross = 0.0
    unmatched_sells = 0
    side_counts: dict[str, int] = defaultdict(int)
    ordered = sorted(
        unique.values(),
        key=lambda row: (
            str(row.get("ord_dt") or ""),
            str(row.get("ord_tmd") or ""),
            str(row.get("odno") or ""),
        ),
    )
    for row in ordered:
        try:
            qty = float(str(row.get("ft_ord_qty", row.get("ord_qty", "nan"))))
            filled = float(str(row.get("ft_ccld_qty", row.get("ccld_qty", "nan"))))
            price = float(str(row.get("ft_ccld_unpr3", row.get("ft_ccld_unpr", "nan"))))
        except ValueError:
            statuses["invalid"] += 1
            continue
        if not math.isfinite(qty + filled) or qty <= 0 or filled < 0 or filled > qty:
            statuses["invalid"] += 1
            continue
        if str(row.get("rvse_cncl_dvsn") or "") not in {"", "00"} or str(
            row.get("orgn_odno") or ""
        ).strip("0 "):
            statuses["cancel_or_revision_record"] += 1
            continue
        status = (
            "filled"
            if filled == qty
            else "partially_filled"
            if filled > 0
            else "accepted_or_unknown_unfilled"
        )
        statuses[status] += 1
        if filled <= 0 or not math.isfinite(price) or price <= 0:
            continue
        side = str(row.get("sll_buy_dvsn_cd") or "")
        side_counts[side] += 1
        symbol = str(row.get("pdno") or "")
        held, basis, cycle_profit = inventory.get(symbol, (0.0, 0.0, 0.0))
        if side == "02":
            inventory[symbol] = (held + filled, basis + filled * price, cycle_profit)
        elif side == "01":
            if held < filled:
                unmatched_sells += 1
                inventory.pop(symbol, None)
                continue
            sale_profit = filled * (price - basis / held)
            remainder = held - filled
            if remainder <= 1e-8:
                finished += 1
                matched_gross += cycle_profit + sale_profit
                inventory.pop(symbol, None)
            else:
                inventory[symbol] = (
                    remainder,
                    basis * remainder / held,
                    cycle_profit + sale_profit,
                )
    fields = sorted({key for row in rows for key in row})
    execution_fields = [
        key
        for key in fields
        if key in {"ccld_dt", "ccld_tmd", "ccld_time", "execution_time"}
    ]
    fee_fields = [
        key
        for key in fields
        if any(word in key.lower() for word in ("fee", "cmsn", "commission", "tax"))
    ]
    status_counts: JsonMap = {key: value for key, value in statuses.items()}
    field_values: list[JsonValue] = [key for key in fields]
    execution_values: list[JsonValue] = [key for key in execution_fields]
    fee_values: list[JsonValue] = [key for key in fee_fields]
    return {
        "raw_rows": len(rows),
        "deduplicated_orders": len(unique),
        "status_counts": status_counts,
        "field_names": field_values,
        "execution_time_field_candidates": execution_values,
        "execution_time_status": "not_provided_in_observed_schema"
        if not execution_fields
        else "requires_contract_verification",
        "fee_field_candidates": fee_values,
        "fee_status": "not_provided_in_observed_schema"
        if not fee_fields
        else "requires_contract_verification",
        "fees_usd": None,
        "roundtrip_holding_time_available": False,
        "filled_buy_order_count": side_counts.get("02", 0),
        "filled_sell_order_count": side_counts.get("01", 0),
        "closed_position_cycles_within_window": finished,
        "matched_cycle_gross_pnl_usd": round(matched_gross, 8),
        "unmatched_sell_orders": unmatched_sells,
        "open_position_symbols_at_window_end": len(inventory),
        "matching_assumption": "order_date_time_sequence_for_cumulative_fills; not_actual_execution_time",
    }
