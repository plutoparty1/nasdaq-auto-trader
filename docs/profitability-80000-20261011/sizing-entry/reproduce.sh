#!/usr/bin/env bash
set -euo pipefail
experiment_output="${1:?Provide a new empty output directory}"
market_data='C:/Users/u/AppData/Local/NasdaqAutoTrader/research/entry-policy-20260929/public'
PYTHONIOENCODING=utf-8 python scripts/run_entry_policy_comparison.py \
  --bars "$market_data/actual_trade_group_after_corporate_action.csv" \
  --provenance "$market_data/comparison-provenance.json" \
  --output "$experiment_output" --usdkrw 1333.6339857490755 \
  --fx-source ECB-reference-KRW-per-EUR-divided-by-USD-per-EUR \
  --fx-as-of 2024-08-30T16:00:00+00:00 --fx-history "$market_data/usdkrw.csv" \
  --train-end 2025-08-29T23:59:59+00:00 \
  --validation-end 2026-02-27T23:59:59+00:00 \
  --profitability-profile experiments/sizing_entry_80000/profile.json
