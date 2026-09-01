# 测试人员时间节省追踪 Skill（通用多业务线版 · MySQL-only · v5.9）

> 从「效贷测试专家」v1.5.0 抽取而来的独立子 Skill，可嵌入任意测试团队的 Skill 套件。
> 用于追踪并量化测试工作中 AI 为每位测试人员节省的时间。
>
> **v5.9 新增**：独立保存 AI 预估节省工时 `ai_estimated_time_saved_hours`；
> “采纳”或追问两次仍无实际值时统一采用参考范围中间值，AI 预估不得替代人员反馈记录值。
>
> **存储口径（v5.3）**：记录只写本地 JSONL → 定时任务（每日 09:00 / 12:00 / 18:00）幂等同步到
> **共享 MySQL 数据库**。不依赖腾讯文档连接器。
>
> **花名册来源（v1.5.2）**：身份识别**实时查询 MySQL `agent_team_roster` 表**，
> 不再读取本地 `team_roster.yaml`。`team_roster.yaml` 已弃用，人员由管理员直接维护在 MySQL `agent_team_roster` 表，多副本/多机器部署下花名册永远最新。
>
> **双宿主兼容**：既可嵌入 WorkBuddy 测试专家（智能体），也可作为纯 Skill 套件嵌入
> VSCode / OpenCode / Claude Code 等 IDE 工具。两类场景的数据最终都同步到**同一张
> MySQL 表**（`agent_time_tracking`，按 `biz_line_code` 区分业务线）。

---

## 1. 这是什么

一个让 AI 在测试工作流每个步骤完成后，**强制收集「这一步为你节省了多少时间」数据**的 Skill。
数据先写本地 JSONL（零网络依赖、永不失败），再由定时任务同步到团队共享 MySQL 数据库，
管理员可用 SQL 汇总；同时可生成 HTML 可视化报告（内置筛选面板）。

每个环节同时保存两种独立口径：AI 在参考范围和人员反馈出现前生成
`ai_estimated_time_saved_hours`；测试人员明确反馈或按规则采用的参考中间值保存在
`time_saved_hours`。两者不得互相覆盖。

**两类使用场景**（数据最终汇聚同一 MySQL 表）：

| 场景 | 形态 | 驱动入口 | 报告展示 |
|------|------|---------|---------|
| WorkBuddy 测试专家 | 智能体（agent） | `agent.md` + 内嵌本 Skill | `present_files` 右侧面板预览 |
| IDE skill 套件 | 纯 Skill 包 | `SKILL.md` | 回复中给出文件路径，浏览器打开 |

> 脚本层完全宿主无关（纯命令行 `.py` / `.bat`），两类场景共用，无需重复开发。

## 2. 部署（三步）

### 第 1 步：解压

把本 zip 解压到目标团队的 Skill 目录，例如：

```
智慧记测试套件/
└── time-tracking-skill/   ← 本包
```

### 第 2 步：配置业务线

编辑 `config/time_tracking_config.yaml`，把 `default_biz_line` 改为你的业务线名称
（**智慧记有三个子业务线，须填具体子业务线全称，不可填统称"智慧记"**）：

```yaml
default_biz_line: "智慧记+运营系统"   # 或 AI进销存 / 智慧记零售
```

支持的业务线：`效贷` / `泾渭云` / `效融` / `小贷` / `智慧记+运营系统`(ZHJ) / `AI进销存`(AIJXC) / `智慧记零售`(ZHJLS)

> 一名员工可属于多条业务线（花名册 `biz_line_code` 数组）。身份确认时，若成员属多条业务线，
> AI 会**列出编号选项**让成员输入数字选择（如 `1. 智慧记+运营系统` / `2. AI进销存` / `3. 智慧记零售`），
> 避免自由文本回答笼统导致匹配不准确；`default_biz_line` 仅作为单业务线成员的默认值。

### 第 3 步：填写花名册

直接维护 MySQL `agent_team_roster` 表的团队成员（INSERT/UPDATE）：

```yaml
members:
  - name: "测试用户"
    role: "功能测试"
    biz_line_code: ["ZHJ", "ZHJLS"]   # 可属于多条业务线
    active: true
```

> **v1.5.2 起**：`team_roster.yaml` 已弃用，**运行时身份验证直接查 MySQL `agent_team_roster` 表**，人员由管理员直接维护该表；`scripts/sync_roster_to_mysql.py` 已弃用，勿再运行。
>
> 花名册控制谁能用：AI 会盲输入姓名精确匹配，不在花名册内直接拒绝服务。

## 3. MySQL 同步（主流程，团队汇总必须配置）

### 3.1 每台电脑一次性初始化（测试人员，v1.5.1 起 AI 自动完成）

> **测试人员无需手动操作**：首次使用专家时，身份验证通过后 AI 会自动检测本机
> `mysql_config.json`——不存在就提示输入密码并自动调用脚本生成对应业务线目录，
> 存在就直接跳过。测试人员**再也不用手动打开 CMD**。

