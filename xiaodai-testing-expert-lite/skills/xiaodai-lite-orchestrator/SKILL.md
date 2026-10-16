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

## 知识库归档（xmind-to-weknora）

终版 xmind 用例归档到团队 weknora 知识库由平级 Skill `../xmind-to-weknora` 负责（空间/知识库映射内置在 `assets/preset_kb_mapping.json`，测试人员只需在连接器里配 `url` + `Authorization`）。本编排层只埋两个钩子，**不复制、不改写**该 Skill 的规则与脚本。

### 钩子 A：生成 xmind 之后（提醒）

环节 4 产出或更新 xmind 用例后，调用 xmind-to-weknora 的「提醒模式」：询问测试人员是否立即上传到 weknora 知识库。
- 回答「是」：进入执行模式（转 MD → 自动匹配 → 确认卡 → 上传）。
- 回答「否」：用 `scripts/sync_state.py mark --status pending` 记录，并在后续每个必做步骤收尾时再次提醒。

### 钩子 B：每个必做步骤收尾（检查）

环节 1、2、4、6、7 结束前执行 `scripts/sync_state.py check --key "<用户故事>|<文档类型>"`：
- 退出码 10/12（pending/无记录）：输出一条提醒，含目标知识库名与触发语「说『上传知识库』即可归档」。
- 退出码 11（skipped）：提醒一次即可，不再追问。
- 退出码 0（uploaded）：还要看 `tag_reminder` 与 `untagged_total`——非空即提醒人工打标；已打标则静默。

### 触发词

用户说「上传知识库」「同步 weknora」「归档用例」「用例入库」「上传到知识库了吗」「批量上传」「历史用例补录」「把这个目录的用例都传上去」时，进入 xmind-to-weknora 的执行模式 / 批量模式。

### 硬约束（来自技能，必须保留）

- 每次上传前必须展示确认卡（业务线/对应专家/空间ID/空间名/知识库名与ID/文档类型/weknora 标签/文档标题/来源文件/新建或更新），拿到明确「确认」才上传；沉默或答非所问视为未确认。
- 映射内置，禁止要求测试人员生成或修改任何本地 json。
- 标签走方案 C（人工勾选 + 全程提醒追踪）：每份上传完成后必须提醒到 weknora 网页端勾选标签，`tag_status` 追踪到闭环。
- 指定目标与预设不一致（resolve_target 退出码 3/4）时，停下来问测试人员是否新增知识库，禁止凭相似名称猜测。
- MCP 连接器未配置时不硬试上传，停在给出配置清单（只需 `url` + `Authorization`）。

## 宿主适配

需要展示文件或报告时读取 `prompts/host_adapters.md`。宿主差异只影响展示和安装方式，不得改变业务规则或数据字段。

## 强制约束

- 两个平级 Skill 的 Prompt 和脚本是权威规则，不复制、不改写、不弱化。
- 不展示花名册，不做模糊姓名匹配，不提供绕过身份校验的 fallback。
- 不在聊天中索要或输出数据库密码。
- 不固定输出盘符；首次产生文件前询问或确认输出目录并在会话内缓存。
- 事实、模型推断、建议和待确认项明确区分。
