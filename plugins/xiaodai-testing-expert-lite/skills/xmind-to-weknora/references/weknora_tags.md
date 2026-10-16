# weknora 标签（文档类型）——方案 C 落地手册

> 2026-10-15 定稿。**当前生效方式：方案 C（自动判定文档类型 + 人工勾选标签 + 全程提醒追踪）。**
> 证据基于实测（MCP `tools/list`、weknora 前端产物、REST 探测）。若 weknora 升级后行为有变，按第 6 节复测。

## 1. 标签是什么、为什么要打

测试人员在 weknora 知识库页按**标签**筛选文档（截图位置：知识库文档列表右上角「标签」）。团队用 4 个标签区分文档类型：

`测试用例` / `测试总结` / `测试需求分析` / `测试缺陷`

**标签是知识库级的**——每个知识库各有一套自己的标签，同一个名字要在每个库里分别建一次。

## 2. 能力现状（实测结论）

| 问题 | 答案 |
| --- | --- |
| 上传时能否**自动确定文档类型**？ | ✅ 能。`resolve_target.py` 输出的 `doc_type` / `tag`（来自专家身份 + 会话上下文 + 知识库归属）。 |
| 能否**通过 MCP 自动打标签**？ | ❌ 不能。MCP 服务端没有标签工具，`add_document` 也没有标签参数。 |
| MCP 能否**读回标签做校验**？ | ❌ 不能。`list_documents` 返回字段里没有标签。 |
| weknora 服务端**本身支持**标签吗？ | ✅ 支持。REST 有完整标签接口，网页端上传确认框就有「标签」页签。 |
| 能否绕过 MCP 走 REST？ | ⚠️ 服务端支持，但需**用户级令牌**；MCP 令牌对 `/api/*` 返回 401（实测）。 |

因此：**类型自动判定，标签人工勾选，进度由 skill 追踪。**

## 3. 方案 C 的完整流程

### 3.1 智能体侧（自动）

1. **判定**：`resolve_target.py` 输出 `tag`，同时写入文档标题后缀与 MD 头部元信息 `weknora标签：测试用例`。
2. **告知**：确认卡第 4/8 项展示「文档类型 + 标签名」。
3. **提醒**：上传成功后回执必带勾选路径——
   > weknora 知识库页（**<知识库名>**，空间：<空间名称>）→ 勾选刚上传的文档 → 点「标签」→ 添加标签 → 选择「**<标签名>**」→ 确定
4. **追踪**：`tag_status` 记录 `pending → done`，每个步骤收尾 `check` 复查；批量模式在报告里汇总待打标清单，追到回写完成。

### 3.2 测试人员侧（人工，5 步）

1. 打开 weknora 对应知识库页（空间名称 + 知识库名逐字核对）
2. 勾选本次上传的文档（可按标题里的日期戳批量勾选）
3. 点顶部「标签」按钮
4. 添加标签 → 选择本次文档类型对应的标签
5. 确定；回到列表确认标签已显示，然后回复「已打标签」

### 3.3 进度回写命令

```bash
# 单条模式
python scripts/sync_state.py mark --key "PRJ-00770309|测试用例" --status uploaded \
       --kb "效贷_测试_测试用例" --title "<标题>" --doc-id "<id>" --tag "测试用例"
python scripts/sync_state.py mark --key "PRJ-00770309|测试用例" --tag-status done
python scripts/sync_state.py list --untagged        # 看还有哪些没打

# 批量模式
python scripts/batch_cases.py mark --manifest manifest.json --id 2,3 --status uploaded --doc-id <id>
python scripts/batch_cases.py report --manifest manifest.json --out 批量上传报告.md   # 待打标勾选清单
python scripts/batch_cases.py mark --manifest manifest.json --id 2,3 --tag-status done
```

`tag_status` 取值：`pending` 待人工打标（上传成功时自动置）／`done` 已打标／`na` 无需打标（未上传）。
**标签进度不影响 `check` 的退出码**，避免打乱专家既有流程；智能体读 `tag_reminder` / `untagged_total` 字段决定要不要提醒。

## 4. 前提：四个标准标签要先建好

首次使用前，请管理员或测试人员在这 8 个测试知识库里各建一次（之后长期复用）：

| 空间（空间ID） | 知识库 | 需建标签 |
| --- | --- | --- |
| 场景业务线（10004） | 效贷_测试_测试用例 | 测试用例、测试总结、测试需求分析、测试缺陷 |
| 场景业务线（10004） | 效融_测试_测试用例 | 同上 |
| 场景业务线（10004） | 效贷_测试_测试总结 | 同上 |
| 场景业务线（10004） | 效融_测试_测试总结 | 同上 |
| 数据业务线（10003） | 泾渭云_测试_测试用例 | 同上 |
| 数据业务线（10003） | 小贷_测试_测试用例 | 同上 |
| 智慧记（10006） | AI零售_测试_测试用例 | 同上 |
| 智慧记（10006） | AI进销存_测试_测试用例 | 同上 |

