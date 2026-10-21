-- ============================================================================
-- 01. 코호트 정의 + 가설 검증 SQL
-- Meta Kaggle QAU 정체 분석 / DBeaver(MySQL)에서 실행
-- 코호트: 4분기 통일 확정 (황금기 2020-Q1~Q4 / 침체기 2024-Q3~2025-Q2)
-- ============================================================================

-- ############################################################################
-- [공통] 코호트 정의 CTE — 모든 가설검증 쿼리의 앞에 붙여 사용
-- ############################################################################
-- WITH TargetUsers AS (
--     SELECT
--         Id AS UserId,
--         RegisterDate,
--         CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
--         CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
--         DATE_ADD(RegisterDate, INTERVAL 90 DAY) AS D90_Date
--     FROM Users
--     WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')  -- 황금기 4분기
--        OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')  -- 침체기 4분기
-- )

-- 활동 분류 체계 (Process Mining 기준, 14개 활동 → 9개 카테고리)
--  Registration        : Users (신규 유입, 시작점)
--  Light_Active        : UserFollowers, ModelVotes, DatasetVotes, ForumMessageVotes, ForumMessageReactions
--  Team_Formation      : TeamMemberships (팀 생성/합류)
--  Competition_Submission : Submissions (팀 경유)
--  Kernel_Production   : Kernels, KernelVersions
--  Model_Production    : Models, ModelVersions
--  Dataset_Production  : Datasets, DatasetVersions, DatasetTasks, DatasetTaskSubmissions
--  Forum_Production    : ForumMessages


-- ############################################################################
-- [가설1-1] Bounce Rate 분석 (LTE90: 90일 내 활동 횟수)
--   순수 눈팅 이탈(Bounce) = 가입 후 90일간 1회 이하 활동
--   결과: 황금기 무활동률 ~73% vs 침체기 ~91% (5중 증거 중 ①)
-- ############################################################################
WITH TargetUsers AS (
    SELECT
        Id AS UserId, RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
        DATE_ADD(RegisterDate, INTERVAL 90 DAY) AS D90_Date
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),
-- 90일 내 활동 1건이라도 있는 유저 (14개 활동 UNION)
ActiveUsers AS (
    SELECT t.UserId FROM TargetUsers t JOIN UserFollowers uf ON t.UserId=uf.UserId WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN ModelVotes mv ON t.UserId=mv.UserId WHERE mv.VoteDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN DatasetVotes dv ON t.UserId=dv.UserId WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN ForumMessageVotes fmv ON t.UserId=fmv.FromUserId WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN ForumMessageReactions fmr ON t.UserId=fmr.FromUserId WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN TeamMemberships tm ON t.UserId=tm.UserId WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN KernelVersions kv ON t.UserId=kv.AuthorUserId WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN ForumMessages fm ON t.UserId=fm.PostUserId WHERE fm.PostDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN DatasetVersions dsv ON t.UserId=dsv.CreatorUserId WHERE dsv.CreationDate BETWEEN t.RegisterDate AND t.D90_Date
    UNION SELECT t.UserId FROM TargetUsers t JOIN ModelVersions mdv ON t.UserId=mdv.CreatorUserId WHERE mdv.CreationDate BETWEEN t.RegisterDate AND t.D90_Date
)
SELECT
    t.Period,
    COUNT(*) AS TotalUsers,
    COUNT(a.UserId) AS ActiveUsers,
    COUNT(*) - COUNT(a.UserId) AS BounceUsers,
    ROUND((COUNT(*) - COUNT(a.UserId)) / COUNT(*) * 100, 2) AS BounceRate_Pct
FROM TargetUsers t
LEFT JOIN (SELECT DISTINCT UserId FROM ActiveUsers) a ON t.UserId = a.UserId
GROUP BY t.Period;


-- ############################################################################
-- [가설1-2] 첫 활동 분석 (속도 + 카테고리 분포)
--   각 유저의 '가장 빠른 첫 활동'의 시점과 종류 식별
--   결과: 첫 활동 카테고리 분포(체리피커 vs 시도자), 가입~첫활동 시간
-- ############################################################################
WITH TargetUsers AS (
    SELECT
        Id AS UserId, RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),