管理员侧需准备：数据库密码（单独告知测试人员）。手动备选方式（AI 调用失败 / 排查时）：

```bat
python init_mysql_config.py --biz-line "智慧记+运营系统"
```

AI 自动模式使用的等价命令（`--auto` 已存在自动跳过、`--quiet` 输出机器可读 JSON）：

```bat
python init_mysql_config.py --biz-line "智慧记+运营系统" --password "xxx" --employee "测试用户" --no-interactive --quiet
```

生成本机配置 `~/.workbuddy/data/time-tracking/智慧记+运营系统/mysql_config.json`
（**含密码，本机私有，不随 Skill 分发，不要发群/提交 Git**）。

> ⚠️ **不初始化 = 数据只在本机**：每步反馈的时间只保存在本地 JSONL，
> 不会同步到团队共享 MySQL，管理员在数据库里看不到你的数据。**记录功能本身不受影响。**

### 3.2 注册定时任务（每日 09:00 / 12:00 / 18:00 自动同步，v5.3 起 AI 自动完成）

> **正常情况下由 AI 自动完成**（会话启动检测到未注册 → 自动 `schtasks /create` 注册早/午/晚三任务）。
> 以下为手动备选方式，仅在 AI 无法自动完成（如权限不足）或管理员排查时使用：

以管理员身份打开 CMD：

```bat
REM 先确认 scripts/sync_task.bat 顶部 set BIZ_LINE=智慧记+运营系统 已改好
schtasks /create /tn "智慧记运营时间同步-早" /tr "C:\...\time-tracking-skill\scripts\sync_task.bat" /sc daily /st 09:00 /f
schtasks /create /tn "智慧记运营时间同步-午" /tr "C:\...\time-tracking-skill\scripts\sync_task.bat" /sc daily /st 12:00 /f
schtasks /create /tn "智慧记运营时间同步-晚" /tr "C:\...\time-tracking-skill\scripts\sync_task.bat" /sc daily /st 18:00 /f
```

> `sync_task.bat` 已内置 Python 自动探测 + GBK/CRLF 编码修复，无需改配置。

### 3.3 手动同步 / 验证

```bat
python sync_to_mysql.py --biz-line "智慧记+运营系统" --dry-run    :: 试运行，只看不写
python sync_to_mysql.py --biz-line "智慧记+运营系统"              :: 真实同步（幂等，重复跑无副作用）
```

## 4. 存储模式选择（可选）

| 模式 | 说明 | 适用 |
|------|------|------|
| `mysql`（默认） | 本地 JSONL + 定时任务同步共享 MySQL | 团队汇总（推荐） |
| `local` | 仅本地 JSONL，无需任何外部依赖 | 个人试用 / 快速验证 |
| `excel` | 本地 + Excel 共享文件（可选附加） | 团队无 MySQL 但有共享目录 |

默认 `mysql`：开箱即用（本地记录），配置好 MySQL 后自动进入团队汇总模式。

## 5. 常见命令速查

```bash
# 记录节省时间（写本地 JSONL，AI 工作流自动调用）
python scripts/record_time_saved.py --employee "张三" --user-story "US-001" \
  --step "文档整理" --step-code "01" --hours 4 \
  --ai-estimated-time-saved-hours 3.5 --biz-line "智慧记+运营系统"

# 全业务线报告（HTML）
python scripts/generate_time_analytics.py --biz-line "智慧记+运营系统"

# 个人报告
python scripts/generate_time_analytics.py --biz-line "智慧记+运营系统" --person "张三"

# CSV 导出
python scripts/generate_time_analytics.py --biz-line "智慧记+运营系统" --format csv

# MySQL 初始化 + 同步
python scripts/init_mysql_config.py --biz-line "智慧记+运营系统"
python scripts/sync_to_mysql.py --biz-line "智慧记+运营系统"
```

## 6. 依赖

| 依赖 | 用途 | 说明 |
|------|------|------|
| pymysql | MySQL 同步 | 已打包（scripts/pymysql/），无需安装 |
| openpyxl | Excel 同步（可选） | `pip install openpyxl` |
| PyYAML | 花名册解析 | 有简易解析兜底，可缺省 |

> 本 Skill 为 MySQL-only，**不依赖腾讯文档连接器**。

## 7. 目录说明

```
time-tracking-skill/
├── VERSION                     # 当前发布版本：5.9
├── SKILL.md                    # Skill 入口（AI 读）
├── README.md                   # 本文件（人读）
├── prompts/time_tracking.md    # AI 执行规则（v5 MySQL-only 口径）
├── config/                     # 主配置（业务线/存储/MySQL）+ 花名册
├── scripts/                    # 全部脚本（含打包的 pymysql）
├── sql/                        # 管理员手动执行的数据库升级脚本
└── tests/                      # v5.9 回归与发布契约测试
```

