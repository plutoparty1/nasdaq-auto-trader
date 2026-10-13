# 공개 실데이터 수집 결과

수집 시각: 2026-09-29T12:37:02.306775+00:00. 개인 거래 원장·계좌·인증정보를 읽지 않는 별도 공개 조회 경로다. 실제 시세/환율은 저장소 밖 `C:/Users/u/AppData/Local/NasdaqAutoTrader/research/entry-policy-20260929/public/`에 저장했다. 파일별 원문/CSV SHA-256과 출처는 [public-data-manifest.json](public-data-manifest.json)에 있다. 기존 저장소와 LocalAppData에서 사용할 수 있는 실제 OHLC CSV를 찾지 못했고 합성 fixture만 있었으므로, 이 자료는 **제공되지 않는 자료가 아니라 이전에 수집하지 않았던 자료**다.

## 확보 범위

사전에 고정한 문제 관측 종목군 CMCSA/KDP/HIVE와 별도 대조군 SPY를 같은 날짜·주기로 요청했다. 요청은 2024-09-01~2026-09-28, 1Day다. 현재 TechnicalStrategy 지표 최소 준비량은 **64봉**이며 학습 모듈의 과거 306봉 조건과 구분한다. 아래 자료는 각각 519봉으로 길이 조건을 충족하지만 CMCSA 기업행위로 평가 가능 구간이 제한된다.

| 종목 | 일봉 수 | 실제 반환 기간 | 달력 대비 누락 수/비율 | 배당 이벤트 | 공급자 splits 이벤트 |
|---|---:|---|---|---:|---:|
| CMCSA | 519 | 2024-09-03 ~ 2026-09-28 | 0 / 0.0% | 8 | 1 |
| KDP | 519 | 2024-09-03 ~ 2026-09-28 | 0 / 0.0% | 9 | 0 |
| HIVE | 519 | 2024-09-03 ~ 2026-09-28 | 0 / 0.0% | 0 | 0 |
| SPY | 519 | 2024-09-03 ~ 2026-09-28 | 0 / 0.0% | 9 | 0 |

- `actual_trade_group.csv`: CMCSA/KDP/HIVE 1,557행. `CMCSA.csv`, `KDP.csv`, `HIVE.csv`, `SPY.csv`: 종목별 파일.
- `SYMBOL.yahoo.json`: 받은 공개 원문. `manifest.json`: 출처·수집일·범위·해시·기업행위.
- `ecb-source.csv`: ECB USD/EUR와 KRW/EUR 원문. `usdkrw.csv`: 같은 날짜 KRW/EUR ÷ USD/EUR인 KRW/USD 530행, 2024-08-30~2026-09-28.
- 주식 schema는 `symbol,timestamp,open,high,low,close,volume`, 환율은 `timestamp,usdkrw`다. 공개 시장자료만 포함한다.

## 시간·조정·누락 검증

Yahoo timestamp는 일봉 세션 날짜를 식별하는 데 사용하고, 완성 일봉의 시각은 미국 뉴욕 정규장 종가 시각으로 기록했다. IANA America/New_York로 DST를 적용하며 보통 20:00/21:00 UTC, 단축장은 17:00/18:00 UTC다. 실제 체결 시각이 아니라 **해당 세션 종가 데이터의 관측 라벨**이다. 2026-09-29 진행 중 봉과 요청 범위 밖 봉은 분석에서 제외한다. 이번 반환 자료의 범위 밖 행은 0개였다.

