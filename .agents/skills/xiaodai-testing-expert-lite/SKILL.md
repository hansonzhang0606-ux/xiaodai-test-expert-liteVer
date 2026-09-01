---
name: xiaodai-testing-expert-lite
description: |
  Use when a user opens this repository in Codex App or VS Code and asks to start the Xiaodai lightweight testing workflow, process requirements, generate or review test points or XMind, generate Excel cases, archive knowledge, or view time-savings statistics.
---

# 效贷测试专家轻量版入口

本文件只负责 Codex 发现，不承载重复业务规则。

1. 先定位仓库根目录。
2. 完整读取 `skills/xiaodai-lite-orchestrator/SKILL.md`。
3. 按编排器要求读取 `skills/xiaodai-lite-orchestrator/config/step_mapping.yaml` 和对应 Prompt。
4. 业务产物只使用 `skills/ai-testcase-workflow-skill` 的规则和脚本。
5. 时间记录只使用 `skills/time-tracking-skill` v5.9 的规则和脚本。

不得直接绕过编排器进入业务 Skill，因为会漏掉业务线、身份和时间追踪门禁。
