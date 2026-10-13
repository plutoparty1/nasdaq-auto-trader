# 조회 전용 자료 확보 결과

2026-09-29 UTC 12:32 및 12:38에 **실제 KIS 인증과 조회**를 수행했다. 주문·취소·잔고 변경·스케줄 실행은 하지 않았다. 개인 원장은 저장소 밖 `%LOCALAPPDATA%/NasdaqAutoTrader/research/entry-policy-20260929/`에만 저장했다. 이 문서와 JSON에는 집계·필드 이름·공개 시세의 범위만 기록했다. 원장 원문, 계좌번호, 키와 토큰은 출력하지 않았다.

## 자료 부족의 원인과 이번 확보 범위

|자료|직전 상태 / 이번 확인|현재 한계|
|---|---|---|
|인증|최초 adjacent `.env`만 확인한 presence 검사는 미확보. 실제 `gui_launcher._load_exe_env()`의 LocalAppData `.env` 우선순위를 반영하자 인증 성공|인증 장애가 원인은 아니었다. 기존 설정 파일은 읽기만 했으며 토큰 캐시는 읽거나 수정하지 않음|
|주문·체결|최근90일 20행에서, 6개월 조회로 **22개 원주문** 확보. 모두 누적 체결수량=주문수량. 매수11·매도11, 연결 가능한 청산 주기11개|목표20~30개 청산보다 적다. 조회한2026-04-01~09-28 범위의 반환 수이며 계좌의 평생 거래 수는 아님|
|체결 시각|응답에 `ord_dt`, `ord_tmd`, `thco_ord_tmd`는 있음. 체결 시각 필드는 없음|주문 시각을 체결 시각으로 쓰지 않으므로 실제 보유시간 계산 불가|
|체결가·수량|`ft_ccld_unpr3`, `ft_ccld_qty`, `ft_ccld_amt3` 제공|누적 평균값이며 개별 부분 체결 이벤트 시각·체결 순서는 없음|
|수수료·제비용|이번 관측 스키마에 관련 필드 없음|실제 비용은 `null`; 0원으로 확정하지 않음|
|일봉|사전 고정 CMCSA/KDP/HIVE와 별도 비교 SPY 각각 **500봉**,2024-09-30~2026-09-28|현재 local source의 한 페이지 조회가 자료 부족에 기여. 이번에는 BYMD를 과거로 이동하여 종목당6페이지 조회|
|과거5분봉|3종목 모두9/23·24·25·28 정규장312개 예정 시각 완비|전체 시세 틱, 당시 API 응답, 당시 미완성 일봉은 복원하지 못함. 봉 라벨의 시작/종료 의미 미확정|

6개월 응답은 4월0·5월0·6월2·7월2·8월8·9월10행이다. 공식 공개 함수는 현지 주문 시작일·종료일을 받으며 확인한 문서에3개월 제한이 없었다. 월별6회로 범위를 제한해 실제 반환을 확인했다. `NASD`는 해당 계약에서 미국시장 전체를 뜻한다. 범위 밖 거래가 없다고 주장하지 않는다.

22행의 원주문 식별자·날짜·거래소 중복을 제거하고 누적 체결수량으로 연결했을 때 완결 주기11개, 미연결 매도0개, 이 구간 매매에서 남은 수량0개다. 연결 순서는 주문 날짜·시각 정렬이며 실제 체결 시각의 증거는 아니다. 비용 전 연결 손익 합계는 **−$1.083**이다. 수수료·환율·외부 입출금·구간 시작 보유분 전체를 포함한 계좌 수익률로 바꾸어 해석하지 않는다.

## 시세 품질·시간·미래 정보 경계