휴장·단축장 표는 [NYSE 2024~2026 공식 일정](https://ir.theice.com/press/news-details/2023/NYSE-Group-Announces-2024-2025-and-2026-Holiday-and-Early-Closings-Calendar/default.aspx)과 [2025-01-09 특별 휴장 공지](https://ir.nasdaq.com/news-releases/news-release-details/nasdaq-announces-closure-its-us-markets-honor-national-day-0)를 적용했다. 2026-07-02는 정상 16시 종가다. 동일 종목·세션 중복, 시간 역순, 0/음수/NaN 가격, 부정합 OHLC, 음수 거래량을 거부하고 결측값을 임의 보간하지 않는다. 네 종목 모두 예상 519거래일 대비 누락 0이었다. 거래일별 실제 상장·거래정지 이력의 별도 공급자 검증까지 완료했다는 뜻은 아니다.

Yahoo `quote` OHLC를 그대로 사용하고 `adjclose`는 사용하지 않았다. Yahoo는 Close를 분할 조정, Adj Close를 분할·배당 등 분배까지 조정한 값으로 설명한다. [Yahoo 가격 조정 설명](https://in.help.yahoo.com/kb/finance/adjusted-close-sln28256.html). 원본 배당·분할 이벤트와 adjclose는 JSON에 보존했다. **배당 현금 지급을 처리하지 않는 비교 엔진 결과는 가격 변동과 비용 기준 수익이며 배당 포함 총수익이 아니다.**

CMCSA의 2026-01-05 `splits` 항목은 공급자가 `1067:1000`으로 표시하지만, 일반 주식수 분할로 사용하면 안 된다. 공식 자료상 2026-01-02 장 종료 후 CMCSA 25주당 VSNT 1주 분사와 소수주 현금 처리가 발생했다. [Comcast 분사 자료](https://www.cmcsa.com/shareholder-services/cost-basis-guide), [SEC 공시](https://www.sec.gov/Archives/edgar/data/1166691/000095010326000079/dp239108_ex9901.htm). 공급자의 과거 가격 조정은 과거 1주 매수 가능 금액을 낮출 수 있다. 따라서 이전 OHLC를 임의 원복하거나 보유 수량에 1.067을 곱하지 않았다. 비교 담당자에게 기업행위 이전/횡단 구간의 제외를 전달했고, 주 비교는 **2026-01-06 이후 자료와 64봉 준비기간**, 추가 KDP/HIVE·SPY 비교는 원래 기간을 사용한다. 이는 성과를 본 뒤 고른 구간이 아니라 기업행위 계산 미지원 때문에 사전에 정한 데이터 품질 제한이다.

현재 확인된 종목을 과거 전체에 고정한 선택은 시점별 투자 가능 종목군 복원이 아니며 생존·선정 편향이 남는다. SPY는 대조군이며 작은 계좌에서 1주/가격 제한 때문에 거래하지 못할 수 있다. 현금으로 남은 결과를 수익전략의 증거로 보지 않는다.

## 환율 출처와 확보 실패 원인

[ECB 공식 환율 안내](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)는 EUR 기준 USD와 KRW를 제공한다. 공식 `data-api.ecb.europa.eu/service/data/EXR/D.USD+KRW.EUR.SP00.A`에서 동일 날짜 두 통화를 받아 나눈 참조환율이다. 실제 KIS 환전 체결환율·환전 스프레드가 아니다. ECB 공표 이후 값만 사용할 수 있도록 일별 값에 보수적인 16:00 UTC 가용 시각을 붙였다. 휴일은 이전 공표 값을 사용하되 미래 날짜 값으로 채우지 않는다. 최초 환율 자료는 주식 최초 봉보다 앞선 2024-08-30이다.

첫 직접 조회는 로컬 Python 기본 인증서 체인에서 `SSLCertVerificationError`가 발생했다. **인증·조회 권한 또는 기간 미제공 문제가 아니었다.** 이미 설치된 certifi CA를 명시하자 검증을 유지한 상태로 ECB 역사환율 조회가 성공했다. 인증서 검증을 끄거나 새 인증·결제·권한 우회를 하지 않았다.

Yahoo 도움말의 일반 브라우징 경로는 429, Stooq 일반 자료 페이지는 JavaScript 검증 화면을 반환했다. 차단된 페이지 보호를 우회하지 않았고, 별도의 공개 Yahoo chart GET 경로가 정상 200 응답을 반환해 그것을 사용했다. 이 경로의 향후 안정성이나 서비스 계약을 보장하지 않는다. 이번 공개 수집기는 일봉만 수집하므로 **약 5분 후 매도 당시 흐름을 정확히 복원하는 자료가 아니다**. KIS 분봉·체결 자료 조회 결과는 별도 수집 보고서에 속한다.

## 구현·검증·재실행

`research_public_transport.py`는 정확한 HTTPS 호스트·경로·쿼리·날짜와 GET만 허용한다. POST/주문/취소/다른 종목/리디렉션을 거부하고 쿼리당 총 2회 이내로 시도한다. 응답 크기 제한 8 MB와 20초 timeout이 있다. 인증 헤더·쿠키·브로커 인스턴스가 없다. CLI는 실거래 엔진을 불러오는 패키지 초기화를 실행하지 않는다. 전송 구현은 기존 프로젝트의 HTTPSConnection 방식과 이미 설치된 certifi/tzdata를 사용하며 새 패키지 설치는 하지 않았다.

실행 명령:

```text
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_research_public.py
uvx --offline ruff check nasdaq_auto_trader/research_public*.py scripts/collect_public_entry_data.py tests/test_research_public.py
python -m py_compile nasdaq_auto_trader/research_public_transport.py nasdaq_auto_trader/research_public_bars.py nasdaq_auto_trader/research_public_fx.py scripts/collect_public_entry_data.py
python scripts/collect_public_entry_data.py
python scripts/collect_public_entry_data.py --help
python scripts/collect_public_entry_data.py --output docs/entry-policy-audit-20260929/denied-public-output
```

초기 endpoint/잘못된 봉 테스트 8개 실패를 확인한 뒤 구현했다. 최종 동일 테스트 파일은 **22 passed in 3.78s**, Ruff 통과, py_compile exit 0이다. 재실행 건수는 합산하지 않았다. 정상 CLI는 종목당 519봉과 FX 530행을 실제 생성했으며 실패 목록이 비어 있었다. help exit 0, 저장소 안 output 지정은 예상대로 exit 2다. CLI import 검사에서 engine/broker/config/KIS client 모듈 로드 0이었다. 주문·취소는 허용 endpoint에 없어 수집 경로 호출 0이며, wire 전 차단 회귀 테스트로 확인했다. 모의 비교 엔진의 주문 격리는 별도 비교 테스트가 검증한다.

재실행은 같은 폴더를 덮어쓰지 않도록 저장소 밖 **새 폴더**를 지정한다. 날짜·종목 범위는 의도적으로 고정했고 임의 URL을 받지 않는다. 새로운 기간·종목이 필요하면 allowlist와 검증 달력을 함께 검토해야 한다. 소스 수정·수집 스크립트만 추가했으며 운영 설정·현재 보유 정책·배포 EXE는 이 작업 범위에서 변경하지 않았다.

보안 재검토에서 manifest가 없는 기존 폴더를 재사용할 수 있는 결함을 발견해 수정했다. 이제 해석된 저장소 밖 경로가 없거나 완전히 빈 디렉터리일 때만 수집하며, 파일 하나라도 있으면 첫 네트워크 요청 전에 exit 2로 거부한다. 기존 `CMCSA.csv`를 둔 CLI 회귀는 수정 전 네트워크 진입으로 실패했고 수정 후 파일 바이트 보존·wire 호출 0을 확인했다. 최종 같은 public 테스트 파일은 **23 passed in 3.87s**이며 Ruff·컴파일도 통과했다. 앞의 22회 실행과 합산하지 않는다. 실제 데이터를 다시 조회하지 않았고 기존 네 종목 CSV와 환율 CSV 해시는 그대로다.
