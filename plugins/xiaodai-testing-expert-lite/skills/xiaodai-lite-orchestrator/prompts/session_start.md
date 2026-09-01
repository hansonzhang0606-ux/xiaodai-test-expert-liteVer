# 会话启动规则

每个新会话按以下顺序执行，完成前不得处理业务材料。

## 1. 选择业务线

固定展示三项并要求输入数字：

1. 效贷（XD）
2. 效融（XR）
3. 小贷（XXD）

只把本次选择缓存为候选业务线，最终权限仍以 MySQL 花名册为准。

## 2. 确保候选业务线配置可用

检查 `~/.workbuddy/data/time-tracking/{业务线中文名}/mysql_config.json`。若缺失，定位平级 `time-tracking-skill/scripts/init_mysql_config.py` 并执行：

```text
python init_mysql_config.py --biz-line "{业务线中文名}" --template --no-interactive --quiet
```

向使用者展示脚本返回的配置文件和说明文件路径，让其只在本地文件中填写管理员提供的信息。不得在聊天中索要密码。填写完成后重新验证配置，再继续。

## 3. 盲输入姓名并精确匹配

调用平级 `time-tracking-skill/scripts/load_roster.py --json` 实时查询 MySQL `agent_team_roster`。不得读取本地 `team_roster.yaml` 作为身份依据。

- 不展示人员列表。
- 让使用者输入姓名，去除首尾空格后与 `active=true` 的 `members[*].name` 精确匹配。
- 匹配失败时拒绝服务，提示联系管理员维护花名册。
- 匹配成功但不属于候选业务线时，只展示该人员在 XD、XR、XXD 中实际拥有的业务线编号，要求重新选择；不得绕过权限。
- 缓存姓名、业务线中文名和编码，后续环节不重复询问。

## 4. 注册同步任务

业务线最终确定后调用：

```text
python xiaodai-lite-orchestrator/scripts/register_sync_tasks.py --biz-line "{业务线中文名}"
```

只使用编排器自带的注册脚本和 `sync_task.bat`；它会把 Python 解析为绝对路径并通过 `%~dp0` 定位平级时间 Skill。禁止直接注册时间 Skill 内的旧 BAT。

成功或已存在即继续。若权限或公司策略导致失败，说明本地 JSONL 记录仍可用，并给出脚本返回的手动同步建议；该失败不阻断测试工作。

## 5. 开始入口

身份通过后展示七个可执行环节，标明按需项，并说明日常主链路为 1 → 4 → 6。等待使用者选择，不自动启动某个环节。
