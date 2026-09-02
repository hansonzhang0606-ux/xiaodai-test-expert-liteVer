# 时间追踪钩子

本文件只定义何时接入时间 Skill，不复制其详细业务规则。

## 触发范围

只处理 `config/step_mapping.yaml` 中 `tracking_code` 非空的环节：01、02、04、06、07。环节 3 和 5 不记录。

## 前置：历史步骤时间补录（v6.0，先于本步骤时间钩子执行）

测试人员可能在某环节尚未进入「完成」态时就跳到下一环节（例如环节 ① 仍在迭代就跳到 ②），
导致该环节的节省时间从未被询问与记录。因此：

- **进入下一个环节后（无论上一环节是否进入「完成」态），立即调用** `time-tracking-skill/scripts/check_missing_time_records.py`
  以「当前环节」为 `current-step-code` 检查上一环节是否已记录；若上一环节漏记，先补录再继续；
- 对 `tracking_code` 非空的环节（01/02/04/06/07），**在触发本步骤时间钩子之前也必须做补录检查**：

1. 调用平级检测脚本（业务线、姓名、用户故事取会话缓存值，不重复询问）：

   ```bash
   python time-tracking-skill/scripts/check_missing_time_records.py \
     --biz-line "{业务线中文名}" \
     --employee "{姓名}" \
     --user-story "{用户故事}" \
     --current-step-code "{本步骤 tracking_code}"
   ```

2. `missing` 非空时，**按编号升序逐个补录**，每个缺失环节完整走一遍：
   展示参考区间 → 独立生成 `ai_estimated_time_saved_hours`（补录环节同样生成，
   且必须在展示参考区间、询问反馈之前完成）→ 询问反馈（`采纳` / 具体数值 / `跳过`）
   → 二次确认 → 只调用 `xiaodai-lite-orchestrator/scripts/secure_record_time_saved.py`
   写入 `records.jsonl`；补录环节无本轮智能体耗时，`agent_duration_minutes` 留空。
3. 人员回复“跳过” → 该环节不记录，回复中标注「环节 X 已跳过、未记录」，继续下一个缺失环节，**不阻塞流程**。
4. 全部缺失环节处理完毕后，才进入本步骤的正常时间反馈流程（见下方固定顺序）。
5. 脚本调用失败（非 0 退出码）→ 说明原因并跳过补录，直接进入正常流程，不阻塞测试工作。

详细规则见平级 `time-tracking-skill/prompts/time_tracking.md` 第零章。

## 固定顺序

1. 业务产物完成并展示后，使用环节开始/结束时间计算 `agent_duration_minutes`。
2. 在展示参考区间和询问人员反馈之前，基于本次输入规模、复杂度和产物独立生成 `ai_estimated_time_saved_hours`，保留两位小数；无法可靠估算时用 `null`。
3. 完整读取平级 `time-tracking-skill/prompts/time_tracking.md`，按 v6.0 展示参考区间并收集用户故事和实际反馈。
4. “采纳”使用参考范围中间值。
5. 最多追问两次仍无实际时间时，使用参考范围中间值，备注固定为“用户未反馈，采用参考中间值”，不再要求第三次确认。
6. 明确反馈或“采纳”按 v6.0 做二次确认；确认后只调用 `xiaodai-lite-orchestrator/scripts/secure_record_time_saved.py`，同时传入 AI 预估与智能体耗时字段。该入口会重新执行 MySQL 花名册精确匹配，失败即终止且不展示名单；禁止由三端专家直接调用底层 `time-tracking-skill/scripts/record_time_saved.py`。
7. 保存完成后才展示下一步选项。

## 主链路完成核验（v6.1）

当主链路全部环节（01 需求整理 → 04 测试点 → 06 用例）均执行完毕后，或会话收尾时，
**必须对每个已执行用户故事做一次端到端同步核验**，确保「本地已记录」与「MySQL 已同步」一致：

