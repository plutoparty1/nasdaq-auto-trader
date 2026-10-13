from pathlib import Path

root = Path('C:/Users/u/nasdaq-auto-trader')
a = Analysis(
    [str(root / 'nasdaq_auto_trader/safe_launcher.py')],
    pathex=[str(root)], binaries=[],
    datas=[(str(root / 'nasdaq_auto_trader/quant_data/defaults/nasdaq_100_universe.json'),
            'nasdaq_auto_trader/quant_data/defaults')],
    hiddenimports=['pandas_market_calendars'], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='NasdaqAutoTraderSafe',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=True, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name='NasdaqAutoTrader')
