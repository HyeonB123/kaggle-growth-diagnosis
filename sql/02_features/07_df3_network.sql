-- ============================================================================
-- 07. df3: 네트워크(받은 영향력) + 메타 피처, D+14 기준
-- DatasetVotes는 DatasetVersionId로 연결 (Datasets → DatasetVersions → DatasetVotes)
-- UserFollowers: UserId = 팔로우한 사람, FollowingUserId = 팔로우 받은 사람
-- ============================================================================
WITH TargetUsers AS (
    SELECT 
        Id AS UserId,
        RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
        DAYOFWEEK(RegisterDate) AS register_day_of_week,
        DATE_ADD(RegisterDate, INTERVAL 14 DAY) AS D14_Date
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),

-- ========================================================================
-- 받은 팔로워 수 (다른 사람이 나를 팔로우)
-- UserFollowers 구조: UserId=팔로우한 사람, FollowingUserId=팔로우 받은 사람 (팔로워 상위: cdeotte 등)
-- ========================================================================
FollowersReceived AS (
    SELECT t.UserId, COUNT(*) AS followers_received_d14
    FROM TargetUsers t 
    JOIN UserFollowers uf ON t.UserId = uf.FollowingUserId
    WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 내가 팔로우한 사람 수 (이미 첫 번째 쿼리에 있지만 일관성 위해 포함)
-- ========================================================================
FollowersGiven AS (
    SELECT t.UserId, COUNT(*) AS followers_given_d14
    FROM TargetUsers t 
    JOIN UserFollowers uf ON t.UserId = uf.UserId
    WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 받은 포럼 메시지 투표 수 (내 글에 받은 vote)
-- ========================================================================
ForumVotesReceived AS (
    SELECT t.UserId, COUNT(*) AS forum_votes_received_d14
    FROM TargetUsers t 
    JOIN ForumMessages fm ON t.UserId = fm.PostUserId
    JOIN ForumMessageVotes fmv ON fm.Id = fmv.ForumMessageId
    WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 받은 포럼 리액션 수 (내 글에 받은 reaction)
-- ========================================================================
ForumReactionsReceived AS (
    SELECT t.UserId, COUNT(*) AS forum_reactions_received_d14
    FROM TargetUsers t 
    JOIN ForumMessages fm ON t.UserId = fm.PostUserId
    JOIN ForumMessageReactions fmr ON fm.Id = fmr.ForumMessageId
    WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),

-- ========================================================================
-- 받은 데이터셋 투표 수
-- ========================================================================
DatasetVotesReceived AS (
    SELECT t.UserId, COUNT(*) AS dataset_votes_received_d14
    FROM TargetUsers t 
    JOIN Datasets d ON t.UserId = d.CreatorUserId
    JOIN DatasetVersions dsv ON d.Id = dsv.DatasetId
    JOIN DatasetVotes dv ON dsv.Id = dv.DatasetVersionId
    WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
)

-- ========================================================================
-- 🏁 최종 출력
-- ========================================================================
SELECT 
    t.UserId,
    
    -- 메타 피처
    t.CohortQuarter,
    t.Period,
    t.register_day_of_week,
    
    -- Network 피처 (받은 영향력)
    COALESCE(fr.followers_received_d14, 0) AS followers_received_d14,
    COALESCE(fg.followers_given_d14, 0) AS followers_given_d14,
    COALESCE(fvr.forum_votes_received_d14, 0) AS forum_votes_received_d14,
    COALESCE(frr.forum_reactions_received_d14, 0) AS forum_reactions_received_d14,
    COALESCE(dvr.dataset_votes_received_d14, 0) AS dataset_votes_received_d14,
    
    -- 종합 영향력 점수 (파생)
    COALESCE(fr.followers_received_d14, 0) + 
    COALESCE(fvr.forum_votes_received_d14, 0) + 
    COALESCE(dvr.dataset_votes_received_d14, 0) AS total_influence_d14
    
FROM TargetUsers t
LEFT JOIN FollowersReceived fr ON t.UserId = fr.UserId
LEFT JOIN FollowersGiven fg ON t.UserId = fg.UserId
LEFT JOIN ForumVotesReceived fvr ON t.UserId = fvr.UserId
LEFT JOIN ForumReactionsReceived frr ON t.UserId = frr.UserId
LEFT JOIN DatasetVotesReceived dvr ON t.UserId = dvr.UserId;
