-- ============================================================================
-- 06. df2_c: 노트북 품질(줄 수·버전 수), 팀 크기, D+14 기준
-- 02_helper_tables.sql 선행 필요. 노트북·팀 활동이 있는 유저만 출력
-- ============================================================================
WITH 
KernelQuality AS (
    SELECT 
        t.UserId,
        MAX(sv.version_per_script) AS max_kernel_versions_d14,
        ROUND(AVG(sv.version_per_script), 2) AS avg_kernel_versions_d14
    FROM temp_target_users t
    JOIN KernelVersions kv ON t.UserId = kv.AuthorUserId
    JOIN temp_script_versions sv ON kv.ScriptId = sv.ScriptId
    WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),
KernelCounts AS (
    SELECT 
        t.UserId,
        COUNT(DISTINCT k.Id) AS total_kernel_count,
        SUM(CASE WHEN k.MadePublicDate BETWEEN t.RegisterDate AND t.D14_Date 
                 THEN 1 ELSE 0 END) AS public_kernel_count
    FROM temp_target_users t
    JOIN Kernels k ON t.UserId = k.AuthorUserId
    WHERE k.CreationDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
),
TeamSizeStats AS (
    SELECT 
        t.UserId,
        ROUND(AVG(ts.team_size), 1) AS avg_team_size,
        MAX(ts.team_size) AS max_team_size
    FROM temp_target_users t
    JOIN TeamMemberships tm ON t.UserId = tm.UserId
    JOIN temp_team_sizes ts ON tm.TeamId = ts.TeamId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
    GROUP BY t.UserId
)
SELECT 
    t.UserId,
    COALESCE(kq.max_kernel_versions_d14, 0) AS max_kernel_versions_d14,
    COALESCE(kq.avg_kernel_versions_d14, 0) AS avg_kernel_versions_d14,
    COALESCE(kc.total_kernel_count, 0) AS total_kernel_count,
    COALESCE(kc.public_kernel_count, 0) AS public_kernel_count,
    CASE 
        WHEN COALESCE(kc.total_kernel_count, 0) > 0 
        THEN ROUND(kc.public_kernel_count * 1.0 / kc.total_kernel_count, 3)
        ELSE 0
    END AS public_kernel_ratio,
    COALESCE(tss.avg_team_size, 0) AS avg_team_size,
    COALESCE(tss.max_team_size, 0) AS max_team_size
FROM temp_target_users t
LEFT JOIN KernelQuality kq ON t.UserId = kq.UserId
LEFT JOIN KernelCounts kc ON t.UserId = kc.UserId
LEFT JOIN TeamSizeStats tss ON t.UserId = tss.UserId
WHERE kq.UserId IS NOT NULL 
   OR kc.UserId IS NOT NULL 
   OR tss.UserId IS NOT NULL;
