"""문제 정의(notebooks/01)에 쓰는 활성 유저 시계열을 data/processed에 저장한다.

QAU 활동 = 참여·창작 활동 (투표·팔로우·반응 같은 가벼운 활동은 제외)
- 참여: 팀 합류(TeamMemberships, 대회 참가 시 생성)
- 창작: 노트북 버전 작성, 노트북 공개, 대회 제출, 포럼 글, 데이터셋·모델 버전, 데이터셋 태스크·태스크 제출

MySQL에 유저-활동일 테이블(qau_user_days)을 만든 뒤 집계한다.

저장 결과
- quarterly_series.parquet : 2016-Q1 ~ 2025-Q4 분기별 신규 가입자, QAU(창작 / 팀 합류만), 가입 코호트의 90일 활성화 인원
- monthly_series.parquet   : 2020-01 ~ 2025-12 월별 신규 가입자, MAU(창작 / 팀 합류만)
- qau_activity_gaps.parquet: 2023 ~ 2024 활동일마다 다음 활동일까지 간격 (일, 없으면 결측)
- qau_by_tenure.parquet    : 2017-Q1 ~ 2025-Q4 분기 QAU를 가입 후 경과 기간(그 분기 첫 활동일 기준)으로 나눈 인원

사용: python scripts/01_activity_series.py   (프로젝트 루트에서 실행, .env 필요, 약 10분)
"""
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from metakaggle.config import ROOT, processed  # noqa: E402
from metakaggle.db import get_engine  # noqa: E402

START = "2016-01-01"
END = "2026-01-01"          # 데이터 마지막 날 2026-03-27 → 2025-Q4 가입자까지 90일 관찰 가능

# (테이블, 유저 컬럼, 날짜 컬럼, 종류)
SOURCES = [
    ("TeamMemberships", "UserId", "RequestDate", "team"),
    ("KernelVersions", "AuthorUserId", "CreationDate", "creator"),
    ("Kernels", "AuthorUserId", "MadePublicDate", "creator"),
    ("Submissions", "SubmittedUserId", "SubmissionDate", "creator"),
    ("ForumMessages", "PostUserId", "PostDate", "creator"),
    ("DatasetVersions", "CreatorUserId", "CreationDate", "creator"),
    ("ModelVersions", "CreatorUserId", "CreationDate", "creator"),
    ("DatasetTasks", "OwnerUserId", "CreationDate", "creator"),
    ("DatasetTaskSubmissions", "SubmittedUserId", "CreationDate", "creator"),
]

BUILD = [
    "drop table if exists qau_user_days",
    "create table qau_user_days as select UserId, d, kind from (\n"
    + "\nunion\n".join(
        f"select {u} as UserId, date({d}) as d, '{k}' as kind from {t} "
        f"where {d} >= '{START}' and {u} is not null" for t, u, d, k in SOURCES)
    + "\n) x",
    "alter table qau_user_days add index idx_qud_user (UserId, d), add index idx_qud_d (d)",
    "drop table if exists qau_user_first",
    "create table qau_user_first as select UserId, min(d) as first_d from qau_user_days group by UserId",
    "alter table qau_user_first add primary key (UserId)",
]

QUARTERLY = f"""
with act as (
    select concat(year(d), '-Q', quarter(d)) as q, UserId, max(kind = 'creator') as is_creator
    from qau_user_days where d < '{END}' group by q, UserId
),
qau as (
    select q, count(*) as qau, sum(is_creator) as qau_creators from act group by q
),
cohort as (
    select concat(year(u.RegisterDate), '-Q', quarter(u.RegisterDate)) as q,
           count(*) as new_users,
           sum(f.first_d <= date_add(u.RegisterDate, interval 90 day)) as activated_90d
    from Users u left join qau_user_first f on f.UserId = u.Id
    where u.RegisterDate >= '{START}' and u.RegisterDate < '{END}'
    group by q
)
select c.q, c.new_users, c.activated_90d, a.qau, a.qau_creators, a.qau - a.qau_creators as qau_team_only
from cohort c join qau a on a.q = c.q order by c.q
"""

MONTHLY = f"""
with act as (
    select date_format(d, '%Y-%m') as ym, UserId, max(kind = 'creator') as is_creator
    from qau_user_days where d >= '2020-01-01' and d < '{END}' group by ym, UserId
),
mau as (select ym, count(*) as mau, sum(is_creator) as mau_creators from act group by ym),
new as (
    select date_format(RegisterDate, '%Y-%m') as ym, count(*) as new_users from Users
    where RegisterDate >= '2020-01-01' and RegisterDate < '{END}' group by ym
)
select n.ym, n.new_users, m.mau, m.mau_creators, m.mau - m.mau_creators as mau_team_only
from new n join mau m on m.ym = n.ym order by n.ym
"""

# 기준 활동일 2023 ~ 2024: 데이터 끝(2026-03-27)까지 15개월 이상 추적 가능
GAPS = """
with days as (select distinct UserId, d from qau_user_days),
g as (select UserId, d, datediff(lead(d) over (partition by UserId order by d), d) as gap from days)
select UserId, d, gap from g where d between '2023-01-01' and '2024-12-31'
"""

# 가입 연차: 그 분기 첫 활동일 - 가입일. Users에 없는 유저 ID(약 2.6%)는 조인에서 빠진다
TENURE = f"""
with act as (
    select concat(year(d), '-Q', quarter(d)) as q, min(d) as qd, UserId
    from qau_user_days where d >= '2017-01-01' and d < '{END}' group by q, UserId
)
select a.q,
    sum(datediff(a.qd, u.RegisterDate) <= 90) as tenure_90d,
    sum(datediff(a.qd, u.RegisterDate) between 91 and 365) as tenure_1y,
    sum(datediff(a.qd, u.RegisterDate) between 366 and 1095) as tenure_1_3y,
    sum(datediff(a.qd, u.RegisterDate) > 1095) as tenure_3y_plus,
    count(*) as qau
from act a join Users u on u.Id = a.UserId
group by a.q order by a.q
"""


def main() -> None:
    t0 = time.time()
    engine = get_engine()
    with engine.begin() as conn:
        for sql in BUILD:
            conn.execute(text(sql))
            print(f"  {sql.split(chr(10))[0][:60]} ({time.time() - t0:.0f}초)", flush=True)

    for name, query in [("quarterly_series", QUARTERLY), ("monthly_series", MONTHLY), ("qau_activity_gaps", GAPS),
                        ("qau_by_tenure", TENURE)]:
        df = pd.read_sql(text(query), engine)
        out = processed(name)
        df.to_parquet(out, index=False)
        print(f"{out.relative_to(ROOT)}: {len(df):,}행 ({time.time() - t0:.0f}초)", flush=True)

    # 검증: 구성요소 합 = QAU, 창작 ≤ QAU
    q = pd.read_parquet(processed("quarterly_series"))
    m = pd.read_parquet(processed("monthly_series"))
    assert (q.qau_creators + q.qau_team_only == q.qau).all() and (q.qau_creators <= q.qau).all()
    assert (m.mau_creators <= m.mau).all()
    assert len(q) == 40 and len(m) == 72, (len(q), len(m))
    print("검증 통과")


if __name__ == "__main__":
    main()