FirstActions AS (
    SELECT t.UserId, MIN(uf.CreationDate) AS FirstTime, 'Light_Active' AS Category
    FROM TargetUsers t JOIN UserFollowers uf ON t.UserId=uf.UserId WHERE uf.CreationDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(mv.VoteDate), 'Light_Active' FROM TargetUsers t JOIN ModelVotes mv ON t.UserId=mv.UserId WHERE mv.VoteDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(dv.VoteDate), 'Light_Active' FROM TargetUsers t JOIN DatasetVotes dv ON t.UserId=dv.UserId WHERE dv.VoteDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(fmv.VoteDate), 'Light_Active' FROM TargetUsers t JOIN ForumMessageVotes fmv ON t.UserId=fmv.FromUserId WHERE fmv.VoteDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(fmr.ReactionDate), 'Light_Active' FROM TargetUsers t JOIN ForumMessageReactions fmr ON t.UserId=fmr.FromUserId WHERE fmr.ReactionDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(tm.RequestDate), 'Team_Formation' FROM TargetUsers t JOIN TeamMemberships tm ON t.UserId=tm.UserId WHERE tm.RequestDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(kv.CreationDate), 'Kernel_Production' FROM TargetUsers t JOIN KernelVersions kv ON t.UserId=kv.AuthorUserId WHERE kv.CreationDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(fm.PostDate), 'Forum_Production' FROM TargetUsers t JOIN ForumMessages fm ON t.UserId=fm.PostUserId WHERE fm.PostDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(dsv.CreationDate), 'Dataset_Production' FROM TargetUsers t JOIN DatasetVersions dsv ON t.UserId=dsv.CreatorUserId WHERE dsv.CreationDate >= t.RegisterDate GROUP BY t.UserId
    UNION ALL SELECT t.UserId, MIN(mdv.CreationDate), 'Model_Production' FROM TargetUsers t JOIN ModelVersions mdv ON t.UserId=mdv.CreatorUserId WHERE mdv.CreationDate >= t.RegisterDate GROUP BY t.UserId
),
UserFirstAction AS (
    SELECT UserId, Category AS FirstCategory, FirstTime,
           ROW_NUMBER() OVER (PARTITION BY UserId ORDER BY FirstTime ASC) AS rn
    FROM FirstActions WHERE FirstTime IS NOT NULL
)
SELECT
    t.UserId, t.CohortQuarter, t.Period, t.RegisterDate,
    ufa.FirstCategory, ufa.FirstTime,
    TIMESTAMPDIFF(HOUR, t.RegisterDate, ufa.FirstTime) AS HoursToFirstAction,
    TIMESTAMPDIFF(DAY,  t.RegisterDate, ufa.FirstTime) AS DaysToFirstAction
FROM TargetUsers t
LEFT JOIN UserFirstAction ufa ON t.UserId = ufa.UserId AND ufa.rn = 1;
-- → Python에서 Period별 FirstCategory 분포, 1H내 활동률, 평균 DaysToFirstAction 집계


