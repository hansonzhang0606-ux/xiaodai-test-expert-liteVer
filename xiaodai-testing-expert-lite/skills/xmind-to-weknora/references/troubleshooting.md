# 故障排查

## 报「找不到映射配置」/「内置预设缺失」

现象：`resolve_target.py` 或 `init_config.py --list` 报找不到配置。

原因与处理：

- **正常情况下不需要任何本地配置**——路由数据内置在 `assets/preset_kb_mapping.json`，由 skill 随包分发。报这个错说明 skill 包不完整（预设文件缺失或被删），**重新解压安装即可**。
- 新增知识库用 `--add-kb` / `--sync-kb`，默认直接写回内置预设（团队标准），随 skill 升级分发；**不需要让测试人员建本地 json**。
- 排查路径优先级：`<工作区>/.workbuddy/weknora_mcp.json` > `~/.workbuddy/weknora_mcp.json` > 内置预设。若前两者存在且是旧副本，会盖住 skill 升级后的新预设——**排障结束后删掉本地配置**。

## MCP 工具不可用 / 未加载

现象：找不到形如 `mcp__<服务器名>__add_document` 的工具。

处理顺序：

1. 跑 `python scripts/init_config.py --discover`，确认目标空间是否 ✅ 识别到；
2. 若 ❌：确认 `~/.workbuddy/mcp.json` 中已配置该空间的 `url` + `Authorization`（**服务器名随便起都可以**），且已在连接器管理中「信任」；
3. 重启会话让工具加载；
4. 在会话中用工具搜索按需加载该类工具后再调用；
5. 仍不可用则先只完成「xmind -> MD 转换」，把 MD 落盘，待 MCP 恢复后用 `add_document` 补传。

## 服务器名不一致会不会传错库

不会。空间识别以 **url** 为准（`--discover` 按 `mcp_url` 匹配），服务器名只影响工具名前缀，与目标知识库无关。最终仍由上传前确认卡核对空间ID + 知识库ID。

## 一个空间识别到多个连接器

`--discover` 报「识别到 N 个条目指向同一空间」时，说明本机配置了多个指向同一 `url` 的条目（例如正式环境 + 自建别名）。**询问测试人员用哪一个**，不要默认取第一个。

若出现「无法与预设空间对应」的 weknora 类服务器，说明其 url 端点不在预设中（可能是测试环境或空间已改名）——**不得**用它当上传目标，先人工确认。

## 调用 add_document 报知识库不存在

- 知识库 ID 已全部预置，正常情况下不该出现；若出现先用 `list_knowledge_bases` 复核该空间下的真实 ID/名称；
- 名称必须与 weknora 中显示的**完全一致**（含 `_`、中英文、全半角）；
- 优先用 `id`，避免名称歧义。

## 命中多个知识库（退出码 2）

`resolve_target.py` 返回 `candidates` 时，**必须让测试人员人工选择**，不要自行猜测。可补充 `--product` 或 `--doc-type` 缩小范围，或用 `--kb "知识库名称"` 直接指定。

典型场景：某业务线同时有「测试用例」和「测试总结」两个库，未指定 `--doc-type` 时可能并列命中。

## xmind 解析失败

- 提示「zip 内既无 content.json 也无 content.xml」：文件可能不是标准 xmind，请用 XMind 重新导出；
- 转换后层级错乱：改试 `--style heading`（前 3 层渲染为标题）；
- 出现乱码：确认脚本以 UTF-8 运行（Windows PowerShell 5.1 下必要时先执行 `chcp 65001`）。

## 重复上传

默认按标题查重（`list_documents` + 标题关键字）：

- 已存在同名文档 -> 询问「更新已有文档 / 新建一份」，默认建议更新；
- 需要强制新建时，在标题尾部追加版本号或时间戳（如 `_v2`）。

## 发现映射里没有的知识库（未登记）

`--diff-kb` 报出未登记知识库时，**不得直接拿它当上传目标**。处理顺序：

1. 把清单给测试人员看，问清「本次要传哪个库 / 归属哪条业务线」——顺便问他是不是新建了知识库；
2. 用 `--add-kb` 或 `--sync-kb` 登记（默认写回 skill 内置预设，随升级分发）；
3. `init_config.py --validate` + `resolve_target.py` 复核；
4. 再走「上传前强制确认」。

映射里存在但 weknora 中查不到的条目（可能改名/删除）：提醒人工核实后再用，不静默沿用旧名称。

## 新增知识库后路由不命中（退出码 3）

知识库必须先登记进映射才会被路由命中，不会自动发现。处理：

```
python scripts/init_config.py --diff-kb --space 10006 --from-json kb_list.json
python scripts/init_config.py --sync-kb --space 10006 --from-json kb_list.json
python scripts/init_config.py --add-kb  --space 10006 --name "AI零售_测试_测试缺陷" --id <新ID>
python scripts/init_config.py --validate
```

`--space` 可传 weknora 空间ID（10004/10003/10006）、空间名称或端点 UUID。若新条目 `biz_line` 为空，路由只能按名称匹配，建议补上（继承规则见 `mcp_setup.md` 第 6 节）。

