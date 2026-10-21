-- ============================================================================
-- 03. 동역학 피처 17개 — temp 3단계 + 본쿼리
-- 누수 차단: 활동정의 = vote(3종)+follow+reaction+team 5종만 (kernel/forum 제외)
-- ============================================================================

-- ############################################################################
-- [STEP 1] temp_all_activities — 44만 학습대상의 5종 활동 로그
--   (DBeaver 블록별 실행. 02의 temp_target_users 선행 필요)
-- ############################################################################
DROP TABLE IF EXISTS temp_all_activities;

CREATE TABLE temp_all_activities AS
SELECT t.UserId, DATE(uf.CreationDate) AS act_date, 'follow' AS act_type
FROM temp_target_users t JOIN UserFollowers uf ON t.UserId=uf.UserId
WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
UNION ALL
SELECT t.UserId, DATE(mv.VoteDate), 'vote' FROM temp_target_users t JOIN ModelVotes mv ON t.UserId=mv.UserId WHERE mv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
UNION ALL
SELECT t.UserId, DATE(dv.VoteDate), 'vote' FROM temp_target_users t JOIN DatasetVotes dv ON t.UserId=dv.UserId WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
UNION ALL
SELECT t.UserId, DATE(fmv.VoteDate), 'vote' FROM temp_target_users t JOIN ForumMessageVotes fmv ON t.UserId=fmv.FromUserId WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
UNION ALL
SELECT t.UserId, DATE(fmr.ReactionDate), 'reaction' FROM temp_target_users t JOIN ForumMessageReactions fmr ON t.UserId=fmr.FromUserId WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
UNION ALL
SELECT t.UserId, DATE(tm.RequestDate), 'team' FROM temp_target_users t JOIN TeamMemberships tm ON t.UserId=tm.UserId WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date;

ALTER TABLE temp_all_activities ADD INDEX idx_aa_user (UserId);
ALTER TABLE temp_all_activities ADD INDEX idx_aa_user_date (UserId, act_date);
-- 검증: unique_users ≈ 438,325 (kernel-only 4,814명은 제외됨 — 정상)
--       act_type 분포: team 297K / vote 202K / follow 69K / reaction 5K

-- ############################################################################
-- [STEP 2] temp_user_active_days — 활동일(distinct) 단위
-- ############################################################################
DROP TABLE IF EXISTS temp_user_active_days;

CREATE TABLE temp_user_active_days AS
SELECT a.UserId, a.act_date, DATEDIFF(a.act_date, t.RegisterDate) AS day_offset
FROM (SELECT DISTINCT UserId, act_date FROM temp_all_activities) a
JOIN temp_target_users t ON a.UserId = t.UserId;

ALTER TABLE temp_user_active_days ADD INDEX idx_uad_user (UserId);
ALTER TABLE temp_user_active_days ADD INDEX idx_uad_user_offset (UserId, day_offset);
-- 검증: min_day=0, max_day=14 (BETWEEN 경계로 D14당일 포함 — 기존 피처와 일관성 위해 유지)

