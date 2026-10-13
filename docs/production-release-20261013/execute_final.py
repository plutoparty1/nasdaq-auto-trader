from pathlib import Path
import json, subprocess, os, hashlib
root=Path.cwd();out=root/'docs/production-release-20261013';exe=root/'deploy-operating/NasdaqAutoTrader/NasdaqAutoTrader.exe'
commands=[('runtime',['--runtime-check']),('help',['--help']),('authorize-help',['authorize-live-session','--help']),('draft-help',['draft-limits','--help']),('replay',['--replay',str(out/'frozen-replay.json')]),('gui',['--gui-smoke',str(out/'frozen-gui')]),('preflight',['preflight'])]
results=[]
for label,args in commands:
    result=subprocess.run([str(exe),*args],capture_output=True,timeout=300,env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
    streams=[]
    for raw in (result.stdout,result.stderr):
        try: streams.append(raw.decode('utf-8'))
        except UnicodeDecodeError: streams.append(raw.decode('cp949',errors='replace'))
    (out/f'frozen-{label}.log').write_text(streams[0]+streams[1],encoding='utf-8')
    results.append({'name':label,'exit':result.returncode,'arguments':args})
    (out/'frozen-execution.json').write_text(json.dumps({'executable':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'executions':results,'actual_orders':0,'actual_approvals':0,'actual_live_start':False},indent=2),encoding='utf-8')
    if result.returncode != 0: raise RuntimeError('frozen_failure:'+label)
print(json.dumps(results))
