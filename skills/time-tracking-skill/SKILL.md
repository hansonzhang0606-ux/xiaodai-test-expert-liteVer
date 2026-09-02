---
name: time-tracking-skill
description: >-
  Use when 测试工作流需要按环节收集 AI 预估节省工时与测试人员确认的节省工时，
  并通过团队身份校验、业务线隔离和 MySQL 同步完成效能追踪时。
---

# 测试人员时间节省追踪 Skill

> 当前发布版本：**v5.9**

> 从「效贷测试专家」抽取而来的独立子 Skill，用于嵌入其他测试团队的 Skill 套件。
> 核心能力：**追踪并量化测试工作中 AI 为每位测试人员节省的时间**。

## 一、能力概览

| 能力 | 说明 |
|------|------|
| AI 独立预估 | 参考范围和人员反馈出现前生成 `ai_estimated_time_saved_hours`，与记录值隔离 |
| 强制反馈 | 工作流每个步骤完成后，强制收集节省时间（不可跳过） |
| 中间值规则 | “采纳”或追问两次仍无实际值时取参考范围中间值；后一种写固定备注 |
| 二次确认 | 明确值和“采纳”分支保存前确认；无反馈分支自动保存中间值，避免永久阻塞 |
| 身份验证 | 盲输入 + 花名册精确匹配，无 fallback |
| 多业务线 | 一份 Skill 服务多条业务线，数据按业务线隔离 |
| 本地优先 | 记录只写本地 JSONL（零网络依赖、永不失败），MySQL 同步由定时任务完成 |
| MySQL 同步 | 本地 JSONL 幂等 upsert 到共享 MySQL（离线可用，pymysql 已打包） |
| 可视化报告 | HTML 报告（内置 JS 筛选面板）+ CSV 导出，报告必展示 |
| 双宿主兼容 | WorkBuddy（`present_files` 展示）与 IDE（VSCode/OpenCode/Claude Code 等，给文件路径）均可运行 |

## 二、目录结构

```
time-tracking-skill/
├── VERSION                           # 当前发布版本：5.9
├── SKILL.md                          # 本文件
├── README.md                         # 使用与部署说明
├── prompts/
│   └── time_tracking.md              # 执行规则（AI 遵循的完整工作流）
├── config/
│   ├── time_tracking_config.yaml     # 主配置（default_biz_line、storage_mode、MySQL 等）
│   └── team_roster.yaml              # 花名册【已弃用，人员改存 MySQL agent_team_roster】
├── scripts/
│   ├── biz_line_helper.py            # 业务线解析助手（统一入口）
│   ├── record_time_saved.py          # 记录节省时间（写本地 JSONL）
│   ├── generate_time_analytics.py    # 生成 HTML/CSV 分析报告
│   ├── sync_to_excel.py              # Excel 集中存储（可选附加）
│   ├── sync_to_mysql.py              # MySQL 幂等同步（时间节省数据 → agent_time_tracking）
│   ├── sync_roster_to_mysql.py       # 花名册同步【已弃用】
│   ├── load_roster.py                # 实时查 MySQL agent_team_roster，AI 身份识别用（v1.5.2）
│   ├── init_mysql_config.py          # 初始化本机 MySQL 配置（一次性）
│   ├── mysql_config.json.template    # MySQL 配置模板
│   ├── sync_task.bat                 # Windows 定时任务入口（每日 09:00 / 12:00 / 18:00）
│   ├── config_loader.py              # 配置加载器
│   └── pymysql/                      # 打包的纯 Python MySQL 驱动
├── sql/
│   └── upgrade_v5.8_to_v5.9.sql     # 管理员手动执行的可重复升级脚本
└── tests/                            # v5.9 自动化回归与发布契约测试
```

## 三、部署必做（仅一步）

编辑 `config/time_tracking_config.yaml`，设置（**智慧记有三个子业务线，须填子业务线全称，不可填统称"智慧记"**）：

```yaml
default_biz_line: "智慧记+运营系统"   # 或 AI进销存 / 智慧记零售
```

支持的业务线及编码：

| 编码 | 业务线 |
|------|--------|
| XD | 效贷 |
| JWY | 泾渭云 |
| XR | 效融 |
| XXD | 小贷 |
| ZHJ | 智慧记+运营系统 |
| AIJXC | AI进销存 |
| ZHJLS | 智慧记零售 |

