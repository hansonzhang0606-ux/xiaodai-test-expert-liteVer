# weknora MCP 接入指引

## 0. 先理清两个概念（重要）

| 概念 | 是什么 | 是否固定 |
| --- | --- | --- |
| **空间身份** | **weknora 空间ID + 空间名称**（如 `10004` 场景业务线、`10003` 数据业务线、`10006` 智慧记） | 固定。以 weknora 侧的 ID/名称为准，映射表内置在 `assets/preset_kb_mapping.json` |
| **连接凭据** | MCP 的 **`url`** + **`headers.Authorization`** | `url` 固定（每个空间一个 MCP 端点）；令牌由管理员发放 |
| **MCP 服务器名** | 各人在连接器里给这条配置起的名字（`weknora-changjingyewu`、`我的效贷库`…） | **不固定，随意起**。技能按 `url` 识别空间，不依赖名字 |

所以：**别把服务器名当固定值**，也不需要为了让名字对齐去改配置。工具名前缀由各人自己的服务器名派生，`init_config.py --discover` 会自动算出来。

## 1. WorkBuddy 中配置 MCP

编辑 `~/.workbuddy/mcp.json`，在 `mcpServers` 下新增对应空间的条目（**不要覆盖已有条目**）：

```json
{
  "mcpServers": {
    "weknora-changjingyewu": {
      "url": "https://finwiki.kingdee.com/mcp/<场景业务线端点UUID>",
      "headers": { "Authorization": "Bearer mcp_<由团队管理员发放的令牌>" }
    },
    "weknora-shujuyewu": {
      "url": "https://finwiki.kingdee.com/mcp/<数据业务线端点UUID>",
      "headers": { "Authorization": "Bearer mcp_<令牌>" }
    },
    "weknora-zhihuiji": {
      "url": "https://finwiki.kingdee.com/mcp/<智慧记端点UUID>",
      "headers": { "Authorization": "Bearer mcp_<令牌>" }
    }
  }
}
```

要点：

- 只有 `url` 与 `Authorization` 是关键字。`url` 必须与 `--discover` 输出的「权威标识 url」逐字一致。
- 服务器名（key）**可自定义**；但注意它决定工具名前缀 `mcp__<服务器名>__<工具>`，所以配好后用 `--discover` 取一次前缀即可。
- 令牌属于团队凭据，**不要**写进 skill 包、不要提交到 Git、不要在会话里明文回显。
- 配置保存后需在 WorkBuddy 的「连接器管理」右上角自定义连接器入口点击「信任」才会生效。
- 新增/修改后重启会话，让新的 MCP 工具被加载。

## 2. 识别与验证

```
python scripts/init_config.py --discover
```

输出每个空间的：权威 url、识别到的服务器名、是否含 Authorization、工具前缀。三种结果的含义：

- ✅ 全部命中 -> 直接用输出的 `mcp_prefix` 调工具。
- ❌ 某空间未命中 -> 该空间没配连接器，按第 1 节补 `url` + `Authorization`。
- ⚠️ 一个空间命中多个条目 -> 请确认用哪一个（例如同时配了正式与测试环境）。
- ⚠️ 「无法与预设空间对应」-> url 端点不在预设里，可能是测试环境或空间已改名，**不得**当上传目标，先人工确认。

随后调用一次列表工具验证连通：

```
{mcp_prefix}list_knowledge_bases
```

预期返回该空间下全部知识库的 `id` / `name` / `description`。返回异常参见 `troubleshooting.md`。

## 3. 其他 AI 智能体工具中配置

| 工具 | 配置位置 | 说明 |
| --- | --- | --- |
| Claude Code / Claude Desktop | `~/.claude.json` 或项目 `.mcp.json` 的 `mcpServers` | 结构同上，http 类型填 `url` + `headers` |
| Cursor | `~/.cursor/mcp.json` | 同上 |
| VS Code | 工作区 `.vscode/mcp.json` | 同上 |
| 其他支持 MCP 的客户端 | 客户端 MCP 设置文件 | 均为 `mcpServers` + `url`/`headers` 结构 |

`--discover` 会扫描上述常见位置（含 WorkBuddy）来识别空间；非 WorkBuddy 客户端的工具名前缀规则以其宿主为准，请注意确认实际可用的工具名。

## 4. 知识库 ID 从哪来

`list_knowledge_bases` 返回的 `id` 即知识库 ID。**团队 8 个测试知识库的 ID 已全部预置**在 `assets/preset_kb_mapping.json`，测试人员无需获取或填写。

`id` 为空时（仅发生在新增知识库未填 ID 的情况）weknora 的 `list_documents` / `add_document` 也接受**精确名称**，本 skill 会自动退回使用名称；名称必须与 weknora 中完全一致（含下划线、中英文）。

## 5. 三个空间的预设（已全部接入）

| weknora空间ID | 空间名称 | 端点 url（权威标识） | 知识库数 |
| --- | --- | --- | --- |
| 10004 | 场景业务线 | `https://finwiki.kingdee.com/mcp/d8ce6877-390f-4e56-9e8e-4310bf76821d` | 4 |
| 10003 | 数据业务线 | `https://finwiki.kingdee.com/mcp/ab150dd0-2b14-4775-9622-0c9c95b9a84e` | 2 |
| 10006 | 智慧记 | `https://finwiki.kingdee.com/mcp/fc8b14ee-4e7a-492b-8610-eb9abc17ae70` | 2 |

> url 里只含空间端点 UUID，不含令牌，因此可以随 skill 分发；令牌必须各人自行配置。

## 6. 后续新增知识库如何接入

后续若新建 `AI零售_测试_测试缺陷`、`AI进销存_测试_测试总结`、`AI进销存_测试_测试需求分析` 等知识库（命名约定 `<前缀>_测试_<文档类型>`），**这件事由智能体完成，测试人员不需要做任何配置**：

1. **发现**：`--diff-kb` 对账，列出 weknora 里有、映射里没有的知识库；
2. **确认**：把清单给测试人员，问清「本次要传的是哪个？归属哪条业务线/产品/专家？」——**未确认前不得上传**；
3. **登记**：写入**内置预设**（团队标准映射），随 skill 升级分发到全团队：

```
python scripts/init_config.py --add-kb  --space 10006 --name "AI零售_测试_测试缺陷" --id <新ID>
python scripts/init_config.py --sync-kb --space 10006 --from-json kb_list.json   # 批量补齐（自动跳过已有）
```

4. **复核**：`--validate` + `resolve_target.py --biz-line ZHJLS --doc-type 测试缺陷`；
5. **重新打包** skill 分发，各台机器即开箱生效。

要点：

- 默认写入目标是 `--target preset`（`assets/preset_kb_mapping.json`）。新增条目自动继承同前缀知识库的业务线/产品/别名/专家，`doc_type` 由名称推导。
- `--target local` 只用于排障时临时覆盖，**不要让测试人员走这条路**——本地副本会盖住 skill 升级后的新预设。
- **不要让测试人员手工编辑 json**；他只需提供新知识库的名称与归属，其余交给智能体。
