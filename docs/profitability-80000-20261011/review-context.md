# Context and data interpretation review

Verdict: **PASS**. Confidence: **HIGH for the frozen offline comparison and its stated scope**. This is the context review lane, not approval for trading or proof of profitability. No implementation files were changed by this reviewer.

## Evidence reviewed

- Prior entry audit `REPORT.md`, `VERIFICATION.md`, `comparison-guide.md`, `public-data.md`, the frozen plan/amendment and referenced original simulation artifacts.
- Prior exit audit `REPORT.md`, `experiment-guide.md` and the existing offline entry/exit profiles.
- New `PROTOCOL.md`, frozen `experiments/profitability_80000/profile.json`, legacy audit, new main/pair manifests, protocols, summaries, benchmark/fill/feasibility tables and the source modules governing those interpretations.
- The narrow Git path/keyword history search returned no matching committed history for the audit/experimental files. Current HEAD was `2b37034` (`260909`); these current audit artifacts are uncommitted. No checkout, staging, commit or history changes were performed. No private sessions, credentials or personal transaction ledger were read.
- KIS public fee page fetched on 2026-10-11: [market fee schedule](https://securities.koreainvestment.com/main/bond/research/_static/TF03ca050000.jsp). It lists US online commission 0.25% and separately lists a sell-side regulatory charge. This supports 0.25% as a public reference scenario, not the particular account's historically charged fee. The stress minimum fee, spread and slippage remain explicit estimates. The retrieved page's regulatory rate is not applied retrospectively as a verified historical rate.

## Findings

| Context | Result and evidence |
|---|---|
| C's role | PASS. The protocol identifies C as the corrected entry baseline. The old comparison's common 1% risk is preserved and explicitly distinguished from the historical 5% minimum-buy exception. |
| Candidate boundaries | PASS. Main has 24 result rows and pair has 72, comprising exactly 12 distinct profiles across the fixed cost scenarios and existing splits. These are four policy bundles times 1/2/4% risk, not 96 separately tuned candidates. |
| Changed sizing interpretation | PASS. The new protocol explicitly distinguishes C's actual first initial stop distance from the old conservative `max(fixed distance, ATR distance)` sizing proxy. New C results must not be portrayed as the old C plus only a changed numerical budget. The new aggregate 6% planned-risk ceiling and stricter buy fill model are also disclosed. |
| Capital and share quantity | PASS. Original main capital is KRW 80,000 converted to USD 54.072814354631596. New result tables retain the conversion by each split's starting FX. `brokers/kis_order.py` floors share quantities, refuses fewer than one share and checks both deposited cash and overseas buying power. The experiment enforces an integer step and the existing one-share cap; raising risk can change eligibility without increasing the size of a matched trade. |
| Daily indicator time scale | PASS. `experiments/entry_policy/profile.json` and the original protocol use `long_sma=20`, not 200. The evaluation uses 64 completed daily bars for initialization. The new protocol keeps daily signals and does not reinterpret 200 daily observations as 200 five-minute bars. |
| 519 bars versus four or five months | PASS. The CMCSA corporate-action exclusion leaves all three main symbols on the common 183-bar period from 2026-01-06. After 64 initialization bars, 119 evaluation bars run 2026-04-09 through 2026-09-28. Only May through August span full calendar windows under the inherited conservative definition. The action-free pair retains 519 minus 64 = 455 evaluation bars across train/validation/final; the five-month statement refers to final's April through August, not all 455 bars. |
| Corporate actions | PASS with documented limitation. CMCSA's provider event `1067:1000` is a spinoff-related price adjustment, not a share multiplication instruction. The old pre-performance data amendment excludes the crossing period and remains in force. KDP/HIVE have no recorded split events in the frozen files. Provider absence of an event is not an independent issuer-level completeness guarantee. |
| Five-minute data | PASS. The four trading days remain auxiliary evidence about repeated signals and protection timing. They are not expanded into monthly/annual evidence and are not used as a substitute for daily signal history. |
| Independence | PASS. Both new manifests contain `assessment=EXPLORATORY_ALREADY_USED_DATA` and `no_independent_holdout=true`. The old train/validation/final names do not create fresh holdout evidence. No new independent market period or synthetic profitability evidence is claimed. |
| Benchmarks | PASS. USD cash has zero modeled interest and separate FX translation. The frozen equal-budget integer basket buys only HIVE in every main/pair cost/split case. It must be described as the integer-rounded basket, not a fully invested three/two-symbol portfolio. Fractional references explicitly carry `NONEXECUTABLE_REFERENCE`, violate integer/total-exposure constraints and omit costs. |
| Monthly target | PASS. All 96 strategy result rows have zero target-complete-month observations. Fractional reference returns are not executable target achievements. Inherited calendar-boundary criteria conservatively exclude some otherwise complete trading-month observations; this convention is explicitly explained and not changed after seeing outcomes. |

## Independent dividend overlap check

The reviewer computed [dividend-overlap.json](dividend-overlap.json) directly from the frozen public Yahoo dividend events and actual new candidate/benchmark fills. It contains 120 scenario records and input/output SHA-256 hashes. The calculation uses holdings before the ex-date opening: a same-date buy is ineligible and a same-date sale remains eligible. Daily fill labels are session-close labels, so the comparison uses trading-session dates.

- All **96 candidate cases** have zero overlap with a recorded cash dividend.
- All **8 executable integer buy-and-hold cases** hold HIVE only and have zero recorded dividend overlap.
- The **8 fractional references** omit the following gross dividend entitlements. These references remain non-executable.

| Reference window | Omitted gross entitlement, USD | Gross return addition upper bound, percentage points |
|---|---:|---:|
| Main final | 0.52263670 | 0.966542 |
| Pair train | 0.60807562 | 1.066461 |
| Pair validation | 0.45898971 | 0.800557 |
| Pair final | 0.63027670 | 1.151920 |

The values are identical between cost labels because the fractional reference is deliberately frictionless. They are not recalculated total returns: withholding, payment dates, reinvestment and payment FX are unverified. The KDP ex-date on 2026-09-28 does not prove the corresponding cash was paid by the evaluation endpoint. These gross amounts are accounting sensitivities for the recorded path. CMCSA dividends before the exclusion date are provider-adjusted and are not used in these overlap amounts.

Consequently, omitted recorded dividends do **not** change the candidate-versus-executable-benchmark comparison here. They do mean that the already non-executable fractional price reference understates dividend-inclusive economic performance. The old report's short-trade dividend conclusion was rechecked rather than assumed to apply to buy-and-hold.

## Remaining data caveats

The frozen cohort was selected after the historical events; it is not a contemporaneous investable-universe reconstruction. Public OHLC values are not the original as-observed snapshots. Daily close protection followed by next-open execution is not continuous intraday protection, and daily labels are not actual execution times. Modeled next-open eligibility is conservative relative to a simple low-touch fill but cannot prove queue position or actual liquidity. Stop percentages are planned distances, not realized-loss guarantees across gaps. Actual commissions, minimums, levies, FX conversion costs and operating costs remain incompletely verified.

The original and new experiment differ in sizing proxy and fill assumptions, so a before/after performance difference cannot be attributed solely to removing forced entry or widening the stop. Within the new experiment, fixed/ATR policies change profit-taking and trailing protection together with the initial stop; generic technical exits remain active. These limits permit exploratory rejection of unsupported candidates, not a permanent conclusion about the entire project.

Blocking missed context: **none in the reviewed frozen protocol and result artifacts**. Final reporting must retain the scope and dividend/benchmark qualifications above.