**不要凭相似名称凑一个库。** 遇到未命中就问测试人员一句：

> 是 weknora 里新建了知识库吗？如果是，你只需告诉我一句「新增了 XX 库，归属 效贷 / 效融 / 泾渭云 / 小贷 / 智慧记零售 / AI进销存」，我来登记，不需要你配置任何 json。

## 命中结果与测试人员指定不一致（退出码 4）

`resolve_target.py` 传了 `--space` / `--biz-line` / `--kb` 时，会与预设做一致性校验，冲突时退出码 4，输出形如：

```
指定空间「智慧记」= 10006，但预设中「效贷_测试_测试用例」属于 场景业务线（10004）
指定业务线「XD」与命中知识库「泾渭云_测试_测试用例」的归属业务线「泾渭云」不一致
```

处理与退出码 3 相同：先复述差异 → 问是否有新知识库或是否口误 → 更正/登记 → 重新路由 → 确认卡 → 上传。未确认前不上传。

> 建议每次都把测试人员说出的空间/知识库一起传进 `resolve_target.py`，这一层校验能挡住"传错库"。

## 批量模式问题

- **scan 报「未匹配到知识库」**：补 `--kb "知识库名称"` 直接指定，或检查 `--biz-line` / `--doc-type` 是否笔误。
- **scan 报「命中多个知识库」**：加 `--product` 或 `--kb` 缩小范围，别让脚本自行选择。
- **出现 ⚠️ 跨线告警**：说明文件名里含其他业务线关键词（如选了效贷但文件名含「效融」），提示会给出「可能应传到：效融_测试_测试用例」这类建议。必须与测试人员逐条确认归属，确认后可用 `mark --status skipped` 排除，或单独用正确的业务线再扫一次。
- **标题不对**：直接编辑 `manifest.json` 里 `items[].title`（或 `requirement` / `user_story`）后再执行 convert；已 converted 的条目加 `--overwrite` 重转。
- **中断后续传**：重新执行 `convert`（自动跳过已转换/已上传），再对清单里非 `uploaded` 的条目继续上传。
- **Windows 路径含中文**：用引号包裹路径；PowerShell 5.1 下中文输出乱码时先执行 `chcp 65001`。

## 无法上传 .xmind / .xlsx 原文件

weknora 的 `add_document` 只接受 **Markdown 文本或 URL**，不接受二进制文件。因此：

- 上传到知识库的永远是 **Markdown 版本**；
- 原始 .xmind / .xlsx 继续保存在本地（或共享盘），MD 文档头部的元信息会记录来源文件名，便于回溯。

## 标签（文档类型）相关

当前执行**方案 C**：类型自动判定，标签人工勾选，进度由 skill 追踪。详见 `weknora_tags.md`。

- **「脚本能自动打标签吗？」**：不能。weknora MCP 的 10 个工具里没有标签参数，`add_document` 的 schema 只有 `knowledge_base_id / title / content / url / publish`。文档类型本 skill 会**自动判定**（写进标题、MD 头部 `weknora标签`、确认卡第 4/8 项），但**标签要在 weknora 网页端勾选**（知识库页 → 勾选文档 → 标签 → 添加标签 → 选择类型 → 确定）。每条上传回执都会提醒，打完回复「已打标签」即可闭环。
- **「怎么知道还有哪些没打标？」**：`sync_state.py list --untagged`（单条）或 `batch_cases.py report`（批量，报告里按标签分组列出勾选清单）。`check` 输出的 `tag_reminder` / `untagged_total` 非空即表示待打标。
- **「打标进度会影响流程吗？」**：不会。`tag_status` 只用于提醒，不改 `check` 的退出码，专家既有流程不受影响。
- **「能不能不走 MCP，直接调 weknora 接口打标？」**：服务端 REST 支持（`/api/v1/knowledge-bases/{kb}/tags`、`/api/v1/knowledge/tags`），但连接器里的 MCP 令牌（`mcp_xxx`）对 `/api/*` 返回 401，需要用**用户登录态令牌或管理员 API Key**（方案 B，脚本已就绪，待令牌启用）。
- **`tag_documents.py --check` 报 401**：你用的多半是 MCP 令牌。换令牌；管理员 API Key 在 `/api/v1/system/admin/api-keys`。
- **标签里的名字和知识库名对不上**：标签是**知识库级**的，同一个名字要在每个知识库分别建。用网页端或 `--ensure-tags` 补齐。
- **某个知识库里没有「测试用例」标签**：先在网页端建好（知识库页 → 标签 → 新建标签），否则勾不到。首次使用前请把 4 个标准标签建全。
- **标签名与文档类型的映射要改**：改预设 `assets/preset_kb_mapping.json` 的 `tags.map` 一处即可，`resolve_target.py` 的 `tag` 输出随之变化。
- **未来想自动打标**：方案 A（请 weknora/MCP 维护方加 `tags` 参数或 `set_document_tags` 工具）→ 改预设 `auto_assign: true` / `channel: "mcp"` 即可，流程无需改动。