1. 本地记录核查（缺记录先补录）：
   ```bash
   python time-tracking-skill/scripts/check_missing_time_records.py \
     --biz-line "{业务线}" --employee "{姓名}" \
     --user-story "{用户故事}" --steps "01,04,06"
   ```
   `missing` 非空 → 按编号升序逐个补录（走正常时间反馈流程），直到本地 01/04/06 齐全。

2. MySQL 同步核查（未同步立即补同步）：
   ```bash
   python time-tracking-skill/scripts/verify_story_sync.py \
     --biz-line "{业务线}" --employee "{姓名}" \
     --user-story "{用户故事}" --steps "01,04,06"
   ```
   `unsynced` 非空 → 说明本地有记录但 MySQL 未入库（如自动同步失败），立即执行
   `sync_to_mysql.py --biz-line "{业务线}"` 补同步，并报告最终同步结果。

3. 只有当 `check_missing` 的 `missing` 为空 **且** `verify_story_sync` 的 `unsynced` 为空时，
   才向测试人员确认「本故事节省时间数据已全部同步完成」。任一非空告警则不得宣称完成。

## 数据隔离

- `ai_estimated_time_saved_hours` 是模型估算，只写同名字段。
- `time_saved_hours` 只能来自人员明确反馈、人员采纳的参考中间值，或两次未反馈后的参考中间值。
- 记录使用会话缓存的姓名、业务线和用户故事，不重复索要已知字段。
- **v6.1 提交后立即同步**：`secure_record_time_saved.py` 在本地 `records.jsonl` 落盘成功后已内置自动调用 `sync_to_mysql.py` 同步到 MySQL，不再依赖计划任务的时序。若自动同步失败，本地记录仍保留，会由计划任务（早/午/晚）重试，并明确告警。

## 同步去重规则（v6.2）

`sync_to_mysql.py` 将本地 `records.jsonl` 推送到 MySQL `agent_time_tracking` 时，采用**两层去重**，避免重跑同步脚本导致的重复入库：

### 第一层：record_key 幂等（同一条本地记录重同步）
- 唯一键 `record_key = MD5(biz_line_code|employee|user_story|step_code|timestamp秒)`。
- 若 `record_key` 已存在，走 `INSERT ... ON DUPLICATE KEY UPDATE`，仅更新其余字段（如 `time_saved_hours`、`updated_at`），**不新增行**。
- 作用：同一份本地记录被自动同步、计划任务、手动补同步多次触发时，保持单行、仅刷新。

### 第二层：业务字段组合去重（不同 timestamp 但业务内容相同）
- 当 `record_key` 不存在（即本次 timestamp 与库内任意记录都不同，疑似「新」记录）时，进一步按业务字段组合判定：
  `biz_line_code` + `employee` + `user_story_code` + `step_code` + `time_saved_hours` 五个字段**完全相同**即视为业务重复。
- 命中的记录返回 `skipped_dup`，**不入库**，控制台打印 `⏭️ 跳过(业务重复)`。
- 作用：修复「同一环节重跑生成不同 timestamp、绕过 record_key 而多插一行」的缺陷（如环节 06 重复提交、自动同步与计划任务时序叠加等场景）。

### 同步结果统计
- 脚本结束时输出：`同步完成: 成功 X 条 / 跳过(重复) Y 条 / 失败 Z 条 / 合计 N 条`。
- `跳过(重复)` 即第二层业务去重命中数；`失败` 为非预期异常（需排查，不得忽略）。

### 约束与盲区
- 去重**不依赖** `created_at`（该字段为 DBA 加的审计列，UTC 时区，不参与去重判定）。
- 盲区：仅能识别「库已存在相同业务内容」；若库内当前无该组合（如首次同步前），则正常入库。删除已有重复数据仍须走 DBA（appuser 无 DELETE 权限）。
- 建议：主链路完成核验（见上节）以 `check_missing` + `verify_story_sync` 双空作为完成判据；本去重规则仅防止「重复同步多插」，不替代端到端核验。
