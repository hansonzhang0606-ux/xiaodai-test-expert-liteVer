---
name: xiaodai-lite-orchestrator
description: |
  Use when a tester asks to start or continue the lightweight testing workflow for Xiaodai, Xiaorong, or Microloan, including requirement consolidation, requirement review or confirmation, test-point or XMind generation or review, Excel case generation, knowledge archiving, or time-savings reports in WorkBuddy, Codex, or VS Code.
---

# 效贷测试专家轻量版编排器

本 Skill 只负责路由和钩子。业务产物必须按 `../ai-testcase-workflow-skill` 执行，时间数据必须按 `../time-tracking-skill` v5.9 执行。

## 每次会话必须先做

完整读取 `prompts/session_start.md`，完成业务线、MySQL 配置、花名册姓名校验和计划任务注册。身份校验失败时不得执行任何业务环节。

## 七环节

执行前读取 `config/step_mapping.yaml` 和 `prompts/workflow_routing.md`。用户可独立调用任一环节，但必须具备该环节需要的合格输入。

1. 需求文档整理
2. 需求评审（按需）
3. 确认评审
4. 生成测试点并最终生成 XMind
5. 评审 XMind 测试点（按需）
6. 生成 Excel 测试用例
7. 知识库入库（按需）

日常默认主链路为 1 → 4 → 6。完成一个环节后不自动进入下一环节。

## 时间钩子

环节 1、2、4、6、7 的产物交付后，完整读取 `prompts/time_tracking_hooks.md`，并进一步读取 `../time-tracking-skill/prompts/time_tracking.md`。时间记录必须经过 `scripts/secure_record_time_saved.py` 的严格身份门禁，完成前不得展示下一步选项。

环节 3、5 不单独创建时间记录。

## 宿主适配

需要展示文件或报告时读取 `prompts/host_adapters.md`。宿主差异只影响展示和安装方式，不得改变业务规则或数据字段。

## 强制约束

- 两个平级 Skill 的 Prompt 和脚本是权威规则，不复制、不改写、不弱化。
- 不展示花名册，不做模糊姓名匹配，不提供绕过身份校验的 fallback。
- 不在聊天中索要或输出数据库密码。
- 不固定输出盘符；首次产生文件前询问或确认输出目录并在会话内缓存。
- 事实、模型推断、建议和待确认项明确区分。
