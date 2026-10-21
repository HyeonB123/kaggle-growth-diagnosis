-- ============================================================================
-- 03. df1: 활동량(Volume) + 시간(Time) 피처, D+14 기준
-- 4분기 코호트 전체 대상 → Python에서 학습대상과 inner merge
-- ============================================================================
WITH TargetUsers AS (
    -- 학습 대상자만 (앞서 추출한 443,139명과 동일 조건)
    SELECT 
        Id AS UserId,
        RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
        DATE_ADD(RegisterDate, INTERVAL 7 DAY) AS D7_Date,
        DATE_ADD(RegisterDate, INTERVAL 14 DAY) AS D14_Date,
        DATE_ADD(RegisterDate, INTERVAL 90 DAY) AS D90_Date
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),

-- ========================================================================
-- 노트북 통계 (D+14 기준)
-- ========================================================================
KernelStats AS (
    SELECT 
        t.UserId,
        COUNT(*) AS kernel_versions_d14,
        COUNT(DISTINCT kv.ScriptId) AS kernel_count_d14,
        MAX(kv.TotalLines) AS max_kernel_lines_d14,
        SUM(kv.TotalLines) AS sum_kernel_lines_d14,
        AVG(kv.TotalLines) AS avg_kernel_lines_d14,
        -- D+7 시점 (속도 측정용)
        SUM(CASE WHEN kv.CreationDate <= t.D7_Date THEN 1 ELSE 0 END) AS kernel_versions_d7
    FROM TargetUsers t
    JOIN KernelVersions kv ON t.UserId = kv.AuthorUserId
    WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 포럼 메시지 통계 (본글 vs 댓글 구분)
-- ========================================================================
ForumStats AS (
    SELECT 
        t.UserId,
        COUNT(*) AS forum_msg_d14,
        SUM(CASE WHEN fm.ReplyToForumMessageId IS NULL THEN 1 ELSE 0 END) AS forum_msg_root_d14,
        SUM(CASE WHEN fm.ReplyToForumMessageId IS NOT NULL THEN 1 ELSE 0 END) AS forum_msg_reply_d14,
        AVG(CHAR_LENGTH(fm.Message)) AS avg_forum_msg_length,
        SUM(CASE WHEN fm.PostDate <= t.D7_Date THEN 1 ELSE 0 END) AS forum_msg_d7
    FROM TargetUsers t
    JOIN ForumMessages fm ON t.UserId = fm.PostUserId
    WHERE fm.PostDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 투표 통계 (Model + Dataset + Forum 통합)
-- ========================================================================
VoteStats AS (
    SELECT UserId, 
           SUM(is_model) AS vote_model_d14,
           SUM(is_dataset) AS vote_dataset_d14,
           SUM(is_forum) AS vote_forum_d14,
           SUM(is_d7) AS vote_total_d7
    FROM (
        SELECT t.UserId, 1 AS is_model, 0 AS is_dataset, 0 AS is_forum,
               CASE WHEN mv.VoteDate <= t.D7_Date THEN 1 ELSE 0 END AS is_d7
        FROM TargetUsers t JOIN ModelVotes mv ON t.UserId = mv.UserId
        WHERE mv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
        UNION ALL
        SELECT t.UserId, 0, 1, 0,
               CASE WHEN dv.VoteDate <= t.D7_Date THEN 1 ELSE 0 END
        FROM TargetUsers t JOIN DatasetVotes dv ON t.UserId = dv.UserId
        WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
        UNION ALL
        SELECT t.UserId, 0, 0, 1,
               CASE WHEN fmv.VoteDate <= t.D7_Date THEN 1 ELSE 0 END
        FROM TargetUsers t JOIN ForumMessageVotes fmv ON t.UserId = fmv.FromUserId
        WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS all_votes
    GROUP BY UserId
),

-- ========================================================================
-- 팔로우 통계
-- ========================================================================
FollowStats AS (
    SELECT t.UserId, COUNT(*) AS follow_count_d14
    FROM TargetUsers t JOIN UserFollowers uf ON t.UserId = uf.UserId
    WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 리액션 통계
-- ========================================================================
ReactionStats AS (
    SELECT t.UserId, COUNT(*) AS reaction_count_d14
    FROM TargetUsers t JOIN ForumMessageReactions fmr ON t.UserId = fmr.FromUserId
    WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 팀 합류 통계
-- ========================================================================
TeamStats AS (
    SELECT t.UserId, COUNT(*) AS team_count_d14
    FROM TargetUsers t JOIN TeamMemberships tm ON t.UserId = tm.UserId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- Submission 통계 (팀 전파 방식)
-- ========================================================================
SubmissionStats AS (
    SELECT t.UserId, COUNT(DISTINCT s.Id) AS submission_count_d14
    FROM TargetUsers t 
    JOIN TeamMemberships tm ON t.UserId = tm.UserId
    JOIN Submissions s ON tm.TeamId = s.TeamId
    WHERE s.SubmissionDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 첫 활동 시점 (이전에 만든 쿼리 재사용)
-- ========================================================================
AllActivities AS (
    SELECT t.UserId, kv.CreationDate AS d 
    FROM TargetUsers t JOIN KernelVersions kv ON t.UserId = kv.AuthorUserId
    WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, fm.PostDate FROM TargetUsers t JOIN ForumMessages fm ON t.UserId = fm.PostUserId
    WHERE fm.PostDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, mv.VoteDate FROM TargetUsers t JOIN ModelVotes mv ON t.UserId = mv.UserId
    WHERE mv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, dv.VoteDate FROM TargetUsers t JOIN DatasetVotes dv ON t.UserId = dv.UserId
    WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, fmv.VoteDate FROM TargetUsers t JOIN ForumMessageVotes fmv ON t.UserId = fmv.FromUserId
    WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, fmr.ReactionDate FROM TargetUsers t JOIN ForumMessageReactions fmr ON t.UserId = fmr.FromUserId
    WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, uf.CreationDate FROM TargetUsers t JOIN UserFollowers uf ON t.UserId = uf.UserId
    WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION ALL
    SELECT t.UserId, tm.RequestDate FROM TargetUsers t JOIN TeamMemberships tm ON t.UserId = tm.UserId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
),
TimeStats AS (
    SELECT 
        a.UserId,                                                              -- 명시
        TIMESTAMPDIFF(HOUR, t.RegisterDate, MIN(a.d)) AS hours_to_first_action,
        TIMESTAMPDIFF(DAY, t.RegisterDate, MIN(a.d)) AS days_to_first_action,
        COUNT(DISTINCT DATE(a.d)) AS active_days_d14,
        TIMESTAMPDIFF(DAY, MAX(a.d), t.D14_Date) AS days_since_last_activity,
        SUM(CASE WHEN DAYOFWEEK(a.d) IN (1,7) THEN 1 ELSE 0 END) / COUNT(*) AS weekend_action_ratio
    FROM AllActivities a
    JOIN TargetUsers t ON a.UserId = t.UserId
    GROUP BY a.UserId, t.RegisterDate, t.D14_Date
)

-- ========================================================================
-- 🏁 최종 출력 - 모든 Volume + Time 피처 결합
-- ========================================================================
SELECT 
    t.UserId,
    t.Period,
    
    -- Volume 피처
    COALESCE(ks.kernel_versions_d14, 0) AS kernel_versions_d14,
    COALESCE(ks.kernel_count_d14, 0) AS kernel_count_d14,
    COALESCE(ks.max_kernel_lines_d14, 0) AS max_kernel_lines_d14,
    COALESCE(ks.sum_kernel_lines_d14, 0) AS sum_kernel_lines_d14,
    COALESCE(ROUND(ks.avg_kernel_lines_d14, 2), 0) AS avg_kernel_lines_d14,
    COALESCE(ks.kernel_versions_d7, 0) AS kernel_versions_d7,
    
    COALESCE(fs.forum_msg_d14, 0) AS forum_msg_d14,
    COALESCE(fs.forum_msg_root_d14, 0) AS forum_msg_root_d14,
    COALESCE(fs.forum_msg_reply_d14, 0) AS forum_msg_reply_d14,
    COALESCE(ROUND(fs.avg_forum_msg_length, 1), 0) AS avg_forum_msg_length,
    COALESCE(fs.forum_msg_d7, 0) AS forum_msg_d7,
    
    COALESCE(vs.vote_model_d14, 0) AS vote_model_d14,
    COALESCE(vs.vote_dataset_d14, 0) AS vote_dataset_d14,
    COALESCE(vs.vote_forum_d14, 0) AS vote_forum_d14,
    COALESCE(vs.vote_total_d7, 0) AS vote_total_d7,
    
    COALESCE(fol.follow_count_d14, 0) AS follow_count_d14,
    COALESCE(rs.reaction_count_d14, 0) AS reaction_count_d14,
    COALESCE(ts.team_count_d14, 0) AS team_count_d14,
    COALESCE(ss.submission_count_d14, 0) AS submission_count_d14,
    
    -- Time 피처
    COALESCE(tms.hours_to_first_action, 999) AS hours_to_first_action,
    COALESCE(tms.days_to_first_action, 99) AS days_to_first_action,
    COALESCE(tms.active_days_d14, 0) AS active_days_d14,
    COALESCE(tms.days_since_last_activity, 14) AS days_since_last_activity,
    COALESCE(ROUND(tms.weekend_action_ratio, 3), 0) AS weekend_action_ratio
    
FROM TargetUsers t
LEFT JOIN KernelStats ks ON t.UserId = ks.UserId
LEFT JOIN ForumStats fs ON t.UserId = fs.UserId
LEFT JOIN VoteStats vs ON t.UserId = vs.UserId
LEFT JOIN FollowStats fol ON t.UserId = fol.UserId
LEFT JOIN ReactionStats rs ON t.UserId = rs.UserId
LEFT JOIN TeamStats ts ON t.UserId = ts.UserId
LEFT JOIN SubmissionStats ss ON t.UserId = ss.UserId
LEFT JOIN TimeStats tms ON t.UserId = tms.UserId
WHERE EXISTS (
    SELECT 1 FROM AllActivities a WHERE a.UserId = t.UserId
);
