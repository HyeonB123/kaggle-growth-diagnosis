"""대시보드(Streamlit, Tableau 공용) 집계 데이터를 dashboard/data/*.csv로 저장한다.

유저 단위 데이터는 내보내지 않고 집계만 저장한다 (Tableau Public은 데이터가 공개되므로).
01 ~ 05 스크립트가 만든 data/processed/*.parquet가 필요하다.

| 파일 | 탭 | 내용 |
|---|---|---|
| growth_quarterly.csv | 성장 현황 | 2017-Q1 ~ 2025-Q4 가입자, QAU(창작 있음 / 팀 합류만), 90일 활성화율 |
| qau_tenure.csv | 성장 현황 | 분기 QAU의 가입 연차 구성 (long 형식) |
| growth_trend.csv | 성장 현황 | 2020 ~ 2025 연간 증가율과 90% CI, 정체 판정 (분기·월) |
| cohort_monthly.csv | 신규 유입 | 두 시기 가입 월별 90일 활성화율, 가입 당일 활동, 대회 참가, 창작, 가벼운 활동 |
| first_activity.csv | 신규 유입 | 시기별 첫 활동 구성 |
| transitions.csv | 신규 유입 | 시기별 분기점 다음 단계 비율 |
| funnel.csv | 신규 유입 | 시기별 퍼널: 가입 → 비-D 참여 시작 → D |
| model_monthly.csv | 모델 모니터링 | 학습 이후 가입 월별 대상 수, 정답 비율, PR-AUC, 상위 10% 정밀도·재현율, 규칙 그룹 전환율 |
| model_deciles.csv | 모델 모니터링 | 점수 10분위별 정답 비율과 lift |
| ab_params.csv | 실험 | 설계 기준값 (월 대상 수, 기준 제출률 등) |

모델 모니터링은 2024-07 ~ 2025-03 가입자로 학습한 모델(05 노트북과 같은 피처)로 2025-04 ~ 09 가입자를 점수화한다.

사용: python scripts/06_dashboard_data.py   (프로젝트 루트에서 실행, .env 필요: 30일 제출 기준값 계산)
"""
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sqlalchemy import text
from statsmodels.regression.linear_model import OLS

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from metakaggle.config import ROOT, SEED, processed  # noqa: E402
from metakaggle.db import get_engine  # noqa: E402

OUT = ROOT / "dashboard" / "data"
GOLDEN_Q = [f"2020-Q{i}" for i in range(1, 5)]
STAG_Q = ["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2"]
KO = {"Golden": "황금기", "Stagnation": "침체기"}
FEATS = ["n_follow", "n_vote_model", "n_vote_dataset", "n_vote_forum", "n_reaction", "n_team", "n_teams", "n_light", "n_light_types",
         "active_days", "first_day", "last_day", "recency", "active_d0", "active_d1_7", "active_d8_14", "reg_weekday",
         "first_is_team", "light_only", "max_team_size_d14", "first_team_day", "min_days_to_deadline", "max_reward",
         "comp_featured", "comp_research", "comp_playground", "comp_community", "comp_getting_started",
         "n_followed_by", "n_closed_comps", "n_open_comps", "share_closed_comps", "max_comp_teams_at_join_open", "min_comp_age",
         "any_kernels_only", "any_playground_series", "any_joined_others_team", "first_reward_usd", "first_reward_knowledge"]


def save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")   # BOM: 엑셀·태블로에서 한글 깨짐 방지
    print(f"dashboard/data/{name}.csv: {len(df):,}행")


