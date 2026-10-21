"""Kaggle 성장 정체 진단 대시보드 (Streamlit)

실행: streamlit run dashboard/app.py   (프로젝트 루트에서)
데이터: dashboard/data/*.csv (scripts/06_dashboard_data.py가 만든 집계본)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

DATA = Path(__file__).parent / "data"

# ── 차트 스타일 (프로젝트 차트 규칙과 같은 색·배치) ─────────────────────
PURPLE, BLUE, ORANGE, GRAY, LAVENDER = "#6A55D0", "#2B78D6", "#E8912D", "#8C8C8C", "#B8B0E2"
BG, SHADE = "#FCFBF9", "#EFEDF8"
FONT = "Apple SD Gothic Neo, Pretendard, Noto Sans KR, sans-serif"
PERIOD_COLOR = {"황금기": BLUE, "침체기": ORANGE}


def style(fig: go.Figure, title: str, height: int = 420, yfmt: str | None = None) -> go.Figure:
    """제목 왼쪽 위, 범례 오른쪽 위 가로 한 줄, 가로 격자만"""
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0, xanchor="left", font=dict(size=15)),
        font=dict(family=FONT, size=12, color="#333"), paper_bgcolor=BG, plot_bgcolor=BG, height=height,
        legend=dict(orientation="h", x=1, xanchor="right", y=1.02, yanchor="bottom", bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=70, b=10), hovermode="x unified")
    fig.update_xaxes(showgrid=False, linecolor="#CCC", tickfont=dict(color=GRAY))
    fig.update_yaxes(gridcolor="#EAEAEA", zeroline=False, tickfont=dict(color=GRAY), tickformat=yfmt)
    return fig


def shade_periods(fig: go.Figure, x_values: list, row=None, col=None) -> None:
    for name, (a, b) in {"황금기": ("2020-Q1", "2020-Q4"), "침체기": ("2024-Q3", "2025-Q2")}.items():
        if a in x_values and b in x_values:
            fig.add_vrect(x0=x_values.index(a) - 0.5, x1=x_values.index(b) + 0.5, fillcolor=SHADE, line_width=0, layer="below",
                          annotation_text=name, annotation_position="top", annotation_font_color=PURPLE, row=row, col=col)


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"{name}.csv", encoding="utf-8-sig")


st.set_page_config(page_title="Kaggle 성장 정체 진단", layout="wide")
st.markdown(f"<style>.stApp {{background-color: {BG};}}</style>", unsafe_allow_html=True)
st.title("Kaggle 성장 정체 진단")
st.caption("Meta Kaggle 공개 데이터 (2026-03-27까지) · 가입자는 3배, 활성 유저는 제자리 — 원인과 대응")

tab1, tab2, tab3, tab4 = st.tabs(["① 성장 현황", "② 신규 유입 퍼널", "③ 예측 모델 모니터링", "④ 실험 설계"])

# ── ① 성장 현황 ─────────────────────────────────────────────────
with tab1:
    q = load("growth_quarterly"); trend = load("growth_trend"); ten = load("qau_tenure")
    quarters = q.q.tolist()
    lo_q, hi_q = st.select_slider("분기 범위", options=quarters, value=(quarters[0], quarters[-1]), key="q_range")
    qs = q[(q.q >= lo_q) & (q.q <= hi_q)]
    xq = qs.q.tolist()

    t = trend[trend["단위"] == "분기"].set_index("지표")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("신규 가입자 연간 증가율", f"{t.loc['신규 가입자', '연간 증가율']:+.1%}", help="2020-Q1 ~ 2025-Q4, log 추세 + 분기 더미")
    c2.metric("QAU 연간 증가율", f"{t.loc['활성 유저', '연간 증가율']:+.1%}",
              f"90% CI {t.loc['활성 유저', 'CI 하한']:+.1%} ~ {t.loc['활성 유저', 'CI 상한']:+.1%} → {t.loc['활성 유저', '정체 판정 (±5%)']}", delta_color="off")
    g = q[q.q.isin(["2020-Q1", "2020-Q2", "2020-Q3", "2020-Q4"])]; s = q[q.q.isin(["2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2"])]
    c3.metric("가입자 (황금기 → 침체기)", f"×{s.new_users.mean() / g.new_users.mean():.2f}")
    c4.metric("QAU (황금기 → 침체기)", f"×{s.qau.mean() / g.qau.mean():.2f}")

    fig = go.Figure()
    fig.add_bar(x=xq, y=qs.qau_creators, name="창작 있음", marker_color=PURPLE)
    fig.add_bar(x=xq, y=qs.qau_team_only, name="팀 합류만 (창작 없음)", marker_color=GRAY, opacity=0.5)
    fig.update_layout(barmode="stack")
    shade_periods(fig, xq)
    st.plotly_chart(style(fig, "QAU = 창작 있음 + 팀 합류만 — 정체는 두 흐름의 상쇄", yfmt=","), width="stretch")

    left, right = st.columns(2)
    with left:
        f2 = go.Figure(go.Bar(x=xq, y=qs.new_users, marker_color=LAVENDER, name="신규 가입자"))
        shade_periods(f2, xq)
        st.plotly_chart(style(f2, "분기 신규 가입자", 360, ","), width="stretch")
    with right:
        tt = ten[(ten.q >= lo_q) & (ten.q <= hi_q)]
        f3 = go.Figure()
        for name, color in [("90일 이내", ORANGE), ("91일 ~ 1년", LAVENDER), ("1 ~ 3년", BLUE), ("3년 이상", PURPLE)]:
            d = tt[tt.tenure == name]
            f3.add_bar(x=d.q, y=d.share, name=name, marker_color=color)
        f3.update_layout(barmode="stack")
        st.plotly_chart(style(f3, "QAU 가입 연차 구성 — 신규는 줄고 3년 이상이 메움", 360, ".0%"), width="stretch")

    st.markdown("**정체 판정 (동등성 검정)** — 연간 증가율의 90% CI가 ±5% 안이면 정체")
    st.dataframe(trend.style.format({"연간 증가율": "{:+.1%}", "CI 하한": "{:+.1%}", "CI 상한": "{:+.1%}"}), hide_index=True, width="stretch")

# ── ② 신규 유입 퍼널 ─────────────────────────────────────────────
with tab2:
    cm = load("cohort_monthly"); fa = load("first_activity"); tr = load("transitions"); fn = load("funnel")
    q = load("growth_quarterly")
    f1 = go.Figure(go.Scatter(x=q.q, y=q.activation_rate, mode="lines+markers", line=dict(color=PURPLE, width=2.5),
                              marker=dict(size=6, line=dict(color="white", width=1)), name="90일 활성화율"))
    shade_periods(f1, q.q.tolist())
    st.plotly_chart(style(f1, "가입 코호트 90일 활성화율 — 가입 후 90일 안에 참여·창작을 시작한 비율", 380, ".0%"), width="stretch")

    metric_names = {"activation_90d": "90일 활성화", "same_day": "가입 당일 활동", "team_90d": "90일 내 대회 참가",
                    "creator_90d": "90일 내 창작", "light_90d": "90일 내 가벼운 활동"}
    pick = st.radio("월별 지표", list(metric_names), format_func=metric_names.get, horizontal=True)
    f2 = go.Figure()
    for p in ["황금기", "침체기"]:
        d = cm[cm.period == p]
        f2.add_scatter(x=d.month_index, y=d[pick], mode="lines+markers", name=f"{p} (n={d.new_users.sum():,})",
                       line=dict(color=PERIOD_COLOR[p], width=2.5), marker=dict(size=7, line=dict(color="white", width=1)),
                       customdata=d.cohort_month, hovertemplate="%{customdata}: %{y:.2%}<extra></extra>")
    f2.update_xaxes(tickmode="array", tickvals=list(range(1, 13)), ticktext=[f"{i}번째 달" for i in range(1, 13)])
    st.plotly_chart(style(f2, f"가입 월별 {metric_names[pick]} — 침체기는 12개월 내내 낮음", 380, ".1%"), width="stretch")

    left, mid, right = st.columns(3)
    with left:
        f3 = go.Figure()
        for p in ["황금기", "침체기"]:
            d = fn[fn.period == p]
            f3.add_bar(x=d["단계"], y=d.rate_of_signups, name=p, marker_color=PERIOD_COLOR[p], opacity=0.75,
                       text=[f"{v:.2%}" for v in d.rate_of_signups], textposition="outside")
        f3.update_layout(barmode="group")
        st.plotly_chart(style(f3, "퍼널 (가입자 대비)", 380, ".0%"), width="stretch")
    with mid:
        f4 = go.Figure()
        for p in ["황금기", "침체기"]:
            d = fa[fa.period == p].sort_values("share")
            f4.add_bar(y=d.activity, x=d.share, orientation="h", name=p, marker_color=PERIOD_COLOR[p], opacity=0.75)
        f4.update_layout(barmode="group")
        st.plotly_chart(style(f4, "첫 활동 구성 (활동 유저 기준)", 380), width="stretch")
    with right:
        f5 = go.Figure()
        for p in ["황금기", "침체기"]:
            d = tr[tr.period == p]
            f5.add_bar(x=d["단계"], y=d.rate, name=p, marker_color=PERIOD_COLOR[p], opacity=0.75,
                       text=[f"{v:.1%}" for v in d.rate], textposition="outside")
        f5.update_layout(barmode="group")
        st.plotly_chart(style(f5, "다음 단계로 넘어가는 비율", 380, ".0%"), width="stretch")
    st.info("참여 이후(대회 참가 → 제출, 노트북 작성 → 공개)는 두 시기가 같고, **가벼운 활동 → 참여**만 절반으로 약해졌다. 병목 후보는 입구.")

# ── ③ 예측 모델 모니터링 ───────────────────────────────────────────
with tab3:
    mm = load("model_monthly"); dec = load("model_deciles")
    st.caption("D+14 행동으로 D+15 ~ D+90 핵심 창작(D)을 예측. 2024-07 ~ 2025-03 가입자로 학습한 모델로 그 이후 가입 월을 점수화")
    last = mm.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{last.cohort_month} 대상", f"{int(last['대상']):,}명")
    c2.metric("PR-AUC (랜덤 대비)", f"{last['PR-AUC']:.3f}", f"{last['랜덤 대비']:.1f}배", delta_color="off")
    c3.metric("상위 10% 재현율", f"{last['상위 10% 재현율']:.0%}")
    c4.metric("규칙 그룹(노트북 작성자) 전환율", f"{last['규칙 그룹 전환율']:.0%}", f"{int(last['규칙 그룹 인원'])}명", delta_color="off")

    left, right = st.columns(2)
    with left:
        f1 = go.Figure()
        for col, color in [("상위 10% 재현율", PURPLE), ("상위 10% 정밀도", BLUE), ("정답 비율", GRAY)]:
            f1.add_scatter(x=mm.cohort_month, y=mm[col], name=col, mode="lines+markers", line=dict(color=color, width=2.5),
                           marker=dict(size=7, line=dict(color="white", width=1)))
        months = mm.cohort_month.tolist(); t0 = months.index("2025-07")
        f1.add_vrect(x0=t0 - 0.5, x1=len(months) - 0.5, fillcolor=SHADE, line_width=0, layer="below", annotation_text="테스트 기간", annotation_position="top")
        f1.update_xaxes(type="category")
        st.plotly_chart(style(f1, "월별 성능 — 학습 이후 기간", 400, ".0%"), width="stretch")
    with right:
        f2 = go.Figure(go.Bar(x=dec.decile, y=dec.lift, marker_color=[PURPLE] + [LAVENDER] * 9,
                              text=[f"{v:.1f}배" for v in dec.lift], textposition="outside"))
        f2.update_xaxes(tickmode="array", tickvals=list(range(1, 11)), title="점수 10분위 (1 = 상위 10%)")
        st.plotly_chart(style(f2, "분위별 lift (분위 정답 비율 ÷ 전체)", 400), width="stretch")
    st.dataframe(mm.style.format({"대상": "{:,}", "정답 비율": "{:.2%}", "PR-AUC": "{:.3f}", "랜덤 대비": "{:.1f}배", "상위 10% 정밀도": "{:.1%}",
                                  "상위 10% 재현율": "{:.1%}", "규칙 그룹 인원": "{:,}", "규칙 그룹 전환율": "{:.1%}"}),
                 hide_index=True, width="stretch")

# ── ④ 실험 설계 ─────────────────────────────────────────────────
with tab4:
    ab = load("ab_params").iloc[0]
    st.markdown("""**실험: 끝난 대회에만 참가한 신규 유저에게 진행 중 대회 추천** (설계서: `docs/ab_test_design.md`)

