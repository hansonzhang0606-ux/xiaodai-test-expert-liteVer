-- 时间节省追踪 Skill v5.8 -> v5.9 数据库升级脚本
-- 管理员审核后，在已经选定的目标数据库连接中手动执行。
-- 本脚本只新增 AI 预估节省工时列，不修改旧字段、索引、唯一键或历史数据。

SET @v59_column_exists = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'agent_time_tracking'
      AND COLUMN_NAME = 'ai_estimated_time_saved_hours'
);

SET @v59_upgrade_sql = IF(
    @v59_column_exists = 0,
    'ALTER TABLE `agent_time_tracking` ADD COLUMN `ai_estimated_time_saved_hours` DECIMAL(10,2) NULL COMMENT ''AI预估本环节可节省工时（小时）'' AFTER `time_saved_hours`',
    'SELECT ''ai_estimated_time_saved_hours column already exists'' AS message'
);

PREPARE v59_upgrade_statement FROM @v59_upgrade_sql;
EXECUTE v59_upgrade_statement;
DEALLOCATE PREPARE v59_upgrade_statement;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'agent_time_tracking'
  AND COLUMN_NAME = 'ai_estimated_time_saved_hours';