## 8. 版本来源

- 抽取自「效贷测试专家」GitHub v1.5.0（`hansonzhang0606-ux/xiaodai-test-expert`）
- 泛化改动：`biz_line` 全部可配置、花名册 `employee_id` → `biz_line_code`、报告标题/表名动态化
- v5 口径：存储改为 MySQL-only（本地 JSONL + 定时任务幂等同步），彻底移除腾讯文档依赖
- 双宿主兼容：`prompts/time_tracking.md` 已做宿主无关处理（WorkBuddy 用 `present_files`，IDE 环境给文件路径）
- v1.5.1：MySQL 初始化由手动改为 **AI 自动完成**（会话启动检测 → 索要密码 → 自动调用 `init_mysql_config.py --auto --quiet`，配置已存在自动跳过），测试人员无需手动开 CMD
- v1.5.2：**身份识别从「读 `team_roster.yaml`」改为「实时查 MySQL `agent_team_roster`」**——`team_roster.yaml` 退化为「输入源」（管理员维护后通过 `sync_roster_to_mysql.py` 推到 MySQL），新增 `scripts/load_roster.py` 给 AI 用 JSON 形式拉取在职人员；会话启动顺序调整为「先 MySQL 配置检查 → 再花名册查询 → 再身份验证」
- 业务线编号选择：多业务线成员身份确认时，AI 列出编号选项让成员输入数字选择（`biz_line_helper.py` 新增 `code_to_biz_line` 反向映射），避免自由文本回答笼统导致匹配不准确
- v5.3：`sync_task.bat` 修复 Windows 兼容性（GBK 编码 + CRLF 换行 + Python 自动探测 + `%~dp0` 定位），解决 schtasks 触发的 cmd.exe 用 GBK(936) 读取 UTF-8/LF bat 导致中文乱码、找不到命令、路径找不到的问题；定时任务注册由「人工手动」升级为「AI 自动完成」（会话启动检测未注册 → 自动 `schtasks /create` 注册早/午/晚三任务）
- v5.5：sync_task.bat 升级为接收第 1 个参数 %1 决定业务线，定时任务 /tr 末尾传入 {biz_line}，同一份 bat 复用服务多业务线（效贷/泾渭云/效融/小贷/智慧记+运营系统/AI进销存/智慧记零售），彻底去掉硬编码；配套效贷测试专家 agent v1.6.3 在业务线确定后强制校验 mysql_config.json 真实生成才算闭环。
- v5.4：强化「立即触发 + 阻塞下一步」——修复实际测试中步骤完成后 AI 跳过时间收集、直接展示「下一步」选项的问题；5 个环节产出交付后必须先完成时间收集（通报 → 询问 → 解析 → 二次确认 → 写本地 JSONL），确认记录完成后才允许展示下一步选项
- v5.6：team_roster.yaml 的 members 名单清空（运行时身份识别早已迁至 MySQL `agent_team_roster`，yaml 不再作为数据源）；同步将全部文档/脚本中「改 yaml → `sync_roster_to_mysql.py` 推 MySQL」的维护口径统一改为「管理员直接 INSERT/UPDATE MySQL `agent_team_roster` 表」，并给 `sync_roster_to_mysql.py` 加【已弃用】提示（误运行不改动 MySQL 数据）；zip 内嵌的 team_roster.yaml 随之更新为空 members。
- v5.7：时间记录增加 `agent_start_time` / `agent_end_time` / `agent_duration_minutes` 三个字段，`record_time_saved.py` 新增对应 CLI 参数，`sync_to_mysql.py` 在 upsert 时同步写入 MySQL `agent_time_tracking` 表，解决表中该三字段长期为 NULL 的问题；`prompts/time_tracking.md` 明确要求 AI 在步骤开始/结束时采集智能体执行耗时并传入脚本。
- v5.8：定时任务自动注册从「提示词内联 3 条带 `<scripts目录>` 占位符的 schtasks 命令（模型无法可靠填出路径，导致其他电脑/测试人员从未真正建出任务）」改为**确定性脚本调用** `python scripts/register_sync_tasks.py --biz-line {biz_line}`；新增 `scripts/register_sync_tasks.py`（用 `__file__` 自定位 `sync_task.bat`、按业务线幂等注册 早/午/晚 三任务、注册失败给明确提示），彻底解决跨机器自动建任务的根因；注册时机从「MySQL 配置就绪后」提前到「业务线确定后」。
- v5.9：新增 `--ai-estimated-time-saved-hours` 与 MySQL 同名可空列；“采纳”和两次追问仍无实际值统一取参考范围中间值，后者写固定备注；未升级数据库时保留 v5.8 同步路径，DDL 只由管理员手动执行。
- 抽取日期：2026-08-18
