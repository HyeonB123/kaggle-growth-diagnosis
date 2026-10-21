"""경로와 프로젝트 전반에서 쓰는 상수.

숫자 하나를 바꿀 때 여러 파일을 고치지 않도록 여기에 모은다.
각 값의 근거는 docs/decisions.md 참고.
"""
from pathlib import Path

# ── 경로 ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]          # 프로젝트 루트
PROCESSED_DIR = ROOT / "data" / "processed"         # MySQL에서 뽑아 저장한 분석용 파일


def processed(name: str) -> Path:
    """data/processed/{name}.parquet 경로."""
    return PROCESSED_DIR / f"{name}.parquet"


# ── 코호트 (4분기 통일 확정) ────────────────────────────
GOLDEN = ("2020-01-01", "2021-01-01")       # 황금기 2020-Q1 ~ Q4 (끝 날짜 미포함)
STAGNATION = ("2024-07-01", "2025-07-01")   # 침체기 2024-Q3 ~ 2025-Q2
PERIOD_SPLIT = "2022-01-01"                 # RegisterDate < 이 날짜면 Golden
OBS_DAYS = 90                               # 가입 후 관찰 기간 (D+0 ~ D+90)

# ── ML 타깃 ──────────────────────────────────────────
PRED_DAY = 14                   # 예측 시점 D+14 (주간 사이클 2회)
TEST_START = "2025-07"          # 이 가입 월부터 테스트 (마지막에 한 번만 평가)
SEED = 42
