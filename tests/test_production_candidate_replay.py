from nasdaq_auto_trader import production_replay


def test_candidate_full_chain_replay_is_exposed():
    # Given the executable carries the isolated sizing candidate scenarios.
    # When the replay entrypoint is inspected.
    # Then the candidate chain is available without injecting decisions.
    assert callable(getattr(production_replay, "run_candidate_cases", None))
