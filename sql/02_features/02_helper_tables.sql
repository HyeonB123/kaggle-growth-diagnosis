-- ============================================================================
-- 02. 피처용 보조 테이블 (temp_relevant_scripts, temp_script_versions, temp_team_sizes)
-- 학습대상의 노트북·팀만 골라 버전 수와 팀 크기를 미리 계산 (df2_c 속도 개선용)
-- TODO: 버전 수·팀 크기에 날짜 제한이 없어 D+14 이후 정보가 섞임 (docs/decisions.md 검토 대기)
-- ============================================================================
-- ════════════════════════════════════════════════════
-- 2단계: 학습 대상자의 노트북만 추출 (전체 X)
-- ════════════════════════════════════════════════════
DROP TABLE IF EXISTS temp_relevant_scripts;

CREATE TABLE temp_relevant_scripts AS
SELECT DISTINCT kv.ScriptId
FROM temp_target_users t
JOIN KernelVersions kv ON t.UserId = kv.AuthorUserId
WHERE kv.CreationDate BETWEEN t.RegisterDate AND t.D14_Date;

ALTER TABLE temp_relevant_scripts ADD INDEX idx_scripts (ScriptId);

-- ════════════════════════════════════════════════════
-- 3단계: 학습 대상자 노트북의 버전 수만 계산 (전체 X)
-- ════════════════════════════════════════════════════
DROP TABLE IF EXISTS temp_script_versions;

CREATE TABLE temp_script_versions AS
SELECT kv.ScriptId, COUNT(*) AS version_per_script
FROM KernelVersions kv
JOIN temp_relevant_scripts rs ON kv.ScriptId = rs.ScriptId
GROUP BY kv.ScriptId;

ALTER TABLE temp_script_versions ADD INDEX idx_sv_script (ScriptId);

-- ════════════════════════════════════════════════════
-- 4단계: 학습 대상자가 속한 팀만 추출 (전체 X)
-- ════════════════════════════════════════════════════
DROP TABLE IF EXISTS temp_team_sizes;

CREATE TABLE temp_team_sizes AS
SELECT TeamId, COUNT(*) AS team_size
FROM TeamMemberships
WHERE TeamId IN (
    SELECT DISTINCT tm.TeamId
    FROM temp_target_users t
    JOIN TeamMemberships tm ON t.UserId = tm.UserId
    WHERE tm.RequestDate BETWEEN t.RegisterDate AND t.D14_Date
)
GROUP BY TeamId;

ALTER TABLE temp_team_sizes ADD INDEX idx_ts_team (TeamId);
