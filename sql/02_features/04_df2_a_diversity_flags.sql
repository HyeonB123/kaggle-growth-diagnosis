-- ============================================================================
-- 04. df2_a: 활동 종류별 보유 여부 (has_*), D+14 기준
-- EXISTS로 확인 (LEFT JOIN 여러 개는 행이 곱해져 느려짐)
-- ============================================================================
SELECT 
    t.UserId,
    
    -- Diversity Binary Flags (각각 독립 EXISTS - 카르테시안 폭발 방지)
    EXISTS (
        SELECT 1 FROM KernelVersions kv 
        WHERE kv.AuthorUserId = t.UserId 
          AND kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_kernel,
    
    EXISTS (
        SELECT 1 FROM ForumMessages fm 
        WHERE fm.PostUserId = t.UserId 
          AND fm.PostDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_forum,
    
    (EXISTS (
        SELECT 1 FROM ModelVotes mv 
        WHERE mv.UserId = t.UserId 
          AND mv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    ) OR EXISTS (
        SELECT 1 FROM DatasetVotes dv 
        WHERE dv.UserId = t.UserId 
          AND dv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    ) OR EXISTS (
        SELECT 1 FROM ForumMessageVotes fmv 
        WHERE fmv.FromUserId = t.UserId 
          AND fmv.VoteDate BETWEEN t.RegisterDate AND t.D14_Date
    )) AS has_vote,
    
    EXISTS (
        SELECT 1 FROM UserFollowers uf 
        WHERE uf.UserId = t.UserId 
          AND uf.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_follow,
    
    EXISTS (
        SELECT 1 FROM ForumMessageReactions fmr 
        WHERE fmr.FromUserId = t.UserId 
          AND fmr.ReactionDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_reaction,
    
    EXISTS (
        SELECT 1 FROM TeamMemberships tm 
        WHERE tm.UserId = t.UserId 
          AND tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_team,
    
    EXISTS (
        SELECT 1 FROM TeamMemberships tm 
        JOIN Submissions s ON tm.TeamId = s.TeamId
        WHERE tm.UserId = t.UserId 
          AND s.SubmissionDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_submission,
    
    EXISTS (
        SELECT 1 FROM DatasetVersions dsv 
        WHERE dsv.CreatorUserId = t.UserId 
          AND dsv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    ) AS has_dataset
    
FROM temp_target_users t;
