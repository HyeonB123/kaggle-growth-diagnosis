"""예측 모델(Early QAU Predictor) 학습 데이터: data/processed/ml_dataset.parquet

예측 시점 D+14, 정답 = D+15 ~ D+90에 D 활동(핵심 창작) 발생 여부
대상 = D+14까지 비-D 활동(가벼운 활동, 대회 참가, 노트북 작성)이 있고 D 활동은 없는 유저
가입 코호트 = 황금기 2020 (비교용) + 2024-07 ~ 2025-09 (학습·검증·테스트, 시간 순 분할)

- 모든 피처는 날짜 단위로 가입일(D+0) ~ D+14 당일까지만 쓴다 (시각이 있는 활동도 날짜로 잘라 경계를 통일)
- 팀 크기는 D+14 당일까지 합류한 팀원만 센다 (이후 합류자는 미래 정보)
- Users.Country, PerformanceTier는 현재 시점 값이라 쓰지 않는다
- 노트북 작성자(D+14까지 노트북 버전 작성)는 segment = 'notebook'으로 표시만 하고 저장한다. 모델은 나머지(segment = 'model')로 학습한다

사용: python scripts/05_ml_dataset.py [--skip-build]   (프로젝트 루트에서 실행, .env 필요)
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from metakaggle.config import PRED_DAY, ROOT, processed  # noqa: E402
from metakaggle.db import get_engine  # noqa: E402

# (종류, 테이블, 유저 컬럼, 날짜 컬럼)
SOURCES = [
    ("follow", "UserFollowers", "UserId", "CreationDate"),
    ("followed_by", "UserFollowers", "FollowingUserId", "CreationDate"),
    ("vote_model", "ModelVotes", "UserId", "VoteDate"),
    ("vote_dataset", "DatasetVotes", "UserId", "VoteDate"),
    ("vote_forum", "ForumMessageVotes", "FromUserId", "VoteDate"),
    ("reaction", "ForumMessageReactions", "FromUserId", "ReactionDate"),
    ("team", "TeamMemberships", "UserId", "RequestDate"),
    ("kernel_version", "KernelVersions", "AuthorUserId", "CreationDate"),
    ("kernel_public", "Kernels", "AuthorUserId", "MadePublicDate"),
    ("forum_post", "ForumMessages", "PostUserId", "PostDate"),
    ("dataset", "DatasetVersions", "CreatorUserId", "CreationDate"),
    ("dataset", "DatasetTasks", "OwnerUserId", "CreationDate"),
    ("dataset", "DatasetTaskSubmissions", "SubmittedUserId", "CreationDate"),
    ("model", "ModelVersions", "CreatorUserId", "CreationDate"),
]
LIGHT = ["follow", "vote_model", "vote_dataset", "vote_forum", "reaction"]
D_TYPES = ["kernel_public", "submission", "forum_post", "dataset", "model"]

BUILD = [
    "drop table if exists ml_users",
    """create table ml_users as
       select Id as UserId, date(RegisterDate) as reg,
              case when RegisterDate < '2022-01-01' then 'Golden' else 'Stagnation' end as period
       from Users
       where (RegisterDate >= '2020-01-01' and RegisterDate < '2021-01-01')
          or (RegisterDate >= '2024-07-01' and RegisterDate < '2025-10-01')""",
    "alter table ml_users add primary key (UserId)",
    "drop table if exists ml_events",
    "create table ml_events as select UserId, day, type, sum(n) as n from (\n"
    + "\nunion all\n".join(
        f"select x.{u} as UserId, datediff(date(x.{d}), u.reg) as day, '{k}' as type, count(*) as n "
        f"from {t} x join ml_users u on u.UserId = x.{u} "
        f"where x.{d} >= u.reg and x.{d} < date_add(u.reg, interval 91 day) group by x.{u}, day"
        for k, t, u, d in SOURCES)
    + """
       union all
       select tm.UserId, datediff(s.d, u.reg) as day, 'submission' as type, count(*) as n
       from TeamMemberships tm
       join ml_users u on u.UserId = tm.UserId
       join (select distinct TeamId, date(SubmissionDate) as d from Submissions) s on s.TeamId = tm.TeamId
       where s.d between u.reg and date_add(u.reg, interval 90 day)
       group by tm.UserId, day
    ) x group by UserId, day, type""",
    "alter table ml_events add index idx_mle (UserId)",
]

# 대회별 날짜별 누적 팀 수 (참가 시점의 대회 인기). 팀 생성일 = 그 팀의 첫 합류일
COMP_BUILD = [
    "drop table if exists ml_comp_daily",
    """create table ml_comp_daily as
       select CompetitionId, d, sum(n) over (partition by CompetitionId order by d) as teams_so_far
       from (select t.CompetitionId, x.d, count(*) as n
             from (select TeamId, date(min(RequestDate)) as d from TeamMemberships
                   where RequestDate is not null group by TeamId) x
             join Teams t on t.Id = x.TeamId where t.CompetitionId is not null
             group by t.CompetitionId, x.d) y""",
    "alter table ml_comp_daily add primary key (CompetitionId, d)",
]

# D+14 당일까지 합류한 팀의 대회 맥락 (모두 참가 시점에 알 수 있는 값)
# 팀 크기는 그 유저의 D+14 시점까지 합류한 팀원만 센다
TEAM_CTX = f"""
select tm.UserId, tm.TeamId, datediff(date(tm.RequestDate), u.reg) as join_day,
       c.HostSegmentTitle as segment, c.RewardType as reward_type, coalesce(c.RewardQuantity, 0) as reward,
       datediff(date(c.DeadlineDate), date(tm.RequestDate)) as days_to_deadline,
       datediff(date(tm.RequestDate), date(c.EnabledDate)) as comp_age,
       c.OnlyAllowKernelSubmissions as kernels_only, c.Slug like 'playground-series%' as playground_series,
       (t.TeamLeaderId <> tm.UserId) as joined_others_team,
       (select max(cd.teams_so_far) from ml_comp_daily cd
         where cd.CompetitionId = c.Id and cd.d <= date(tm.RequestDate)) as comp_teams_at_join,
       (select count(*) from TeamMemberships t2
         where t2.TeamId = tm.TeamId and t2.RequestDate < date_add(u.reg, interval {PRED_DAY + 1} day)) as team_size_d14
