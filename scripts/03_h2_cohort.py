"""가설2(활성화 병목) 검증용: 두 시기 가입자의 첫 비-D 참여 시점, 첫 D 시점, 초기 노트북 강도를 data/processed/h2_cohort.parquet로 저장한다.

D 활동 (핵심 창작): 노트북 공개, 대회 제출(팀원 전원에게 전파), 포럼 글, 데이터셋 버전·태스크·태스크 제출, 모델 버전
비-D 참여: 팀 합류(대회 참가), 노트북 버전 작성(비공개 포함)

컬럼 (가입일로부터 며칠 뒤 처음 했는지, 안 했으면 결측)
- first_team, first_kv : 첫 팀 합류, 첫 노트북 버전
- first_d              : 첫 D 활동
- max_lines_90d        : 가입 후 90일 안에 만든 노트북별 마지막 버전 줄 수의 최댓값
- max_versions_90d     : 가입 후 90일 안에 만든 노트북별 버전 수의 최댓값

02_h1_cohort.py가 만든 h1_users가 필요하다.

사용: python scripts/03_h2_cohort.py   (프로젝트 루트에서 실행, .env 필요)
"""
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from metakaggle.config import ROOT, processed  # noqa: E402
from metakaggle.db import get_engine  # noqa: E402

BUILD = [
    # 첫 D 활동: 종류별 최솟값을 모아 다시 최솟값
    "drop table if exists h2_first_d",
    """create table h2_first_d as
    select UserId, min(d) as first_d from (
        select k.AuthorUserId as UserId, min(date(k.MadePublicDate)) as d
            from Kernels k join h1_users h on h.UserId = k.AuthorUserId where k.MadePublicDate is not null group by k.AuthorUserId
        union all
        select tm.UserId, min(s.d) from TeamMemberships tm
            join h1_users h on h.UserId = tm.UserId
            join (select TeamId, min(date(SubmissionDate)) as d from Submissions group by TeamId) s on s.TeamId = tm.TeamId
            group by tm.UserId
        union all
        select f.PostUserId, min(date(f.PostDate)) from ForumMessages f join h1_users h on h.UserId = f.PostUserId group by f.PostUserId
        union all
        select v.CreatorUserId, min(date(v.CreationDate)) from DatasetVersions v join h1_users h on h.UserId = v.CreatorUserId group by v.CreatorUserId
        union all
        select t.OwnerUserId, min(date(t.CreationDate)) from DatasetTasks t join h1_users h on h.UserId = t.OwnerUserId group by t.OwnerUserId
        union all
        select t.SubmittedUserId, min(date(t.CreationDate)) from DatasetTaskSubmissions t join h1_users h on h.UserId = t.SubmittedUserId group by t.SubmittedUserId
        union all
        select m.CreatorUserId, min(date(m.CreationDate)) from ModelVersions m join h1_users h on h.UserId = m.CreatorUserId group by m.CreatorUserId
    ) x group by UserId""",
    "alter table h2_first_d add primary key (UserId)",
    # 가입 후 90일 안의 노트북 버전 (노트북 강도 계산용)
    "drop table if exists h2_kv_90d",
    """create table h2_kv_90d as
    select kv.AuthorUserId as UserId, kv.ScriptId, kv.CreationDate, kv.TotalLines
    from KernelVersions kv join h1_users h on h.UserId = kv.AuthorUserId
    where kv.CreationDate < date_add(h.reg, interval 91 day)""",
    "alter table h2_kv_90d add index idx_h2kv (UserId, ScriptId, CreationDate)",
    "drop table if exists h2_kernel_stats",
    """create table h2_kernel_stats as
    select UserId, min(date(first_v)) as first_kv, max(final_lines) as max_lines_90d, max(n_versions) as max_versions_90d
    from (
        select UserId, ScriptId, min(CreationDate) as first_v, count(*) as n_versions,
               substring_index(group_concat(coalesce(TotalLines, 0) order by CreationDate desc), ',', 1) + 0 as final_lines
        from h2_kv_90d group by UserId, ScriptId
    ) s group by UserId""",
    "alter table h2_kernel_stats add primary key (UserId)",
]

# 첫 노트북 버전은 90일 밖까지 필요 없으므로 h2_kernel_stats(90일 안)에서 가져온다
QUERY = """
select u.UserId, u.period, u.reg,
       datediff(k.first_team, u.reg) as first_team,
       datediff(s.first_kv, u.reg) as first_kv,
       datediff(d.first_d, u.reg) as first_d,
       s.max_lines_90d, s.max_versions_90d
from h1_users u
left join h1_first_kind k on k.UserId = u.UserId
left join h2_kernel_stats s on s.UserId = u.UserId
left join h2_first_d d on d.UserId = u.UserId
where k.first_team is not null or s.first_kv is not null or d.first_d is not null
"""


def main() -> None:
    t0 = time.time()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("set session group_concat_max_len = 1000000"))
        for sql in BUILD:
            conn.execute(text(sql))
            print(f"  {sql.split(chr(10))[0][:60]} ({time.time() - t0:.0f}초)", flush=True)

    df = pd.read_sql(text(QUERY), engine)
    out = processed("h2_cohort")
    df.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(df):,}행 ({time.time() - t0:.0f}초)")
    print(df.groupby("period").size())


if __name__ == "__main__":
    main()
