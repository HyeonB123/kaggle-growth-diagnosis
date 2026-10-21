"""MySQL 접속. 접속 정보는 프로젝트 루트의 .env에서 읽는다 (.env.example 참고)."""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import ROOT


def get_engine() -> Engine:
    """DB_NAME이 비어 있으면 Meta Kaggle 테이블(Users, TeamMemberships)이 있는 스키마를 찾아 쓴다."""
    load_dotenv(ROOT / ".env")
    base = (f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
            f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}")
    db_name = os.getenv("DB_NAME")
    if not db_name:
        with create_engine(base).connect() as conn:
            db_name = conn.execute(text(
                "select TABLE_SCHEMA from information_schema.TABLES "
                "where TABLE_NAME in ('Users', 'TeamMemberships') "
                "group by TABLE_SCHEMA having count(*) = 2 limit 1")).scalar()
        if db_name is None:
            raise RuntimeError("Meta Kaggle 테이블이 있는 스키마를 찾지 못함. .env에 DB_NAME을 적을 것")
    return create_engine(f"{base}/{db_name}")
