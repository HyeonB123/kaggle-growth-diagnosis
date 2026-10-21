-- ============================================================================
-- 00. 학습대상 테이블 (temp_target_users)
-- 4분기 코호트 중 D+14까지 비-D 활동(노트북 버전·팔로우·투표·반응·팀 합류)이 있고 D 활동은 없는 유저
-- 결과: 443,139명 (Golden 217,088 / Stagnation 226,051)
-- ============================================================================
DROP TABLE IF EXISTS temp_target_users;

CREATE TABLE temp_target_users AS
WITH Candidates AS (
    SELECT Id AS UserId, RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
        DATE_ADD(RegisterDate, INTERVAL 14 DAY) AS D14_Date
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),
-- D+14 이전에 이미 D활동 한 누수자 (제외 대상)
D_Leakers AS (
    SELECT DISTINCT c.UserId FROM Candidates c JOIN Kernels k ON c.UserId=k.AuthorUserId WHERE k.MadePublicDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN TeamMemberships tm ON c.UserId=tm.UserId JOIN Submissions s ON tm.TeamId=s.TeamId WHERE s.SubmissionDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN DatasetTasks dt ON c.UserId=dt.OwnerUserId WHERE dt.CreationDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN DatasetVersions dsv ON c.UserId=dsv.CreatorUserId WHERE dsv.CreationDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN ForumMessages fm ON c.UserId=fm.PostUserId WHERE fm.PostDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN DatasetTaskSubmissions dts ON c.UserId=dts.SubmittedUserId WHERE dts.CreationDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN ModelVersions mv ON c.UserId=mv.CreatorUserId WHERE mv.CreationDate BETWEEN c.RegisterDate AND c.D14_Date
),
-- D+14 시점 C-Active (활동 1개 이상)
D14_ActiveUsers AS (
    SELECT DISTINCT c.UserId FROM Candidates c JOIN KernelVersions kv ON c.UserId=kv.AuthorUserId WHERE kv.CreationDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN UserFollowers uf ON c.UserId=uf.UserId WHERE uf.CreationDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN ModelVotes mv ON c.UserId=mv.UserId WHERE mv.VoteDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN DatasetVotes dv ON c.UserId=dv.UserId WHERE dv.VoteDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN ForumMessageVotes fmv ON c.UserId=fmv.FromUserId WHERE fmv.VoteDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN ForumMessageReactions fmr ON c.UserId=fmr.FromUserId WHERE fmr.ReactionDate BETWEEN c.RegisterDate AND c.D14_Date
    UNION SELECT DISTINCT c.UserId FROM Candidates c JOIN TeamMemberships tm ON c.UserId=tm.UserId WHERE tm.RequestDate BETWEEN c.RegisterDate AND c.D14_Date
)
SELECT c.UserId, c.RegisterDate, c.CohortQuarter, c.Period, c.D14_Date
FROM Candidates c
JOIN D14_ActiveUsers d14 ON c.UserId = d14.UserId
WHERE c.UserId NOT IN (SELECT UserId FROM D_Leakers);

ALTER TABLE temp_target_users ADD INDEX idx_tt_user (UserId);
ALTER TABLE temp_target_users ADD INDEX idx_tt_user_dates (UserId, RegisterDate, D14_Date);
-- 검증: SELECT COUNT(*) FROM temp_target_users;  -- ≈ 443,139
--       SELECT Period, COUNT(*) FROM temp_target_users GROUP BY Period;  -- Golden ~217K / Stag ~226K