> 若未设置，脚本运行时会明确报错提示，不会静默写入错误业务线。

## 四、快速开始

```bash
# 1. 记录一条节省时间（花名册校验 + 写入本地 JSONL）
python scripts/record_time_saved.py \
  --employee "测试用户" \
  --user-story "PRJ-00888888-【智慧记】测试需求" \
  --step "文档整理" --step-code "01" \
  --hours 4 \
  --ai-estimated-time-saved-hours 3.5 \
  --biz-line "智慧记+运营系统"

# 2. 生成分析报告（HTML，内置筛选面板）
python scripts/generate_time_analytics.py --biz-line "智慧记+运营系统"

# 3. 生成个人报告
python scripts/generate_time_analytics.py --biz-line "智慧记+运营系统" --person "测试用户"

# 4. MySQL 初始化（首次会话由 AI 自动完成；手动方式：需管理员告知数据库密码）
python scripts/init_mysql_config.py --biz-line "智慧记+运营系统" --password "xxx" --no-interactive --employee "测试用户" --quiet

# 5. 手动同步到 MySQL（幂等；日常由定时任务 09:00/12:00/18:00 自动执行）
python scripts/sync_to_mysql.py --biz-line "智慧记+运营系统"
```

## 五、核心概念

### 业务线（biz_line）
- 每条业务线的数据隔离存储在 `~/.workbuddy/data/time-tracking/{biz_line}/`
- 脚本通过 `--biz-line` 参数指定；未指定时读取 `default_biz_line`
- 花名册中一名员工可属于多条业务线（`biz_line_code` 数组），身份确认时由员工选择

### 身份验证
- 会话开始时 AI 查询 MySQL `agent_team_roster` 表，盲输入姓名精确匹配
- 匹配失败直接拒绝服务，无 fallback
- 会话启动时 AI 自动检查 `mysql_config.json`：缺失则向用户索要密码并**自动调用 `init_mysql_config.py` 完成初始化**（无需手动开 CMD），不阻塞服务

### 存储模式（storage_mode）
- `mysql`（默认）：本地 JSONL 兜底 + 定时任务同步共享 MySQL，供团队汇总
- `local`：仅本地 JSONL（无集中存储，开箱即用）
- `excel`：本地 JSONL + Excel 文件（可选附加）

## 六、详细执行规则

AI 在每个步骤完成后如何收集时间、如何生成报告，详见 `prompts/time_tracking.md`。
该文件是给 AI 读的执行规则，测试人员无需关心。

## 七、依赖说明

| 依赖 | 用途 | 是否需要安装 |
|------|------|------------|
| pymysql | MySQL 同步 | 否（已打包进 scripts/pymysql/） |
| openpyxl | Excel 同步（可选） | 是（`pip install openpyxl`） |
| PyYAML | 花名册解析 | 否（有简易解析兜底） |

> 本 Skill 为 MySQL-only，**不依赖腾讯文档连接器**。

## 八、宿主环境适配（双场景）

本 Skill 同时支持两类使用场景，数据最终都同步到**同一张 MySQL 表**（`agent_time_tracking`，
按 `biz_line_code` 区分业务线）：

| 场景 | 形态 | 驱动入口 | 报告展示方式 |
|------|------|---------|------------|
| **WorkBuddy 测试专家** | 智能体（agent） | `agent.md` + 内嵌本 Skill | 调用 `present_files` 在右侧面板打开 HTML 预览 |
| **IDE skill 套件** | 纯 Skill 包 | `SKILL.md`（VSCode / OpenCode / Claude Code 等可加载） | 回复中给出报告文件完整路径，用户用浏览器打开 |

> - **脚本层完全宿主无关**：全部脚本是纯命令行（`.py` / `.bat`），两类场景共用，无需重复开发
> - **记录链路一致**：每步时间 → 本地 `records.jsonl` → `sync_to_mysql.py`（定时任务 09:00/12:00/18:00）→ 共享 MySQL
> - **幂等键兼容（两层去重 v6.2）**：`record_key = MD5(biz_line_code|employee|user_story|step_code|timestamp)` 保证同条记录重同步不新增行；另按 `(biz_line_code, employee, user_story_code, step_code, time_saved_hours)` 业务字段组合去重，避免不同 timestamp 但业务相同的记录重复入库
> - **本机配置共用**：`mysql_config.json` 是本机私有配置，同一台电脑两种工具共用一份
