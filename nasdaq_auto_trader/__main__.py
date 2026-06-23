"""python -m nasdaq_auto_trader 실행을 CLI로 연결한다."""

from .cli import main


# 모듈 실행 시 명령줄 입구를 호출한다.
if __name__ == "__main__":
    raise SystemExit(main())
