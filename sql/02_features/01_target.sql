-- ============================================================================
-- 01. 학습대상 + 타깃 (target_d_conversion = D+15 ~ D+90에 D 활동 발생)
-- 결과: 443,139명, 양성 18,815명 (4.25%). Python에서 df1 ~ df3와 UserId로 병합
-- TODO: 시각이 기록되는 활동(KernelVersions, ForumMessages, DatasetVersions 등)은 D+14 당일분이
--       누수자·타깃 어디에도 안 잡힘 (docs/decisions.md 검토 대기)
-- ============================================================================
WITH TargetUsers AS (
    SELECT 
        Id AS UserId,
        RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
        DATE_ADD(RegisterDate, INTERVAL 14 DAY) AS D14_Date,
        DATE_ADD(RegisterDate, INTERVAL 90 DAY) AS D90_Date
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),

-- ========================================================================
-- [STEP 1] D+14 시점까지 D 활동 한 유저 (누수자 - 제외 대상)
-- ========================================================================
D_Leakers AS (
    SELECT DISTINCT t.UserId
    FROM TargetUsers t
    JOIN (
        -- D 정의 활동 (D+14 이전)
        SELECT k.AuthorUserId AS UserId, k.MadePublicDate AS d_date 
        FROM Kernels k WHERE k.MadePublicDate IS NOT NULL
        UNION ALL
        SELECT tm.UserId, s.SubmissionDate
        FROM TeamMemberships tm JOIN Submissions s ON tm.TeamId = s.TeamId
        UNION ALL
        SELECT dt.OwnerUserId, dt.CreationDate FROM DatasetTasks dt
        UNION ALL
        SELECT dsv.CreatorUserId, dsv.CreationDate FROM DatasetVersions dsv
        UNION ALL
        SELECT fm.PostUserId, fm.PostDate FROM ForumMessages fm
        UNION ALL
        SELECT dts.SubmittedUserId, dts.CreationDate FROM DatasetTaskSubmissions dts
        UNION ALL
        SELECT mv.CreatorUserId, mv.CreationDate FROM ModelVersions mv
    ) d_acts ON t.UserId = d_acts.UserId
    WHERE d_acts.d_date BETWEEN t.RegisterDate AND t.D14_Date
),

-- ========================================================================
-- [STEP 2] D+14 시점 C-Active 유저 식별
-- ========================================================================
D14_Activity AS (
    -- has_notebook
    SELECT t.UserId, 'notebook' AS act_type
    FROM TargetUsers t JOIN KernelVersions kv ON t.UserId = kv.AuthorUserId
    WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION
    -- has_follow
    SELECT t.UserId, 'follow'
    FROM TargetUsers t JOIN UserFollowers uf ON t.UserId = uf.UserId
    WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION
    -- has_vote (Model)
    SELECT t.UserId, 'vote'
    FROM TargetUsers t JOIN ModelVotes mv ON t.UserId = mv.UserId
    WHERE mv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION
    -- has_vote (Dataset)
    SELECT t.UserId, 'vote'
    FROM TargetUsers t JOIN DatasetVotes dv ON t.UserId = dv.UserId
    WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION
    -- has_vote (ForumMessage)
    SELECT t.UserId, 'vote'
    FROM TargetUsers t JOIN ForumMessageVotes fmv ON t.UserId = fmv.FromUserId
    WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION
    -- has_reaction
    SELECT t.UserId, 'reaction'
    FROM TargetUsers t JOIN ForumMessageReactions fmr ON t.UserId = fmr.FromUserId
    WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
    UNION
    -- team 합류
    SELECT t.UserId, 'team'
    FROM TargetUsers t JOIN TeamMemberships tm ON t.UserId = tm.UserId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
),

D14_ActiveUsers AS (
    -- D+14 시점 C-Active = 위 활동 중 하나라도 있는 유저
    SELECT DISTINCT UserId FROM D14_Activity
),

-- ========================================================================
-- [STEP 3] 학습 대상 확정 (D+14 C-Active + 누수자 제외)
-- ========================================================================
LearnTargets AS (
    SELECT t.UserId, t.RegisterDate, t.CohortQuarter, t.Period, 
           t.D14_Date, t.D90_Date
    FROM TargetUsers t
    JOIN D14_ActiveUsers d14 ON t.UserId = d14.UserId
    WHERE t.UserId NOT IN (SELECT UserId FROM D_Leakers)
),

-- ========================================================================
-- [STEP 4] D+15 ~ D+90 사이 D 활동 발생 여부 (타깃)
-- ========================================================================
D_Targets AS (
    SELECT DISTINCT lt.UserId
    FROM LearnTargets lt
    JOIN (
        SELECT k.AuthorUserId AS UserId, k.MadePublicDate AS d_date 
        FROM Kernels k WHERE k.MadePublicDate IS NOT NULL
        UNION ALL
        SELECT tm.UserId, s.SubmissionDate
        FROM TeamMemberships tm JOIN Submissions s ON tm.TeamId = s.TeamId
        UNION ALL
        SELECT dt.OwnerUserId, dt.CreationDate FROM DatasetTasks dt
        UNION ALL
        SELECT dsv.CreatorUserId, dsv.CreationDate FROM DatasetVersions dsv
        UNION ALL
        SELECT fm.PostUserId, fm.PostDate FROM ForumMessages fm
        UNION ALL
        SELECT dts.SubmittedUserId, dts.CreationDate FROM DatasetTaskSubmissions dts
        UNION ALL
        SELECT mv.CreatorUserId, mv.CreationDate FROM ModelVersions mv
    ) d_acts ON lt.UserId = d_acts.UserId
    WHERE d_acts.d_date BETWEEN DATE_ADD(lt.RegisterDate, INTERVAL 15 DAY) 
                            AND lt.D90_Date
)

-- ========================================================================
-- 🏁 최종 출력: 학습 대상자 + 타깃 라벨
-- ========================================================================
SELECT 
    lt.UserId,
    lt.RegisterDate,
    lt.CohortQuarter,
    lt.Period,
    CASE WHEN dt.UserId IS NOT NULL THEN 1 ELSE 0 END AS target_d_conversion
FROM LearnTargets lt
LEFT JOIN D_Targets dt ON lt.UserId = dt.UserId;