from TeamMemberships tm
join ml_users u on u.UserId = tm.UserId
join Teams t on t.Id = tm.TeamId
join Competitions c on c.Id = t.CompetitionId
where tm.RequestDate >= u.reg and tm.RequestDate < date_add(u.reg, interval {PRED_DAY + 1} day)
"""


def build_features(ev: pd.DataFrame, team: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    early = ev[ev.day <= PRED_DAY]
    first_d = ev[ev.type.isin(D_TYPES)].groupby("UserId").day.min()
    nonD_early = early[early.type.isin(LIGHT + ["team", "kernel_version"])]

    df = users.set_index("UserId")
    df["first_d"] = first_d
    df = df[df.index.isin(nonD_early.UserId) & ~(df.first_d <= PRED_DAY)].copy()
    df["y"] = df.first_d.between(PRED_DAY + 1, 90).astype("int8")
    kv = early[early.type == "kernel_version"].UserId.unique()
    df["segment"] = np.where(df.index.isin(kv), "notebook", "model")

    e = early[early.UserId.isin(df.index)]
    cnt = e.pivot_table(index="UserId", columns="type", values="n", aggfunc="sum", fill_value=0)
    for k in LIGHT + ["followed_by", "team", "kernel_version"]:
        df[f"n_{k}"] = cnt.get(k, 0)
    df[[c for c in df.columns if c.startswith("n_")]] = df.filter(like="n_").fillna(0)
    df["n_light"] = df[[f"n_{k}" for k in LIGHT]].sum(axis=1)
    df["n_light_types"] = (df[[f"n_{k}" for k in LIGHT]] > 0).sum(axis=1)

    act = e[e.type != "followed_by"]                      # 본인이 한 활동만
    days = act.groupby("UserId").day
    df["active_days"] = days.nunique()
    df["first_day"] = days.min()
    df["last_day"] = days.max()
    df["recency"] = PRED_DAY - df.last_day
    df["active_d0"] = act[act.day == 0].groupby("UserId").size().gt(0)
    df["active_d1_7"] = act[act.day.between(1, 7)].groupby("UserId").day.nunique()
    df["active_d8_14"] = act[act.day.between(8, 14)].groupby("UserId").day.nunique()
    first_type = act.assign(light=act.type.isin(LIGHT)).sort_values(["UserId", "day", "light"]).groupby("UserId").first()
    df["first_is_team"] = first_type.type.eq("team")
    df["light_only"] = df.n_team.eq(0) & df.n_kernel_version.eq(0)

    t = team[team.UserId.isin(df.index)].sort_values(["UserId", "join_day"])
    tg = t.groupby("UserId")
    df["n_teams"] = tg.size()
    df["max_team_size_d14"] = tg.team_size_d14.max()
    df["first_team_day"] = tg.join_day.min()
    df["min_days_to_deadline"] = tg.days_to_deadline.min()
    df["max_reward"] = tg.reward.max()
    # 마감이 지난 대회 참가 = 대회가 아니라 데이터를 받으려는 참가일 가능성 (규칙 동의 후 다운로드)
    t["closed"] = t.days_to_deadline < 0
    df["n_closed_comps"] = t.groupby("UserId").closed.sum()
    df["n_open_comps"] = t.groupby("UserId").closed.apply(lambda s: (~s).sum())
    df["share_closed_comps"] = df.n_closed_comps / df.n_teams
    df["max_comp_teams_at_join_open"] = t[~t.closed].groupby("UserId").comp_teams_at_join.max()
    df["min_comp_age"] = tg.comp_age.min()
    df["any_kernels_only"] = tg.kernels_only.max()
    df["any_playground_series"] = tg.playground_series.max()
    df["any_joined_others_team"] = tg.joined_others_team.max()
    df["first_reward_usd"] = tg.reward_type.first().eq("USD")
    df["first_reward_knowledge"] = tg.reward_type.first().eq("Knowledge")
    first_seg = tg.segment.first()
    for seg in ["Featured", "Research", "Getting Started", "Playground", "Community"]:
        df[f"comp_{seg.lower().replace(' ', '_')}"] = first_seg.eq(seg)

    df["reg"] = pd.to_datetime(df.reg)
    df["cohort_month"] = df.reg.dt.to_period("M").astype(str)
    df["reg_weekday"] = df.reg.dt.weekday
    fill0 = [c for c in df.columns if c not in ("first_d", "first_day", "last_day", "recency", "first_team_day", "min_days_to_deadline",
                                                "share_closed_comps", "max_comp_teams_at_join_open", "min_comp_age")]
    df[fill0] = df[fill0].fillna(0)
    # 일부 유저에만 값이 있던 True/False 열은 결측을 채운 뒤 object가 된다 → 정수로 통일
    flags = [c for c in df.columns if df[c].dtype in ("bool", "object") and c not in ("period", "segment", "cohort_month")]
    df[flags] = df[flags].astype("int8")
    return df.drop(columns=["first_d"]).reset_index()


def main() -> None:
    t0 = time.time()
    engine = get_engine()
    skip = "--skip-build" in sys.argv          # MySQL 테이블(ml_users, ml_events)이 이미 있으면 다시 만들지 않음
    with engine.begin() as conn:
        for sql in ([] if skip else BUILD):
            conn.execute(text(sql))
            print(f"  {sql.split(chr(10))[0][:60]} ({time.time() - t0:.0f}초)", flush=True)
    with engine.begin() as conn:
        for sql in COMP_BUILD:
            conn.execute(text(sql))
        print(f"  ml_comp_daily ({time.time() - t0:.0f}초)", flush=True)
    ev = pd.read_sql(text("select UserId, day, type, n from ml_events"), engine)
    print(f"  ml_events {len(ev):,}행 ({time.time() - t0:.0f}초)", flush=True)
    team = pd.read_sql(text(TEAM_CTX), engine)
    print(f"  team ctx {len(team):,}행 ({time.time() - t0:.0f}초)", flush=True)
    users = pd.read_sql(text("select UserId, reg, period from ml_users"), engine)

    df = build_features(ev, team, users)
    out = processed("ml_dataset")
    df.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(df):,}행 x {df.shape[1]}열 ({time.time() - t0:.0f}초)")
    print(df.groupby(["period", "segment"]).y.agg(["size", "mean"]))


if __name__ == "__main__":
    main()
