# 效贷测试专家轻量版

同一套工程同时面向 WorkBuddy、Codex App 和 Windows VS Code + Codex 扩展。它保留轻量测试业务 Skill v3.7 与时间追踪 Skill v6.3 的原有逻辑，通过一个薄编排器把七个可执行环节、三条业务线和节省工时反馈连接起来。

## 日常流程

默认主链路：需求文档整理 → 生成测试点与 XMind → 生成 Excel 测试用例。

按需环节：需求评审、确认评审、评审 XMind 测试点、知识库入库。七个环节都可以从合格的已有输入资产独立启动，不会自动推进。

时间追踪覆盖文档整理（01）、需求评审（02）、生成测试点（04）、生成用例（06）和入库知识库（07）。确认评审和评审 XMind 不单独记录。

## 三端使用

- WorkBuddy：使用 `dist/xiaodai-testing-expert-lite-v1.0.2-workbuddy.zip`，或导入 `xiaodai-testing-expert-lite/` 专家目录。
- Codex App：打开本仓库，Codex 从 `.agents/skills/xiaodai-testing-expert-lite/SKILL.md` 发现入口。
- VS Code：安装 Codex 扩展后打开本仓库，使用同一个 `.agents/skills` 入口。

详见 [三端使用说明](docs/三端使用说明.md) 和 [架构说明](docs/架构与维护.md)。

## 构建与验证

```powershell
python -m pip install -r requirements.txt
python scripts/build_release.py
python scripts/validate_release.py
python -m unittest discover -s tests -v
```

根目录 `skills/` 是唯一业务源码。WorkBuddy 专家包和 `plugins/` 镜像由构建脚本生成，请勿手工修改其中的 Skill 副本。

## 安全

MySQL 地址、库名、账号和密码只填写在使用者本机生成的 `mysql_config.json`，不得提交 Git。仓库及发布 ZIP 不预置内网连接信息。专家不会展示花名册，姓名按 MySQL `agent_team_roster` 在职记录和所选业务线精确匹配；校验服务不可用时拒绝写入。