建法：知识库页 → 标签 → 新建标签。**名称逐字一致**（中文，无空格、无下划线）。
验证：点「标签」应能看到 4 个标准标签，缺哪个补哪个。

> 实际用不到的类型可以暂时不建（例如某库只放测试用例，就先建「测试用例」），但建议一次建全，避免后续补建时遗漏。

## 5. 证据与未来升级路径

### 5.1 MCP 侧：10 个工具，零标签参数

直接对 MCP 端点做 JSON-RPC `tools/list`（`https://finwiki.kingdee.com/mcp/<端点UUID>`，携带连接器 `Authorization`）：

```
add_document        ['content', 'knowledge_base_id', 'publish', 'title', 'url']
grep_chunks         ['knowledge_base_ids', 'limit', 'query']
list_documents      ['keyword', 'knowledge_base_id', 'page', 'page_size']
list_knowledge_bases []
read_document       ['knowledge_id', 'limit', 'offset', 'query']
search_knowledge    ['knowledge_base_ids', 'limit', 'mode', 'query']
update_document     ['content', 'knowledge_id', 'publish', 'title']
wiki_index          ['knowledge_base_id', 'limit']
wiki_read_page      ['knowledge_base_id', 'slug']
wiki_search         ['knowledge_base_ids', 'limit', 'query', 'regex']
```

- `add_document` 的 `inputSchema.additionalProperties = false`，塞额外字段会被拒。
- `list_documents` 返回不含标签（只有 id / title / file_name / file_type / parse_status / description / created_at / updated_at）。

### 5.2 weknora 服务端：REST 有完整标签能力

从前端产物提取的调用封装：

```js
// 知识库级标签
listKbTags  = GET    /api/v1/knowledge-bases/{kb}/tags
createKbTag = POST   /api/v1/knowledge-bases/{kb}/tags
updateKbTag = PUT    /api/v1/knowledge-bases/{kb}/tags/{tagId}
deleteKbTag = DELETE /api/v1/knowledge-bases/{kb}/tags/{tagId}?force=true
// 给文档打标签
putKnowledgeTags = PUT /api/v1/knowledge/tags
```

旁证：手动编辑器发布请求体 `{title, content, status, tag_ids: [...]}`（**新建文档就支持带标签**）；上传确认框有「标签」页签；标签还能作为检索范围 `tag_scopes`。

### 5.3 为什么不能"绕过 MCP 直连 REST"

```
GET /api/v1/auth/me  ->  HTTP 401  {"error":"Unauthorized: invalid or expired token"}
```

MCP 令牌形如 `mcp_xxx`（54 字符），只对 `/mcp/<uuid>` 端点有效。REST 需要**用户登录态令牌**（登录后 JWT）或**管理员 API Key**（`/api/v1/system/admin/api-keys`）。
注意：`/api/*` 有统一鉴权中间件，未授权时即便路径不存在也返回 401，所以 401 不能用来判断接口是否存在——上面的接口清单来自前端产物，可信。

### 5.4 方案 A：给 MCP 加标签能力（推荐，根因修复）

请 weknora / MCP 维护方改 MCP 服务端，底层 REST 已支持，改动小：

1. `add_document` 增加可选参数 `tags: string[]`（标签名；服务端在目标知识库内按名称匹配，不存在则创建）
2. 新增 `list_tags(knowledge_base_id)` 工具
3. 新增 `set_document_tags(knowledge_id, tags)` 工具（供历史文档补标）

改完后改预设两处，skill 流程无需改动即自动打标：

```json
"tags": { "enabled": true, "auto_assign": true, "channel": "mcp" }
```

建议同时让 `list_documents` 返回 `tags` 字段，便于回读校对。

### 5.5 方案 B：REST 直连（拿到令牌即可启用）

```bash
export WEKNORA_TOKEN="<登录态令牌或管理员 API Key>"   # 不要写进 skill / 不要提交 Git

python scripts/tag_documents.py --check                                   # 通道自检
python scripts/tag_documents.py --kb <KB_ID> --list-tags                  # 看现有标签
python scripts/tag_documents.py --kb <KB_ID> --ensure-tags --apply        # 批量建 4 个标准标签
python scripts/tag_documents.py --kb <KB_ID> --title-match "零售版v1.0" --tag 测试用例 --apply
python scripts/tag_documents.py --kb <KB_ID> --from-manifest batch_manifest.json --tag 测试用例 --apply
```

- 默认 **dry-run**，必须显式 `--apply` 才写数据。
- 令牌用环境变量或 `--token-file`，**不要**用 `--token`（会进 shell 历史）。

启用 B 后，第 4 节的标签初始化可由 `--ensure-tags --apply` 一次性完成，历史文档也能按标题批量补标。

## 6. 复测方法（weknora 升级后自查）

```bash
python _selftest/probe_mcp_tools.py        # tools/list 里是否出现 tag 相关参数/工具
python scripts/tag_documents.py --check    # REST 通道是否可用
```

若 MCP 已支持标签 → 改预设 `auto_assign: true` / `channel: "mcp"`，重新打包分发，方案 C 的人工步骤即可全部退役。
