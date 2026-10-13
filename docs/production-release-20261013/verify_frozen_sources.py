from pathlib import Path
from types import CodeType
import hashlib, json, marshal, sys
from PyInstaller.archive.readers import CArchiveReader
root=Path.cwd()
exe=Path(sys.argv[1]) if len(sys.argv)>1 else root/'deploy-operating/NasdaqAutoTrader/NasdaqAutoTrader.exe'
archive=CArchiveReader(str(exe))
pyz=archive.open_embedded_archive('PYZ.pyz')
def signature(code):
    return {'bytecode':code.co_code.hex(),'names':code.co_names,'varnames':code.co_varnames,
        'args':[code.co_argcount,code.co_posonlyargcount,code.co_kwonlyargcount,code.co_flags],
        'freevars':code.co_freevars,'cellvars':code.co_cellvars,
        'constants':[signature(v) if isinstance(v,CodeType) else
                     sorted(repr(item) for item in v) if isinstance(v,frozenset) else
                     repr(v) for v in code.co_consts]}
results=[]
files=list((root/'nasdaq_auto_trader').glob('production_*.py'))+[
    root/'nasdaq_auto_trader'/name for name in (
        'engine_orders.py','engine_cycle.py','risk.py','automatic_risk.py',
        'automatic_order_pending.py','automatic_entry_eligibility.py',
        'automatic_order_guard.py','automatic_order_audit.py','automatic_order_types.py',
        'automatic_selection.py','automatic_selection_production.py','session_claims.py',
        'session_store_io.py','config_runtime.py','config_settings.py','order_decision_diagnostics.py',
    )
]
for file in files:
    packaged=marshal.loads(archive.extract('production_launcher')) if file.stem=='production_launcher' else pyz.extract('nasdaq_auto_trader.'+file.stem)
    current=compile(file.read_text(encoding='utf-8'),str(file),'exec',dont_inherit=True,optimize=0)
    equal=signature(current)==signature(packaged)
    results.append({'module':file.stem,'frozen_matches_source':equal,'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
payload={'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'modules':results,'all_match':all(i['frozen_matches_source'] for i in results)}
(root/'docs/production-release-20261013/frozen-source-match.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps(payload))
raise SystemExit(0 if payload['all_match'] else 1)
