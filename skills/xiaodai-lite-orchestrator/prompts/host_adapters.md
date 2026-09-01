# 三端宿主适配

## WorkBuddy

- 使用专家包内的三个平级 Skill。
- HTML 报告生成后用 WorkBuddy 的文件展示能力打开，并在回复中给出完整本地路径。

## Codex App

- 从仓库 `.agents/skills/xiaodai-testing-expert-lite/SKILL.md` 进入。
- 使用本机终端执行 Python 脚本；生成文件后给出可点击的完整路径。

## Windows VS Code + Codex

- 与 Codex App 共用 `.agents/skills` 入口和根 `skills/` 源码。
- 使用 VS Code 工作区对应的本机终端执行 Python 脚本；生成文件后给出完整路径。

宿主只改变文件展示方式，不改变身份、七环节、时间反馈、MySQL 字段或业务规则。