- 요청 기간은 응답 전에2024-09-28~2026-09-28, 종목은 CMCSA/KDP/HIVE/SPY로 고정했다. 현재 시점 유동성 순위를 과거 선정에 사용하지 않았다. 실제 거래 종목에서 출발한 고정 종목군 자체는 사후 선정이므로 종목 선택의 생존 편향이 없는 모집단 실험은 아니다.
- 일봉500개는 지표 준비64봉과 별도 학습 준비306봉을 모두 충족한다. 네 종목 모두 SPY의500개 관측 세션 대비 결측0, 중복0, 비정상 OHLCV0이다. **공식 거래소 캘린더 전수 대조를 대신하는 수치는 아니다.**
- 일봉은 기존 로컬 호출과 동일하게 `MODP=1`을 요청했다. 공급자의 수정주가 정의와 개별 분할 사건 표를 별도로 확보하지 않아 수정 계수·배당·당시 주식 수량을 완전히 검증하지 못했다. 현재 제공되는 과거 가격을 당시 알려진 가격 이력이라고 단정하지 않는다.
- 일봉 CSV의16:00 America/New_York 라벨은 표준 종가 시각 정규화다. 조기 폐장 일자를 별도 검증하지 않았다. 장중 재현은 전일 이전의 완성 일봉만 사용해야 한다.
- 분봉 `xymd/xhms`를 미국 현지 시각으로 해석한 UTC 값은 모든 반환 행에서 `kymd/khms`의 한국 시각과 일치했다. 시각 불일치0, 중복0, 비정상 OHLCV0이다.9/29 현지 날짜의 모든 행은 canonical CSV에서 제외했다.
- 최종 CMCSA/KDP/HIVE canonical5분봉은 각각686/476/695행이다.9/22 일부 버퍼 및 시간외 봉을 포함한다.9/23·24·25·28의09:30~15:55 예정312슬롯은 각 종목 결측0이다. 미거래 구간 전체 또는 시간외 모든 슬롯의 완전성을 뜻하지 않는다.
- 봉 라벨이 시작 시각인지 종료 시각인지 공식적으로 확정하지 못했다. 비교에서는 최소 다음 라벨 이후 이용하는 보수적 지연을 적용해야 한다. 5분 OHLC만으로 지정가 체결 순서·호가 스프레드·부분 체결을 정확히 재현할 수 없다.

최종 기간·결측·해시·요청 횟수는 [kis-acquisition-final.json](kis-acquisition-final.json)에 있다. 첫 수집 결과 [kis-acquisition.json](kis-acquisition.json)도 보존했다. 첫 분봉 수집의 일자 기준 중단은9/23 개장 전까지 도달하지 못해, 최종 수집에서 **9/23 09:30 이전**까지 한 페이지씩 더 확보했다. 두 결과를 서로 독립 표본으로 합산하지 않는다.

## 격리와 요청 계약

`research_readonly_contract.py`는 정확한 경로·HTTP method·TR_ID·파라미터 키·값을 허용 목록으로 검사한다. `research_readonly.py`는 다시 검사한 뒤 고정 TLS 호스트 `openapi.koreainvestment.com:9443`에만 접속한다. 프록시나 리디렉션 따라가기가 없고,3xx는 즉시 거부한다. POST는 `/oauth2/tokenP`의 client_credentials 인증만 가능하다. 주문·취소·hashkey·미등록 경로는 네트워크 전에 거부된다.

GET는 일봉 `HHDFS76240000`, 주문체결조회 `TTTS3035R`, 분봉 `HHDFS76950200` 세 경로뿐이다. 심볼·거래소도 사전 목록으로 고정했다. 인증은 실행당1회, GET 재시도 최대1회, 요청 간 최소0.6초, 연결 timeout15초, 응답8MB 상한이다. 과거조회는 월당10페이지·일봉종목당20페이지·분봉종목당10페이지로 제한한다. 토큰은 메모리에만 유지하며 기존 인증 캐시는 읽거나 수정하지 않는다.

자격증명 출처는 `gui_launcher.py:116`의 우선순위와 같다: process environment → LocalAppData/NasdaqAutoTrader/.env → EXE 인접.env → EXE 상위.env → 인접 config.kis.json의 kis 값. 소스 루트.env로 임의 대체하지 않았다. 정상 조회에 인증 POST가 필요한 것과 주문 POST는 별개다.

CLI는 애플리케이션 `__init__`을 우회하여 engine/brokers/config를 import하지 않는다. 메타데이터 출력은 이 감사 문서 폴더의 **새 JSON 파일**만 허용하며 기존 파일 덮어쓰기나 외부 경로를 인증 전에 거부한다. `--collect`가 없으면 자격증명 존재 여부만 검사한다.

