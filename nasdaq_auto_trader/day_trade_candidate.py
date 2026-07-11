from __future__ import annotations

from .day_trade_pricing import (
    _candidate_score,
    _change_pct,
    _first_float,
    _first_text,
    _pct_range,
    _spread_pct,
)
from .day_trade_types import CandidateEvaluation, DayTradeDataClient


class DayTradeCandidateMixin:
    def _evaluate_candidate(
        self,
        client: DayTradeDataClient,
        symbol: str,
    ) -> CandidateEvaluation:
        evaluation = CandidateEvaluation(symbol=symbol, eligible=True)
        try:
            detail = client.get_price_detail(symbol)
            quote = client.get_best_quote(symbol)
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            evaluation.eligible = False
            evaluation.exclude_reasons.append(f"api_error:{type(exc).__name__}:{exc}")
            return evaluation

        evaluation.name = _first_text(
            detail,
            quote,
            "name",
            "item_name",
            "prdt_name",
            "prdt_eng_name",
            "ovrs_item_name",
            "hts_eng_nm",
            "kor_isnm",
            default=symbol,
        )
        last_price = _first_float(detail, quote, "last", "ovrs_nmix_prpr", "stck_prpr")
        bid = _first_float(quote, detail, "pbid1", "bid")
        ask = _first_float(quote, detail, "pask1", "ask")
        high = _first_float(detail, quote, "high", "ovrs_nmix_hgpr", "stck_hgpr")
        low = _first_float(detail, quote, "low", "ovrs_nmix_lwpr", "stck_lwpr")
        base = _first_float(detail, quote, "base", "rclose", "stck_sdpr")
        volume = _first_float(detail, quote, "tvol", "acml_vol", "volume")
        bid_size = _first_float(quote, detail, "vbid1", "dbid1")
        ask_size = _first_float(quote, detail, "vask1", "dask1")
        buy_limit_price = ask if ask > 0 else last_price
        spread_pct = _spread_pct(bid, ask)
        day_range_pct = _pct_range(high, low, last_price)
        change_pct = _change_pct(last_price, base)
        dollar_volume = volume * last_price
        buffer = max(
            self.config.fee_buffer_usd,
            buy_limit_price * self.config.fee_buffer_pct / 100,
        )
        required = buy_limit_price * self.config.qty + buffer

        evaluation.last_price = last_price
        evaluation.bid = bid
        evaluation.ask = ask
        evaluation.buy_limit_price = buy_limit_price
        evaluation.spread_pct = spread_pct
        evaluation.bid_size = bid_size
        evaluation.ask_size = ask_size
        evaluation.volume = volume
        evaluation.dollar_volume = dollar_volume
        evaluation.day_range_pct = day_range_pct
        evaluation.change_pct = change_pct
        evaluation.estimated_required_amount = required
        evaluation.score = _candidate_score(day_range_pct, dollar_volume, spread_pct)

        if last_price <= 0:
            evaluation.exclude_reasons.append("missing_or_invalid_price")
        if last_price > self.config.max_total_usd:
            evaluation.exclude_reasons.append("price_above_max_total_usd")
        if bid <= 0 or ask <= 0:
            evaluation.exclude_reasons.append("missing_bid_or_ask")
        if spread_pct <= 0 or spread_pct > self.config.max_spread_pct:
            evaluation.exclude_reasons.append("spread_too_wide")
        if bid_size + ask_size < self.config.min_quote_depth:
            evaluation.exclude_reasons.append("quote_depth_too_low")
        if volume < self.config.min_volume:
            evaluation.exclude_reasons.append("volume_too_low")
        if dollar_volume < self.config.min_dollar_volume:
            evaluation.exclude_reasons.append("dollar_volume_too_low")
        if day_range_pct < self.config.min_day_range_pct:
            evaluation.exclude_reasons.append("day_range_too_low")
        if day_range_pct > self.config.max_day_range_pct:
            evaluation.exclude_reasons.append("day_range_too_high")
        if abs(change_pct) > self.config.max_abs_change_pct:
            evaluation.exclude_reasons.append("daily_change_too_extreme")
        if required > self.config.max_total_usd:
            evaluation.exclude_reasons.append("required_amount_above_max_total_usd")

        evaluation.eligible = not evaluation.exclude_reasons
        return evaluation

    def _select_affordable_candidate(
        self,
        client: DayTradeDataClient,
        evaluations: list[CandidateEvaluation],
    ) -> CandidateEvaluation | None:
        ranked = sorted(
            [item for item in evaluations if item.eligible],
            key=lambda item: item.score,
            reverse=True,
        )
        for evaluation in ranked:
            try:
                buying_power = client.get_overseas_buying_power(
                    evaluation.symbol,
                    evaluation.buy_limit_price,
                )
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                evaluation.eligible = False
                evaluation.exclude_reasons.append(
                    f"buying_power_api_error:{type(exc).__name__}:{exc}"
                )
                continue
            evaluation.buying_power_checked = True
            evaluation.buying_power = buying_power
            evaluation.one_share_affordable = (
                buying_power >= evaluation.estimated_required_amount
            )
            if evaluation.one_share_affordable:
                return evaluation
            evaluation.eligible = False
            evaluation.exclude_reasons.append("buying_power_insufficient")
        return None
