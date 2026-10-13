from pathlib import Path
import json,hashlib
root=Path.cwd();source=root/'docs/roundtrip-repair-20261013/preservation-hashes.json'
records=json.loads(source.read_text(encoding='utf-8-sig'))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
changed=[str(path) for name,sha in records.items() if not (path:=Path(name)).exists() or digest(path)!=sha]
safe={}
for folder,sha in [('roundtrip-20261013','61ccd1c47252d428211f264a97129bca8f0a7a8efbd2528f0e3e07de873cdd59'),('operating-transition-20261013','fc3909f258a56b67b795d77b993062c220896ec3db040c89635b7add1aa883ed')]:
    path=root/'deploy-safe'/folder/'NasdaqAutoTrader/NasdaqAutoTraderSafe.exe'
    safe[str(path)]={'sha256':digest(path),'preserved':digest(path)==sha}
profile=root/'deploy-operating/NasdaqAutoTrader/operating_state/NasdaqAutoTrader/runtime'
approvals=list(profile.glob('*authorization*.json'))+list(profile.glob('*approval*.json'))
payload={'protected_original_files':len(records),'mismatches':changed,'safe_exes':safe,'actual_profile_approval_files':[str(p) for p in approvals],'fee_review':json.loads((root/'deploy-operating/NasdaqAutoTrader/fee-review.json').read_text(encoding='utf-8'))}
(root/'docs/production-release-20261013/preservation.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps(payload))
assert not changed and all(v['preserved'] for v in safe.values()) and not approvals
