-- ============================================================================
-- 05. df2_b: 활동 카테고리 수, 섀넌 엔트로피, D+14 기준
-- 활동이 1개 이상인 유저만 출력 → Python에서 left merge 후 0으로 채움
-- ============================================================================
WITH CategoryCounts AS (
    SELECT t.UserId, 'kernel' AS cat, COUNT(*) AS cnt
    FROM temp_target_users t JOIN KernelVersions kv ON t.UserId = kv.AuthorUserId
    WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
    UNION ALL
    SELECT t.UserId, 'forum', COUNT(*)
    FROM temp_target_users t JOIN ForumMessages fm ON t.UserId = fm.PostUserId
    WHERE fm.PostDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
    UNION ALL
    SELECT v.UserId, 'vote', COUNT(*)
    FROM (
        SELECT t.UserId FROM temp_target_users t JOIN ModelVotes mv ON t.UserId = mv.UserId 
        WHERE mv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
        UNION ALL
        SELECT t.UserId FROM temp_target_users t JOIN DatasetVotes dv ON t.UserId = dv.UserId 
        WHERE dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
        UNION ALL
        SELECT t.UserId FROM temp_target_users t JOIN ForumMessageVotes fmv ON t.UserId = fmv.FromUserId 
        WHERE fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS v GROUP BY v.UserId
    UNION ALL
    SELECT t.UserId, 'follow', COUNT(*)
    FROM temp_target_users t JOIN UserFollowers uf ON t.UserId = uf.UserId
    WHERE uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
    UNION ALL
    SELECT t.UserId, 'reaction', COUNT(*)
    FROM temp_target_users t JOIN ForumMessageReactions fmr ON t.UserId = fmr.FromUserId
    WHERE fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
    UNION ALL
    SELECT t.UserId, 'team', COUNT(*)
    FROM temp_target_users t JOIN TeamMemberships tm ON t.UserId = tm.UserId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),
UserCategoryTotal AS (
    SELECT UserId, SUM(cnt) AS total_cnt
    FROM CategoryCounts GROUP BY UserId
)
SELECT 
    cc.UserId,
    COUNT(DISTINCT cc.cat) AS n_categories_d14,
    ROUND(
        -SUM(
            (cc.cnt / NULLIF(uct.total_cnt, 0)) * 
            LN(NULLIF(cc.cnt / NULLIF(uct.total_cnt, 0), 0))
        ), 3
    ) AS shannon_entropy_d14
FROM CategoryCounts cc
JOIN UserCategoryTotal uct ON cc.UserId = uct.UserId
GROUP BY cc.UserId;
