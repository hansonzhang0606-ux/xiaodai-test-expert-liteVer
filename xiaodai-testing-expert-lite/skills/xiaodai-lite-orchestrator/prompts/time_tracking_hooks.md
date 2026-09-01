# 时间追踪钩子

本文件只定义何时接入时间 Skill，不复制其详细业务规则。

## 触发范围

只处理 `config/step_mapping.yaml` 中 `tracking_code` 非空的环节：01、02、04、06、07。环节 3 和 5 不记录。

## 固定顺序

1. 业务产物完成并展示后，使用环节开始/结束时间计算 `agent_duration_minutes`。
2. 在展示参考区间和询问人员反馈之前，基于本次输入规模、复杂度和产物独立生成 `ai_estimated_time_saved_hours`，保留两位小数；无法可靠估算时用 `null`。
3. 完整读取平级 `time-tracking-skill/prompts/time_tracking.md`，按 v5.9 展示参考区间并收集用户故事和实际反馈。
4. “采纳”使用参考范围中间值。
5. 最多追问两次仍无实际时间时，使用参考范围中间值，备注固定为“用户未反馈，采用参考中间值”，不再要求第三次确认。
6. 明确反馈或“采纳”按 v5.9 做二次确认；确认后只调用 `xiaodai-lite-orchestrator/scripts/secure_record_time_saved.py`，同时传入 AI 预估与智能体耗时字段。该入口会重新执行 MySQL 花名册精确匹配，失败即终止且不展示名单；禁止由三端专家直接调用底层 `time-tracking-skill/scripts/record_time_saved.py`。
7. 保存完成后才展示下一步选项。

## 数据隔离

- `ai_estimated_time_saved_hours` 是模型估算，只写同名字段。
- `time_saved_hours` 只能来自人员明确反馈、人员采纳的参考中间值，或两次未反馈后的参考中间值。
- 记录使用会话缓存的姓名、业务线和用户故事，不重复索要已知字段。
- AI 不主动执行 MySQL 同步；由计划任务同步，除非使用者明确要求立即同步。
