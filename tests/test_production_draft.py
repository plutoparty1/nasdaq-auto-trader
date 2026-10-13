import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.production_draft import update_draft
from nasdaq_auto_trader.production_runtime import load_runtime


def test_draft_edits_are_not_approvals_and_invalid_edit_is_atomic():
    original = Path('deploy-operating/NasdaqAutoTrader').resolve()
    with TemporaryDirectory() as directory:
        profile = Path(directory)/'profile'
        shutil.copytree(original,profile,ignore=shutil.ignore_patterns('_internal','*.exe','runtime','*.log'))
        runtime=load_runtime(profile,Path(directory)/'old',Path(__file__).resolve())
        before=(profile/'config.operating.json').read_bytes()
        with patch('nasdaq_auto_trader.production_draft.conflicting_processes',return_value=[]):
            with pytest.raises(ValueError): update_draft(runtime,{'single_position_pct':float('nan')})
            assert (profile/'config.operating.json').read_bytes()==before
            result=update_draft(runtime,{'single_position_pct':4,'total_exposure_pct':20})
        assert result['approval_issued'] is False
        assert not runtime.receipt_path.exists() and not runtime.authorization_path.exists()
        assert json.loads((profile/'config.operating.json').read_text())['risk']['max_position_pct']==.04
        assert json.loads((profile/'fee-review.json').read_text())['confirmed'] is False
        assert load_runtime(profile,runtime.original_data,runtime.executable).settings.order_qty==1
