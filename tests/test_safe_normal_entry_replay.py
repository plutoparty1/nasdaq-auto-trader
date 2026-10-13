from pathlib import Path
import json
import shutil

from nasdaq_auto_trader.roundtrip_replay import run_replay
from nasdaq_auto_trader import safe_runtime


def test_replay_generates_real_normal_entry_plan_but_never_sends(tmp_path, monkeypatch):
    # Given the actual deployed effective settings and an irrevocably locked test process.
    release = Path('deploy-safe/roundtrip-20261013/NasdaqAutoTrader')
    for name in ('config.safe.json', 'trading_config.json'):
        shutil.copyfile(release / name, tmp_path / name)
    monkeypatch.setattr(safe_runtime, 'orders_locked', lambda: True)
    monkeypatch.setattr('nasdaq_auto_trader.engine_orders.orders_locked', lambda: True)
    output = tmp_path / 'result.json'
    # When only the offline replay creates a positive technical OHLCV fixture.
    run_replay(output, tmp_path)
    payload = json.loads(output.read_text(encoding='utf8'))
    case = next(item for item in payload['cases'] if item['case'] == 'normal_entry_order_plan')
    # Then the real strategy/sizing generate one share, and transmission stays blocked.
    assert case['decision']['action'] == 'buy'
    assert case['decision']['score'] >= 8
    assert case['order']['qty'] == 1
    assert case['response']['reason'] == 'safe_release_order_lock'
    assert case['response']['submitted_order'] is False
