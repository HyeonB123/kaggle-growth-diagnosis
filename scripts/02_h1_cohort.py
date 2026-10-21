"""가설1(유입 질) 검증용: 두 시기 신규 가입자 전원의 첫 활동 시점을 data/processed/h1_cohort.parquet로 저장한다.

대상: 황금기 2020-Q1 ~ Q4, 침체기 2024-Q3 ~ 2025-Q2 가입자 전원 (약 798만 명)
컬럼 (가입일로부터 며칠 뒤 처음 했는지, 안 했으면 결측)
- first_qau      : 참여·창작 활동 (QAU 정의)
- first_creator  : 창작 활동 (노트북 버전·공개, 제출, 포럼 글, 데이터셋·모델 버전, 태스크)
- first_team     : 팀 합류 (대회 참가)
- first_light    : 가벼운 활동 (투표 3종, 팔로우, 반응)
- country        : 프로필 국가 (빈 값 → 결측)

대안 설명(대회 공급 감소) 확인용으로 두 시기에 열린 대회 목록도 h1_competitions.parquet로 저장한다.

01_activity_series.py가 만든 qau_user_days가 필요하다.
RAM 8GB라 50만 행씩 받아 parquet에 이어 쓴다.

사용: python scripts/02_h1_cohort.py   (프로젝트 루트에서 실행, .env 필요)
"""
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from metakaggle.config import GOLDEN, PERIOD_SPLIT, ROOT, STAGNATION, processed  # noqa: E402
from metakaggle.db import get_engine  # noqa: E402

LIGHT = [
    ("UserFollowers", "UserId", "CreationDate"),
    ("ModelVotes", "UserId", "VoteDate"),
    ("DatasetVotes", "UserId", "VoteDate"),
    ("ForumMessageVotes", "FromUserId", "VoteDate"),
    ("ForumMessageReactions", "FromUserId", "ReactionDate"),
]

BUILD = [
    "drop table if exists h1_users",
    f"""create table h1_users as
        select Id as UserId, date(RegisterDate) as reg, nullif(trim(Country), '') as country,
               case when RegisterDate < '{PERIOD_SPLIT}' then 'Golden' else 'Stagnation' end as period
        from Users
        where (RegisterDate >= '{GOLDEN[0]}' and RegisterDate < '{GOLDEN[1]}')
           or (RegisterDate >= '{STAGNATION[0]}' and RegisterDate < '{STAGNATION[1]}')""",
    "alter table h1_users add primary key (UserId)",
    "drop table if exists h1_first_kind",
    """create table h1_first_kind as
        select q.UserId,
               min(case when q.kind = 'creator' then q.d end) as first_creator,
               min(case when q.kind = 'team' then q.d end) as first_team
        from qau_user_days q join h1_users u on u.UserId = q.UserId
        group by q.UserId""",
    "alter table h1_first_kind add primary key (UserId)",
    "drop table if exists h1_first_light",
    "create table h1_first_light as select UserId, min(d) as first_light from (\n"
    + "\nunion all\n".join(
        f"select l.{u} as UserId, min(date(l.{d})) as d from {t} l join h1_users h on h.UserId = l.{u} group by l.{u}"
        for t, u, d in LIGHT)
    + "\n) x group by UserId",
    "alter table h1_first_light add primary key (UserId)",
]

QUERY = """
select u.UserId, u.period, u.reg, u.country,
       datediff(least(coalesce(k.first_creator, '9999-12-31'), coalesce(k.first_team, '9999-12-31')), u.reg) as first_qau,
       datediff(k.first_creator, u.reg) as first_creator,
       datediff(k.first_team, u.reg) as first_team,
       datediff(l.first_light, u.reg) as first_light
from h1_users u
left join h1_first_kind k on k.UserId = u.UserId
left join h1_first_light l on l.UserId = u.UserId
"""

SCHEMA = pa.schema([
    ("UserId", pa.int64()), ("period", pa.string()), ("reg", pa.date32()), ("country", pa.string()),
    ("first_qau", pa.float32()), ("first_creator", pa.float32()), ("first_team", pa.float32()), ("first_light", pa.float32()),
])

COMPETITIONS = f"""
select Id, HostSegmentTitle as segment, date(EnabledDate) as enabled, RewardType as reward_type,
       RewardQuantity as reward, TotalTeams as total_teams,
       case when EnabledDate < '{PERIOD_SPLIT}' then 'Golden' else 'Stagnation' end as period
from Competitions
where (EnabledDate >= '{GOLDEN[0]}' and EnabledDate < '{GOLDEN[1]}')
   or (EnabledDate >= '{STAGNATION[0]}' and EnabledDate < '{STAGNATION[1]}')
"""


def save_competitions(engine) -> None:
    comp = pd.read_sql(text(COMPETITIONS), engine)
    out = processed("h1_competitions")
    comp.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(comp):,}행")


def main() -> None:
    t0 = time.time()
    engine = get_engine()
    with engine.begin() as conn:
        for sql in BUILD:
            conn.execute(text(sql))
            print(f"  {sql.split(chr(10))[0][:60]} ({time.time() - t0:.0f}초)", flush=True)

    out = processed("h1_cohort")
    out.unlink(missing_ok=True)
    n = 0
    with engine.connect().execution_options(stream_results=True) as conn, \
            pq.ParquetWriter(out, SCHEMA, compression="zstd") as writer:
        for chunk in pd.read_sql(text(QUERY), conn, chunksize=500_000):
            # 활동이 전혀 없으면 least(9999-12-31) → 결측으로
            chunk.loc[chunk.first_qau > 100_000, "first_qau"] = None
            chunk["reg"] = pd.to_datetime(chunk.reg).dt.date
            writer.write_table(pa.Table.from_pandas(chunk.astype({c: "float32" for c in SCHEMA.names[4:]}),
                                                    schema=SCHEMA, preserve_index=False))
            n += len(chunk)
    df = pd.read_parquet(out, columns=["period", "first_qau"])
    print(f"{out.relative_to(ROOT)}: {n:,}행 ({time.time() - t0:.0f}초)")
    rate = df.assign(act=df.first_qau <= 90).groupby("period").act.mean()
    print(rate)
    # 검증: 01 노트북의 90일 활성화율과 같아야 한다 (12.71% / 3.61%)
    assert len(df) == 7_985_565
    assert abs(rate["Golden"] - 0.1271) < 0.0005 and abs(rate["Stagnation"] - 0.0361) < 0.0005
    print("검증 통과")
    save_competitions(engine)


if __name__ == "__main__":
    main()
