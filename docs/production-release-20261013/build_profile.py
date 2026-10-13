from pathlib import Path
import json, shutil, os
root = Path.cwd()
target = root / 'deploy-operating/NasdaqAutoTrader'
target.mkdir(parents=True, exist_ok=True)
safe = root / 'deploy-safe/operating-transition-20261013/NasdaqAutoTrader'
config = json.loads((safe/'config.safe.json').read_text(encoding='utf-8-sig'))
config.update(mode='live', allow_live_trading=True, live_environment_authorized=True)
config['kis']['paper'] = False
config['risk']['max_position_pct'] = .05
settings = json.loads((safe/'trading_config.json').read_text(encoding='utf-8-sig'))
settings.update(live_trading=True,dry_run=False,max_daily_loss_rate=2,log_path=str(target/'operating_state/NasdaqAutoTrader/logs/trader.log'))
for name,data in [('config.operating.json',config),('trading_config.json',settings),('fee-review.json',{'confirmed':False,'source':'unapproved_draft_actual_fees_unknown'})]:
    path=target/name
    if path.exists(): raise RuntimeError('profile already exists: '+name)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(target/'credential-source.txt').write_text(str(root/'dist/NasdaqAutoTrader/config.kis.json'),encoding='utf-8')
source = Path(os.environ['LOCALAPPDATA'])/'NasdaqAutoTrader/ai_quant_lab'
destination = target/'operating_state/NasdaqAutoTrader/ai_quant_lab'
records=[]
for name in ['strategy_registry.json','promoted_strategy.json','ai_quant_config.json','strategy_specs/builtin_ai_volatility_target-data-b230423351524f87-catalogue-v5.json']:
    item=source/name
    if item.exists():
        out=destination/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(item,out)
        records.append({'source':str(item),'destination':str(out),'kind':'unchanged_strategy_validation_not_account_approval'})
(root/'docs/production-release-20261013/profile-provenance.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