실제 요청 횟수:

|실행|인증POST|일봉GET|내역GET|분봉GET|주문|취소|
|---|---:|---:|---:|---:|---:|---:|
|첫 수집|1|24|3|13|0|0|
|보완 수집|1|24|6|16|0|0|
|전체 실제 네트워크 요청|2|48|9|29|0|0|

## 실행 명령과 파일

실제로 실행한 수집 명령은 다음과 같다. 출력 파일은 이미 존재하므로 재실행 시 새 이름이 필요하다.

```text
python scripts/collect_entry_policy_data.py --collect --summary docs/entry-policy-audit-20260929/kis-acquisition.json
python scripts/collect_entry_policy_data.py --collect --summary docs/entry-policy-audit-20260929/kis-acquisition-final.json
```

현재 구현 파일은 `research_readonly.py`(인증·전송), `_contract.py`(요청 허용 계약·타입), `_credentials.py`(기존 인증 읽기·외부 저장소), `_collect.py`(내역·일봉 수집), `_history.py`(비공개 체결 집계), `_minute.py`(분봉 수집·정규화), `scripts/collect_entry_policy_data.py`(일회성 진입점)다. 모든 파일은 이번에 추가했으며 기존 운영 브로커·GUI·EXE는 수정하지 않았다.

격리 회귀 명령:

```text
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_research_readonly*.py
uvx --offline ruff check nasdaq_auto_trader/research_readonly*.py scripts/collect_entry_policy_data.py tests/test_research_readonly*.py
python -m py_compile nasdaq_auto_trader/research_readonly*.py
```

최종28개 회귀가 한 실행에서 통과했다(2.87초). 이전21/26/27회 결과를 더하지 않는다. 프로젝트 설정 전체 Ruff 검사 오류0, py_compile 종료0. 재수출 이름은 명시적 `__all__`로 유지하고 일봉 커서는 날짜 타입, 분봉 커서는 미국 현지 시간대로 명시했다. 차단 경로·TR_ID/값 변조·리디렉션·상한 재시도·비밀정보 없는 실패·대기 주문·부분 체결·평균단가 연결·시각 변환·데이터 수집에서 주문0·독립 CLI import 격리·출력 덮어쓰기 방지를 포함한다. 실제 자료 수집도 CLI로 직접 실행하여 인증·분할 조회·파일 생성을 확인했다.

최종 보안 검토에서 `.env` 한 파일 안의 중복 키 처리 차이를 발견했다. 기존 GUI처럼 파일 내부에서는 마지막 값, 파일 간에는 먼저 읽은 파일·프로세스 환경 우선이 되도록 교정했다. 가짜 자격증명 회귀는 수정 전1개 실패에서 수정 후 통과했다. 실제 선택 대상 파일에 해당 자격증명 키의 중복이 있는지만 확인한 결과 **없음**이었다. 키나 값은 출력하지 않았으며 이미 수집한 자료의 자격증명 선택에는 영향이 없다. 추가 네트워크 조회는 하지 않았다.

캐시에 있는 일회성 `uvx --offline basedpyright --outputjson`으로 위7개 구현 파일을 검사한 결과 오류0·경고41개다. LSP 설치나 기존 프로젝트의 타입 설정 변경은 하지 않았다. JSON/argparse 경계의 동적 타입 등 경고는 남아 있으며 전체 strict-clean이라고 보고하지 않는다. 세부 결과는 [research-types.json](research-types.json)이다.

## 공식 계약 참고

로컬 구현을 먼저 읽었고 외부 코드를 운영 경로에 복원하지 않았다. 공식 KIS 자료는 읽기 엔드포인트 계약 확인에만 사용했다: [주문체결조회](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_ccnl/inquire_ccnl.py), [일봉](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/dailyprice/dailyprice.py), [분봉](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_time_itemchartprice/inquire_time_itemchartprice.py).2026-09-29 확인. API가 미래의 모든 기간을 계속 제공한다는 보장은 아니다.