-- ############################################################################
-- [STEP 3] 본쿼리 — 동역학 17개 피처 (Python pd.read_sql로 실행)
--   ⚠️ StreakGroups의 ROW_NUMBER() 뺄셈은 CAST AS SIGNED 필수 (BIGINT UNSIGNED 오버플로우)
-- ############################################################################
/*
WITH
TimeDynamics AS (
    SELECT UserId,
        SUM(CASE WHEN day_offset BETWEEN 0 AND 6 THEN 1 ELSE 0 END) AS days_active_d1_to_d7,
        SUM(CASE WHEN day_offset BETWEEN 7 AND 14 THEN 1 ELSE 0 END) AS days_active_d8_to_d14,
        SUM(day_offset + 1) AS weighted_recency_score,
        MAX(day_offset) - MIN(day_offset) AS first_vs_last_action_gap
    FROM temp_user_active_days GROUP BY UserId
),
ActivityGaps AS (
    SELECT UserId, day_offset,
        day_offset - LAG(day_offset) OVER (PARTITION BY UserId ORDER BY day_offset) AS gap_from_prev
    FROM temp_user_active_days
),
StreakGapStats AS (
    SELECT UserId, MAX(gap_from_prev) AS activity_gap_max_d14,
        ROUND(STDDEV(gap_from_prev), 3) AS activity_gap_std_d14
    FROM ActivityGaps WHERE gap_from_prev IS NOT NULL GROUP BY UserId
),
StreakGroups AS (
    SELECT UserId, day_offset,
        CAST(day_offset AS SIGNED) - CAST(ROW_NUMBER() OVER (PARTITION BY UserId ORDER BY day_offset) AS SIGNED) AS grp
    FROM temp_user_active_days
),
StreakMax AS (
    SELECT UserId, MAX(streak_len) AS activity_streak_max_d14
    FROM (SELECT UserId, grp, COUNT(*) AS streak_len FROM StreakGroups GROUP BY UserId, grp) s
    GROUP BY UserId
),
ActionCounts AS (
    SELECT a.UserId,
        SUM(CASE WHEN DATEDIFF(a.act_date, t.RegisterDate) BETWEEN 0 AND 6 THEN 1 ELSE 0 END) AS total_actions_d7,
        SUM(CASE WHEN DATEDIFF(a.act_date, t.RegisterDate) BETWEEN 7 AND 14 THEN 1 ELSE 0 END) AS total_actions_d8_to_d14
    FROM temp_all_activities a JOIN temp_target_users t ON a.UserId=t.UserId GROUP BY a.UserId
),
TeamJoinTiming AS (
    SELECT t.UserId, MIN(DATEDIFF(DATE(tm.RequestDate), t.RegisterDate)) AS team_join_day
    FROM temp_target_users t JOIN TeamMemberships tm ON t.UserId=tm.UserId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date GROUP BY t.UserId
),
ActionTypeCounts AS (
    SELECT UserId,
        SUM(CASE WHEN act_type IN ('vote','follow','reaction') THEN 1 ELSE 0 END) AS total_consumption_d14,
        SUM(CASE WHEN act_type='team' THEN 1 ELSE 0 END) AS total_production_d14,
        SUM(CASE WHEN act_type='vote' THEN 1 ELSE 0 END) AS vote_count_all,
        COUNT(*) AS total_actions_all
    FROM temp_all_activities GROUP BY UserId
)
SELECT
    t.UserId,
    COALESCE(sm.activity_streak_max_d14, 1) AS activity_streak_max_d14,
    COALESCE(sg.activity_gap_max_d14, 0)    AS activity_gap_max_d14,
    COALESCE(sg.activity_gap_std_d14, 0)    AS activity_gap_std_d14,
    COALESCE(td.days_active_d1_to_d7, 0)    AS days_active_d1_to_d7,
    COALESCE(td.days_active_d8_to_d14, 0)   AS days_active_d8_to_d14,
    COALESCE(td.weighted_recency_score, 0)  AS weighted_recency_score,
    COALESCE(ac.total_actions_d7, 0)        AS total_actions_d7,
    COALESCE(ac.total_actions_d8_to_d14, 0) AS total_actions_d8_to_d14,
    CASE WHEN COALESCE(ac.total_actions_d7,0) > 0
         THEN ROUND(COALESCE(ac.total_actions_d8_to_d14,0)*1.0/ac.total_actions_d7, 3) ELSE 0 END AS velocity_ratio,
    COALESCE(tj.team_join_day, 99)          AS team_join_day,
    COALESCE(td.first_vs_last_action_gap,0) AS first_vs_last_action_gap,
    COALESCE(atc.total_consumption_d14, 0)  AS total_consumption_d14,
    COALESCE(atc.total_production_d14, 0)   AS total_production_d14,
    CASE WHEN COALESCE(atc.total_actions_all,0) > 0
         THEN ROUND(atc.total_consumption_d14*1.0/atc.total_actions_all, 3) ELSE 0 END AS consumption_ratio,
    CASE WHEN COALESCE(atc.total_actions_all,0) > 0
         THEN ROUND(atc.vote_count_all*1.0/atc.total_actions_all, 3) ELSE 0 END AS vote_dominance,
    CASE WHEN COALESCE(td.days_active_d1_to_d7,0)+COALESCE(td.days_active_d8_to_d14,0) > 0
         THEN ROUND(atc.vote_count_all*1.0/(td.days_active_d1_to_d7+td.days_active_d8_to_d14), 3) ELSE 0 END AS vote_per_active_day,
    CASE WHEN COALESCE(td.days_active_d1_to_d7,0)+COALESCE(td.days_active_d8_to_d14,0) > 0
         THEN ROUND(atc.total_production_d14*1.0/(td.days_active_d1_to_d7+td.days_active_d8_to_d14), 3) ELSE 0 END AS team_per_active_day
FROM temp_target_users t
LEFT JOIN TimeDynamics td ON t.UserId=td.UserId
LEFT JOIN StreakMax sm ON t.UserId=sm.UserId
LEFT JOIN StreakGapStats sg ON t.UserId=sg.UserId
LEFT JOIN ActionCounts ac ON t.UserId=ac.UserId
LEFT JOIN TeamJoinTiming tj ON t.UserId=tj.UserId
LEFT JOIN ActionTypeCounts atc ON t.UserId=atc.UserId
WHERE EXISTS (SELECT 1 FROM temp_all_activities aa WHERE aa.UserId = t.UserId);
*/
-- → df4 (features_dynamics.csv). Python에서 X_clean2(16피처)와 UserId merge → X_full(33피처)
--    kernel-only 4,814명은 df4에 없어 merge시 NaN → team_join_day=99, 나머지 0으로 fillna
-- 누수점검 통과: 전 피처 <10x. 최강 activity_gap_std_d14 4.2x, velocity_ratio 3.2x (정상)