| | 실험군 | 대조군 |
|---|---|---|
| 대상 | D+14에 끝난 대회에만 참가, D·노트북 활동 없음 | 같음 |
| 처치 | D+15 "지금 참가할 수 있는 대회 3개" 메일 + 알림 1회 | 없음 |
| 주 지표 | 처치 후 30일 대회 제출 | 같음 |""")
    c1, c2, c3 = st.columns(3)
    c1.metric("월 평균 대상", f"{ab['월 평균 대상']:,.0f}명", f"모델 대상의 {ab['모델 대상 대비 비중']:.0%}", delta_color="off")
    c2.metric("30일 제출 기준값", f"{ab['30일 제출 기준값']:.2%}")
    c3.metric("90일 D 전환 기준값", f"{ab['90일 D 전환 기준값']:.2%}")

    st.subheader("표본 크기 계산기")
    a, b, c = st.columns(3)
    mde = a.slider("잡고 싶은 상대 효과 (%)", 10, 60, 30, 5) / 100
    share_t = b.slider("실험군 비율 (%)", 10, 90, 50, 10) / 100
    monthly = c.number_input("월 대상 인원", value=int(ab["월 평균 대상"]), step=500)
    p0 = ab["30일 제출 기준값"]
    ratio = (1 - share_t) / share_t
    n1 = NormalIndPower().solve_power(effect_size=proportion_effectsize(p0 * (1 + mde), p0), alpha=0.05, power=0.8, ratio=ratio)
    total = n1 * (1 + ratio)
    k1, k2, k3 = st.columns(3)
    k1.metric("실험군", f"{n1:,.0f}명"); k2.metric("대조군", f"{n1 * ratio:,.0f}명"); k3.metric("모집 기간", f"{total / monthly:.1f}개월")
    st.caption(f"기준 {p0:.2%} → {p0 * (1 + mde):.2%}, 양측 α = 0.05, 검정력 80%")

    st.subheader("표본 비율 불일치(SRM) 점검")
    a, b = st.columns(2)
    nt = a.number_input("실험군 배정 인원", value=6000, step=100)
    nc = b.number_input("대조군 배정 인원", value=6000, step=100)
    expected = np.array([share_t, 1 - share_t]) * (nt + nc)
    p_srm = stats.chisquare([nt, nc], expected).pvalue
    (st.error if p_srm < 0.001 else st.success)(f"χ² 검정 p = {p_srm:.4f} — " + ("배정·로깅 오류 의심, 분석 중단" if p_srm < 0.001 else "배정 비율 정상"))