def annual_growth(y: pd.Series, per_year: int, maxlags: int) -> tuple:
    X = pd.DataFrame({"const": 1.0, "t": np.arange(len(y)) / per_year}, index=y.index)
    season = y.index.str[-2:]
    for s in sorted(set(season))[1:]:
        X[f"s_{s}"] = (season == s).astype(float)
    r = OLS(np.log(y.astype(float)), X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    lo, hi = r.conf_int(alpha=0.10).loc["t"]
    return np.expm1(r.params["t"]), np.expm1(lo), np.expm1(hi)


def growth() -> None:
    q = pd.read_parquet(processed("quarterly_series")).set_index("q").loc["2017-Q1":]
    q["activation_rate"] = q.activated_90d / q.new_users
    q["period"] = np.where(q.index.isin(GOLDEN_Q), "황금기", np.where(q.index.isin(STAG_Q), "침체기", ""))
    save(q.reset_index(), "growth_quarterly")

    ten = pd.read_parquet(processed("qau_by_tenure"))
    names = {"tenure_90d": "90일 이내", "tenure_1y": "91일 ~ 1년", "tenure_1_3y": "1 ~ 3년", "tenure_3y_plus": "3년 이상"}
    long = ten.melt(id_vars=["q", "qau"], value_vars=list(names), var_name="tenure", value_name="users")
    long["tenure"] = long.tenure.map(names)
    long["share"] = long.users / long.qau
    save(long, "qau_tenure")

    m = pd.read_parquet(processed("monthly_series")).set_index("ym")
    rows = []
    for unit, df, cols, per, lags in [("분기", q.loc["2020-Q1":"2025-Q4"], {"new_users": "신규 가입자", "qau": "활성 유저", "qau_creators": "창작 있음", "qau_team_only": "팀 합류만"}, 4, 2),
                                      ("월", m, {"new_users": "신규 가입자", "mau": "활성 유저", "mau_creators": "창작 있음", "mau_team_only": "팀 합류만"}, 12, 6)]:
        for c, name in cols.items():
            g, lo, hi = annual_growth(df[c], per, lags)
            rows.append({"단위": unit, "지표": name, "연간 증가율": g, "CI 하한": lo, "CI 상한": hi,
                         "정체 판정 (±5%)": "정체" if (lo > -0.05 and hi < 0.05) else ("증가" if lo > 0 else ("감소" if hi < 0 else "판정 불가"))})
    save(pd.DataFrame(rows), "growth_trend")


def acquisition() -> None:
    h1 = pd.read_parquet(processed("h1_cohort"), columns=["period", "reg", "first_qau", "first_creator", "first_team", "first_light"])
    h1["cohort_month"] = pd.to_datetime(h1.reg).dt.to_period("M").astype(str)
    agg = h1.groupby(["period", "cohort_month"]).agg(
        new_users=("reg", "size"), activation_90d=("first_qau", lambda s: (s <= 90).mean()),
        same_day=("first_qau", lambda s: (s <= 0).mean()), team_90d=("first_team", lambda s: (s <= 90).mean()),
        creator_90d=("first_creator", lambda s: (s <= 90).mean()), light_90d=("first_light", lambda s: (s <= 90).mean())).reset_index()
    agg["period"] = agg.period.map(KO)
    agg["month_index"] = agg.groupby("period").cumcount() + 1
    save(agg, "cohort_monthly")

    log = pd.read_parquet(processed("event_log"))
    order = ["가벼운 활동", "대회 참가", "노트북 작성", "대회 제출", "노트북 공개", "포럼 글", "데이터셋", "모델"]
    log = log.assign(r=log.activity.map({a: i for i, a in enumerate(order)})).sort_values(["UserId", "day", "r"])
    log["nxt"] = log.groupby("UserId").activity.shift(-1).fillna("(끝)")
    first = log.groupby("UserId").agg(period=("period", "first"), activity=("activity", "first"))
    fa = first.groupby(["period", "activity"]).size().rename("users").reset_index()
    fa["share"] = fa.users / fa.groupby("period").users.transform("sum")
    fa["period"] = fa.period.map(KO)
    save(fa, "first_activity")

    rows = []
    for p in ["Golden", "Stagnation"]:
        x = log[log.period == p]
        for node, target in [("대회 참가", "대회 제출"), ("노트북 작성", "노트북 공개")]:
            n = x[x.activity == node]
            rows.append({"period": KO[p], "단계": f"{node} → {target}", "n": len(n), "rate": (n.nxt == target).mean()})
        f = first[first.period == p]
        light_first = f[f.activity == "가벼운 활동"].index
        deeper = x[(x.activity != "가벼운 활동") & x.UserId.isin(light_first)].UserId.nunique()
        rows.append({"period": KO[p], "단계": "가벼운 활동 시작 → 참여·창작", "n": len(light_first), "rate": deeper / len(light_first)})
    save(pd.DataFrame(rows), "transitions")

    h2 = pd.read_parquet(processed("h2_cohort"))
    h2["start"] = h2[["first_team", "first_kv"]].min(axis=1)
    st = h2[(h2.start <= 90) & ~(h2.first_d < h2.start)]
    st = st.assign(conv=(st.first_d - st.start).between(0, 90))
    n_users = h1.groupby("period").size()
    rows = []
    for p in ["Golden", "Stagnation"]:
        s = st[st.period == p]
        rows += [{"period": KO[p], "단계": "1. 가입", "users": int(n_users[p])},
                 {"period": KO[p], "단계": "2. 비-D 참여 시작 (90일)", "users": len(s)},
                 {"period": KO[p], "단계": "3. 시작 후 D 전환 (90일)", "users": int(s.conv.sum())}]
    fn = pd.DataFrame(rows)
    fn["rate_of_signups"] = fn.users / fn.period.map({KO[p]: n_users[p] for p in n_users.index})
    save(fn, "funnel")


def model_monitoring() -> None:
    d = pd.read_parquet(processed("ml_dataset"))
    s = d[d.period == "Stagnation"]
    m_df, rule = s[s.segment == "model"], s[s.segment == "notebook"]
    train = m_df[m_df.cohort_month <= "2025-03"]
    later = m_df[m_df.cohort_month >= "2025-04"].copy()
    model = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, random_state=SEED, verbose=-1).fit(train[FEATS], train.y)
    later["score"] = model.predict_proba(later[FEATS])[:, 1]

    rows = []
    for mon, g in later.groupby("cohort_month"):
        k = int(len(g) * 0.1); top = g.nlargest(k, "score")
        r = rule[rule.cohort_month == mon]
        rows.append({"cohort_month": mon, "구분": "검증" if mon <= "2025-06" else "테스트", "대상": len(g), "정답 비율": g.y.mean(),
                     "PR-AUC": average_precision_score(g.y, g.score), "랜덤 대비": average_precision_score(g.y, g.score) / g.y.mean(),
                     "상위 10% 정밀도": top.y.mean(), "상위 10% 재현율": top.y.sum() / g.y.sum(),
                     "규칙 그룹 인원": len(r), "규칙 그룹 전환율": r.y.mean()})
    save(pd.DataFrame(rows), "model_monthly")

    later["decile"] = 10 - pd.qcut(later.score.rank(method="first"), 10, labels=False)
    dec = later.groupby("decile").agg(users=("y", "size"), positive_rate=("y", "mean")).reset_index()
    dec["lift"] = dec.positive_rate / later.y.mean()
    save(dec, "model_deciles")


def ab_params() -> None:
    d = pd.read_parquet(processed("ml_dataset"))
    m = d[(d.period == "Stagnation") & (d.segment == "model")]
    elig = m[(m.n_teams > 0) & (m.share_closed_comps == 1) & (m.n_teams <= 10)]
    sub = pd.read_sql(text("select distinct UserId from ml_events where type = 'submission' and day between 15 and 44"), get_engine()).UserId
    save(pd.DataFrame([{"월 평균 대상": elig.groupby("cohort_month").size().mean(),
                        "30일 제출 기준값": elig.UserId.isin(sub).mean(), "90일 D 전환 기준값": elig.y.mean(),
                        "모델 대상 대비 비중": len(elig) / len(m)}]), "ab_params")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    growth(); acquisition(); model_monitoring(); ab_params()


if __name__ == "__main__":
    main()
