# 首次使用配置清单（给测试人员）

好消息：**知识库映射已经内置在 skill 里，你不需要配置任何 json。**

第一次使用只需要做一件事：**在 AI 工具里连上你们业务线的 weknora 空间（MCP 连接器）**。连上之后，上传目标（空间 / 知识库 / 业务线）由技能自动匹配，并在真正上传前展示确认卡让你核对。

> 智能体检测到没连上时会主动给出本清单并停在配置步骤，不会盲目上传。

## 第 1 步：向团队管理员索取连接信息

每个 weknora 空间一条，只需要两样东西：

- **url**：`https://finwiki.kingdee.com/mcp/<空间端点UUID>`
- **令牌**：`mcp_xxx`（写在 Authorization 头里的 Bearer 令牌）

按自己业务线取（不必全配）：

| 你的业务线 | 需要连接的空间 | weknora 空间ID |
| --- | --- | --- |
| 效贷、效融 | 场景业务线 | 10004 |
| 泾渭云、小贷 | 数据业务线 | 10003 |
| 智慧记零售、AI进销存 | 智慧记 | 10006 |

## 第 2 步：在 WorkBuddy 里配置连接器

编辑 `C:\Users\<用户名>\.workbuddy\mcp.json`，在 `mcpServers` 里**追加**（不要覆盖已有条目）：

```json
{
  "mcpServers": {
    "weknora-changjingyewu": {
      "url": "https://finwiki.kingdee.com/mcp/<场景业务线端点UUID>",
      "headers": { "Authorization": "Bearer mcp_<令牌>" }
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

**关键点（重要）**：

- 真正起作用的是 **`url`** 和 **`headers.Authorization`** 两个字段。
- **服务器名（上面示例里的 `weknora-changjingyewu`）可以随便起**，比如 `我的效贷库` 也行——技能是按 `url` 识别空间的，不依赖这个名字。团队里各人起名不一致也没关系。
- `url` 必须与技能识别出的「权威标识 url」完全一致（同一空间只有这一个端点），不要自行拼错 UUID。
- 令牌属于团队凭据：**不要**提交到 Git、不要发到群里、不要贴进 skill 包。

然后：

1. 打开 WorkBuddy「连接器管理」→ 右上角自定义连接器入口 → 对新服务器点「信任」；
2. **重启会话**，让新工具被加载。

> 用其他 AI 工具（Claude Code / Cursor / VS Code 等）：把同样的 `url` + `Authorization` 写进该工具的 MCP 配置文件即可，服务器名同样可自定义。

## 第 3 步：自检（不用改任何配置）

让智能体跑这两条，或自己在工作区执行：

```
python scripts/init_config.py --discover      # 看三个空间是否识别到、工具前缀是什么
python scripts/init_config.py --doctor        # 一键体检：映射来源 + 连接器识别结果
```

预期输出（已连通时）：

```
空间 场景业务线（空间ID 10004）
  权威标识 url：https://finwiki.kingdee.com/mcp/d8ce6877-...
  ✅ 服务器名：weknora-changjingyewu｜WorkBuddy｜✅ 已含 Authorization
     工具前缀：mcp__weknora-changjingyewu__
```

某空间显示 ❌ 就是还没配好，按第 2 步补该空间的 `url` + `Authorization`。

最后让智能体调用一次 `list_knowledge_bases`（工具名前缀用上一步输出的），能列出知识库即为连通。

## 第 4 步：在你用的知识库里建好 4 个标准标签（只需做一次）

weknora 用标签区分文档类型。**标签是知识库级的**，每个库各建一次，之后长期复用。

打开你负责的知识库 → 点「标签」→ 新建标签，依次建这 4 个（名称逐字一致，中文无空格）：

```
测试用例    测试总结    测试需求分析    测试缺陷
```

只建你实际会用到的类型也可以（例如只放测试用例的库先建「测试用例」），但建议一次建全。

> 上传后技能会提醒你给文档勾标签——那时候标签必须已经存在，否则选不到。

## 你**不需要**做的事

- ❌ 不需要创建或修改 `weknora_mcp.json`（没有这个文件也完全正常）。
- ❌ 不需要填知识库 ID、业务线映射、专家归属——都已内置在 skill 里。
- ❌ 不需要保证服务器名和别人一致——名字随便起。
- ✅ 后续团队新增了知识库，也不归你配：告诉智能体「新增了 XX 库」，由它确认归属后写进 skill 内置映射，下次升级自动生效。

## 常见问题

- **服务器名和别人不一样 / 我改了名，会不会传错库？** 不会。技能按 `url` 识别空间，名字任意；最终还靠上传前的确认卡核对空间ID与知识库ID。
- **只想连自己业务线的空间**：可以，只配一个即可，其它业务线的知识库你也用不到。
- **配了还是调不通**：先确认已点「信任」并重启会话；再确认 `url` 与管理员给的完全一致；最后查令牌是否过期。
- **不确定传到哪个库**：不要猜。上传前技能会展示确认卡；也可以用 `--diff-kb` 先对账知识库清单。
- **标签能不能自动打上？** 暂时不能——weknora 的 MCP 通道没有标签参数（已实测）。文档类型由技能自动判定并写进标题和文档头部，标签需要你在网页端勾一下；技能会记进度并在每个步骤收尾提醒，直到你回复「已打标签」为止。
