# NASDAQ Auto Trader

나스닥 종목을 대상으로 유명 기술 지표를 기계적으로 계산해서 `buy`, `sell`, `hold` 판단을 내리는 자동매매 도구다. 기본값은 실제 주문이 나가지 않는 `dry_run`이고, 실전 주문은 `live`와 `allow_live_trading=true`를 같이 켜야만 가능하다.

## 하는 일

- SMA, EMA, RSI, MACD, Bollinger Bands 계산
- 지표 점수를 합쳐 매수/매도 판단
- 손절, 익절, 종목당 최대 투자 비율 제한
- CSV 백테스트
- Alpaca paper/live 주문 연결

## 필요한 API

Alpaca 계정에서 아래 두 값을 가져오면 된다.

```powershell
$env:ALPACA_API_KEY="발급받은_key"
$env:ALPACA_SECRET_KEY="발급받은_secret"
```

기본 시세 feed는 무료 계정에서 쓰기 쉬운 `iex`로 잡아뒀다. 설정 파일의 `alpaca.feed`를 바꾸면 다른 feed도 쓸 수 있다.

## 설정 확인

```powershell
python -m nasdaq_auto_trader --config config.example.json show-config
```

## 백테스트

CSV는 아래 컬럼을 가져야 한다.

```csv
symbol,timestamp,open,high,low,close,volume
QQQ,2026-01-01,100,101,99,100,1000000
```

실행:

```powershell
python -m nasdaq_auto_trader --config config.example.json backtest --csv path\to\bars.csv --cash 10000
```

## 한 번 실행

`dry_run`은 주문을 실제로 보내지 않고 주문 모양만 기록한다. 다만 최신 시세를 가져오려면 Alpaca 키가 필요하다.

```powershell
python -m nasdaq_auto_trader --config config.example.json once --mode dry_run
```

paper 주문:

```powershell
python -m nasdaq_auto_trader --config config.example.json once --mode paper
```

## 계속 자동 실행

1시간마다 한 번씩 판단하게 할 수 있다.

```powershell
python -m nasdaq_auto_trader --config config.example.json loop --mode paper --interval-minutes 60
```

처음 시험할 때는 한 번만 돌게 제한할 수 있다.

```powershell
python -m nasdaq_auto_trader --config config.example.json loop --mode dry_run --interval-minutes 1 --max-runs 1
```

## live 모드 안전장치

실전 주문은 설정 파일에서 둘 다 켜야 한다.

```json
{
  "mode": "live",
  "allow_live_trading": true
}
```

이 도구는 투자 조언이 아니라 자동 실행 도구다. 먼저 백테스트와 paper 거래로 충분히 확인하고 써야 한다.