-- ############################################################################
-- [가설2] 그룹(A/B/C/D) 분류 + C→D 전환율
--   D 정의: 노트북 공개 / 대회제출 / 데이터셋·모델·포럼 생산 등 (의미있는 산출)
--   C 정의: 팀 합류 OR 노트북 10줄 이상 작성 (시도했으나 미완)
--   PureC = C 조건 충족 & D 미달성
--   핵심 발견: C→D 전환율은 침체기(37%)가 황금기(28%)보다 오히려 높음
--             → "시스템 병목" 기각 → "모집단 변화 + 자연선택"(2단 양극화)로 재해석
-- ############################################################################
WITH TargetUsers AS (
    SELECT
        Id AS UserId, RegisterDate,
        CONCAT(YEAR(RegisterDate), '-Q', QUARTER(RegisterDate)) AS CohortQuarter,
        CASE WHEN RegisterDate < '2022-01-01' THEN 'Golden' ELSE 'Stagnation' END AS Period,
        DATE_ADD(RegisterDate, INTERVAL 90 DAY) AS D90_Date
    FROM Users
    WHERE (RegisterDate >= '2020-01-01' AND RegisterDate < '2021-01-01')
       OR (RegisterDate >= '2024-07-01' AND RegisterDate < '2025-07-01')
),
GroupD_Users AS (
    SELECT k.AuthorUserId AS UserId FROM Kernels k JOIN TargetUsers u ON k.AuthorUserId=u.UserId WHERE k.MadePublicDate <= u.D90_Date
    UNION SELECT tm.UserId FROM TargetUsers u JOIN TeamMemberships tm ON u.UserId=tm.UserId JOIN Submissions s ON tm.TeamId=s.TeamId WHERE s.SubmissionDate <= u.D90_Date
    UNION SELECT dt.OwnerUserId FROM DatasetTasks dt JOIN TargetUsers u ON dt.OwnerUserId=u.UserId WHERE dt.CreationDate <= u.D90_Date
    UNION SELECT dsv.CreatorUserId FROM DatasetVersions dsv JOIN TargetUsers u ON dsv.CreatorUserId=u.UserId WHERE dsv.CreationDate <= u.D90_Date
    UNION SELECT fm.PostUserId FROM ForumMessages fm JOIN TargetUsers u ON fm.PostUserId=u.UserId WHERE fm.PostDate <= u.D90_Date
    UNION SELECT dts.SubmittedUserId FROM DatasetTaskSubmissions dts JOIN TargetUsers u ON dts.SubmittedUserId=u.UserId WHERE dts.CreationDate <= u.D90_Date
    UNION SELECT mv.CreatorUserId FROM ModelVersions mv JOIN TargetUsers u ON mv.CreatorUserId=u.UserId WHERE mv.CreationDate <= u.D90_Date
),
GroupC_Users AS (
    SELECT tm.UserId FROM TargetUsers u JOIN TeamMemberships tm ON u.UserId=tm.UserId WHERE tm.RequestDate <= u.D90_Date
    UNION SELECT kv.AuthorUserId FROM KernelVersions kv JOIN TargetUsers u ON kv.AuthorUserId=u.UserId WHERE kv.CreationDate <= u.D90_Date AND kv.TotalLines >= 10
),
PureC_Users AS (
    SELECT c.UserId FROM (SELECT DISTINCT UserId FROM GroupC_Users) c
    WHERE c.UserId NOT IN (SELECT DISTINCT UserId FROM GroupD_Users)
)
SELECT
    t.Period,
    COUNT(DISTINCT pc.UserId) AS PureC_Count,
    COUNT(DISTINCT CASE WHEN d.UserId IS NOT NULL THEN gc.UserId END) AS ... -- 전환율은 아래 주석 로직 참고
FROM TargetUsers t
LEFT JOIN PureC_Users pc ON t.UserId = pc.UserId
LEFT JOIN (SELECT DISTINCT UserId FROM GroupC_Users) gc ON t.UserId = gc.UserId
LEFT JOIN (SELECT DISTINCT UserId FROM GroupD_Users) d ON t.UserId = d.UserId
GROUP BY t.Period;
-- 주: C→D 전환율 = (C조건 충족하고 D도 달성한 유저) / (C조건 충족 전체).
--     위 마지막 SELECT는 뼈대만. 실제로는 'C경험자' 중 D달성 비율을 Period별로 계산.
--     C-Active 분리(단순 팀합류 비활성 제외)까지 반영하면 C-Active 비율 19.5%→14.6%.

-- ============================================================================
-- 가설1 최종: 수질저하 채택 (5중 증거)
--   ① 무활동률 73%→91%  ② 대회시도율(Team) 16.98%→3.85%
--   ③ 빠른대회참여 0.24%→0.08%  ④ 진짜대회완주 ~1.7%→~0.4%  ⑤ 1H내활동 8.78%→2.81%
-- 가설2 최종: 시스템병목 기각 → 2단 양극화 모델 (모집단변화+자연선택)
-- ============================================================================
