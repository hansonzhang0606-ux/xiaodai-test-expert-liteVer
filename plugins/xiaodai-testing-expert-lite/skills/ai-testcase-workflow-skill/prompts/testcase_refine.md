# Excel 详细用例生成 Prompt

用于把已确认的测试点/XMind 细化为 DMP 可导入的 Excel 测试用例。

## 触发条件

仅当用户说“生成用例”“生成 Excel”“出详细用例”时执行。

## 输入优先级

1. 用户评审后的 XMind。
2. 若没有评审后的 XMind，使用本轮生成的测试点 JSON。
3. 读取已确认需求整理稿或同目录 `*整理版*.md`，用于补充业务规则和测试数据。
4. 技术方案如存在且与用例步骤相关，可读取；不强制搜索所有资料。
5. 默认不读取知识库。

## 参数规则

从 `{项目根}/.skill/project.yaml` 读取：

- `defaults.team`
- `defaults.product`
- `defaults.modulePath`
- `defaults.manager`
- `defaults.caseLevel`
- `defaults.source`
- `defaults.autoState`

用户每次只需提供：

| 参数 | 说明 | 示例 |
|------|------|------|
| title | 用户故事标题 | 调资方接口前校验税票采集状态 |
| version | 版本号 | V2026.08.20 |
| relateReqCode | 需求编码 | PRJ-00737131 |

`caseGroup` 从版本号和标题推导：

```text
V2026.08.20 + 调资方接口前校验税票采集状态
=> 2026-202608-20260820-调资方接口前校验税票采集状态
```

若 `defaults.manager` 缺失，才向用户追问责任人。

## 细化规则

- 每个测试点生成 1-N 条用例，按风险和场景复杂度决定。
- XMind 叶子节点是测试点原始事实，Excel 阶段不擅自改名、改义或把泛化标题脑补成新测试点。
- 解析 XMind 后先复检叶子节点；若存在分类词、规则标题、过短泛化标题，先输出问题清单并停止生成 Excel。
- 每条用例步骤至少 2 步。
- 步骤使用 `1、` `2、` 格式。
- 预期结果数量与步骤数量一一对应。
- 测试数据必须实例化，避免“某值”“某状态”这类占位描述。
- P0 只给主链路或高风险阻塞场景；默认 P1。
- 删除标记的 XMind 节点不生成用例。

## Excel 固定列

| 列 | 字段 |
|----|------|
| A | team |
| B | caseGroup |
| C | name |
| D | preCondition |
| E | input |
| F | output |
| G | product |
| H | modulePath |
| I | version |
| J | caseType |
| K | source |
| L | caseLevel |
| M | manager |
| N | autoState |
| O | relateReqCode |
| P | workload |
| Q | remarks |
| R | separator |

## 输出

- `{需求名}_测试用例.json`
- `{需求名}_测试用例.xlsx`

## 脚本调用

如输入是 XMind：

```bash
python scripts/parse_xmind.py "{需求名}_测试点.xmind" -o "{需求名}_测试点_reviewed.json"
```

细化并生成 Excel：

```bash
python scripts/refine_testcases.py "{测试点JSON}" --caseGroup "{功能路径}" --version "{版本号}" --manager "{责任人}" --relateReqCode "{需求编码}"
python scripts/generate_excel.py "{测试用例JSON}" --caseGroup "{功能路径}" --version "{版本号}" --manager "{责任人}" --relateReqCode "{需求编码}"
```

## 禁止项

- 未确认测试点前，不生成 Excel。
- 默认不读取知识库。
- 不重复询问 project.yaml 已有的固定参数。
- 不生成空泛步骤或不可验证预期。
- 不把“正常流程/业务规则/边界与组合/异常场景/单客户最多5次”等分类或规则标题直接生成 Excel 用例。