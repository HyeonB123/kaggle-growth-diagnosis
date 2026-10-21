"""프로세스 마이닝용 이벤트 로그: 두 시기 가입자의 가입 후 90일 활동을 data/processed/event_log.parquet로 저장한다.

케이스 = 유저, 이벤트 = 활동 종류별 **첫** 발생일 (같은 활동의 반복은 경로를 복잡하게 만들 뿐이라 첫 번째만 남긴다)

| 활동 | 원천 |
|---|---|
| 가벼운 활동 | 투표 3종, 팔로우, 반응 |
| 대회 참가 | 팀 합류 (TeamMemberships) |
| 노트북 작성 | 노트북 버전 (비공개 포함) |
| 대회 제출 | 팀 제출 (팀원 전원에게 전파) |
| 노트북 공개 | Kernels.MadePublicDate |
| 포럼 글 | ForumMessages |
| 데이터셋 | 데이터셋 버전·태스크·태스크 제출 |
| 모델 | 모델 버전 |

가입 후 90일(D+0 ~ D+90) 안의 활동만, 활동이 하나라도 있는 유저만 저장한다 (가입자 수는 h1_cohort로 확인).
02_h1_cohort.py가 만든 h1_users가 필요하다.

사용: python scripts/04_event_log.py   (프로젝트 루트에서 실행, .env 필요)
"""
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from metakaggle.config import ROOT, processed  # noqa: E402
from metakaggle.db import get_engine  # noqa: E402

# (활동, 원천 쿼리: UserId, d 반환)
SOURCES = {
    "가벼운 활동": [("UserFollowers", "UserId", "CreationDate"), ("ModelVotes", "UserId", "VoteDate"),
                ("DatasetVotes", "UserId", "VoteDate"), ("ForumMessageVotes", "FromUserId", "VoteDate"),
                ("ForumMessageReactions", "FromUserId", "ReactionDate")],
    "대회 참가": [("TeamMemberships", "UserId", "RequestDate")],
    "노트북 작성": [("KernelVersions", "AuthorUserId", "CreationDate")],
    "노트북 공개": [("Kernels", "AuthorUserId", "MadePublicDate")],
    "포럼 글": [("ForumMessages", "PostUserId", "PostDate")],
    "데이터셋": [("DatasetVersions", "CreatorUserId", "CreationDate"), ("DatasetTasks", "OwnerUserId", "CreationDate"),
              ("DatasetTaskSubmissions", "SubmittedUserId", "CreationDate")],
    "모델": [("ModelVersions", "CreatorUserId", "CreationDate")],
}

SUBMISSION = """
select tm.UserId, min(s.d) as d
from TeamMemberships tm
join h1_users h on h.UserId = tm.UserId
join (select TeamId, date(SubmissionDate) as d from Submissions) s on s.TeamId = tm.TeamId
where s.d between h.reg and date_add(h.reg, interval 90 day)
group by tm.UserId
"""


def first_dates(table: str, user: str, date: str) -> str:
    return (f"select x.{user} as UserId, min(date(x.{date})) as d from {table} x "
            f"join h1_users h on h.UserId = x.{user} "
            f"where x.{date} >= h.reg and x.{date} < date_add(h.reg, interval 91 day) group by x.{user}")


def main() -> None:
    t0 = time.time()
    engine = get_engine()
    parts = []
    for activity, sources in SOURCES.items():
        q = "select UserId, min(d) as d from (" + " union all ".join(first_dates(*s) for s in sources) + ") y group by UserId"
        df = pd.read_sql(text(q), engine).assign(activity=activity)
        parts.append(df)
        print(f"  {activity}: {len(df):,}명 ({time.time() - t0:.0f}초)", flush=True)
    sub = pd.read_sql(text(SUBMISSION), engine).assign(activity="대회 제출")
    parts.append(sub)
    print(f"  대회 제출: {len(sub):,}명 ({time.time() - t0:.0f}초)", flush=True)

    users = pd.read_sql(text("select UserId, period, reg from h1_users"), engine)
    log = pd.concat(parts).merge(users, on="UserId")
    log["day"] = (pd.to_datetime(log.d) - pd.to_datetime(log.reg)).dt.days.astype("int16")
    log = log[["UserId", "period", "activity", "day"]].sort_values(["UserId", "day"])
    out = processed("event_log")
    log.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(log):,}행, 유저 {log.UserId.nunique():,}명 ({time.time() - t0:.0f}초)")
    print(log.groupby(["period", "activity"]).UserId.nunique().unstack(0))


if __name__ == "__main__":
    main()
