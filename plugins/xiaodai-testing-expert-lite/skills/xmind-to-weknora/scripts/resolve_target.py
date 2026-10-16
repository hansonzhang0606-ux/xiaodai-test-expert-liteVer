#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_target.py - 根据业务线/产品/文档类型路由到 weknora 空间与目标知识库。

路由数据来自 skill 内置预设（assets/preset_kb_mapping.json）或本地覆盖配置，
测试人员无需自行配置映射表。

用法:
  python resolve_target.py --biz-line XD --doc-type 测试用例 --user-story PRJ-00770309 --requirement 额度申请
  python resolve_target.py --biz-line JWY --json
  python resolve_target.py --list
  python resolve_target.py --kb "效贷_测试_测试用例"          # 直接按名称/ID 反查

输出字段（--json 为纯 JSON）:
  space_id / space_name / space_url / mcp_prefix / kb_id / kb_name / kb_ref /
  biz_line / biz_line_name / product / doc_type / expert / title / confidence /
  tag / tag_auto / tag_hint    （tag = weknora 中对应文档类型的标签名；tag_auto 表示能否自动打标）

退出码: 0 命中唯一；2 多个候选需人工选择；3 未命中（疑似新知识库）；
        4 命中但与测试人员指定的空间/业务线不一致；1 配置缺失
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from init_config import load_config, config_source, is_preset, resolve_space_key  # noqa: E402


def norm(s):
    return (s or "").strip().lower()


def score_kb(kb, biz_line, product, doc_type):
    s = 0
    bl, pd, dt = norm(biz_line), norm(product), norm(doc_type)
    if bl:
        names = [norm(kb.get("biz_line")), norm(kb.get("biz_line_name"))]
        aliases = [norm(a) for a in (kb.get("biz_line_alias") or [])]
        if bl in names:
            s += 5
        elif bl in aliases:
            s += 4
        elif any(bl in a or a in bl for a in aliases + names if a):
            s += 2
    if pd:
        pnames = [norm(kb.get("product"))] + [norm(a) for a in (kb.get("product_alias") or [])]
        if any(pd == n for n in pnames if n):
            s += 3
        elif any(pd in n or n in pd for n in pnames if n):
            s += 2
        if pd in norm(kb.get("name")):
            s += 2
    if dt:
        if norm(kb.get("doc_type")) == dt:
            s += 5
        elif dt in norm(kb.get("name")):
            s += 3
        else:
            s -= 2
    return s


def all_kbs(cfg):
    for key, sp in (cfg.get("spaces") or {}).items():
        for kb in sp.get("knowledge_bases", []):
            yield key, sp, kb


NEW_KB_TIP = (
    "如果 weknora 里确实新建了知识库 / 调整了归属，测试人员只需告诉智能体一句：\n"
    "    「新增了 XX 库，归属 效贷（或 效融 / 泾渭云 / 小贷 / 智慧记零售 / AI进销存）」\n"
    "智能体会与你确认归属后写进 skill 内置映射，随下次升级分发到全团队 —— 不需要你自己配置任何 json。"
)


STOP_TOKENS = {"测试", "用例", "用例库", "知识库", "的"}


def similar_kbs(cfg, hint, limit=5):
    """按子串包含关系找相似知识库，用于「是不是新建了库」的提示。"""
    h = norm(hint)
    if not h:
        return []
    out = []
    for key, sp, kb in all_kbs(cfg):
        name = norm(kb.get("name"))
        score = 0
        if h in name or name in h:
            score = 2
        else:
            for tok in (h.split("_") if "_" in h else [h]):
                if tok and len(tok) >= 2 and tok not in STOP_TOKENS and tok in name:
                    score = 1
                    break
        if score:
            out.append({"space_id": sp.get("space_id") or key,
                        "space_name": sp.get("space_name") or sp.get("name", ""),
                        "kb_name": kb.get("name"), "kb_id": kb.get("id"),
                        "biz_line": kb.get("biz_line_name") or kb.get("biz_line"),
                        "doc_type": kb.get("doc_type")})
    out.sort(key=lambda x: len(x["kb_name"]))
    return out[:limit]


def mismatch_payload(cfg, args, kind, detail):
    """未命中 / 不一致时的统一输出：说清差异 + 提示是否有新知识库 + 告诉测试人员该怎么做。"""
    return {
        "mismatch": kind,
        "detail": detail,
        "input": {"biz_line": args.biz_line, "product": args.product,
                  "doc_type": args.doc_type, "kb": args.kb, "space": getattr(args, "space", None)},
        "ask_tester": "你指定的目标与团队预设映射不一致 —— 是 weknora 里新建了知识库，还是换了一条业务线/空间？",
        "new_kb_tip": NEW_KB_TIP,
        "agent_action": [
            "1) 用 MCP list_knowledge_bases 拉该空间的真实清单，存成 kb_list.json",
            "2) python init_config.py --diff-kb --space <空间ID> --from-json kb_list.json  （列出未登记/失效项）",
            "3) 与测试人员确认归属后：python init_config.py --add-kb --space <空间ID> --name \"<库名>\" --id <ID>",
            "4) 复核：init_config.py --validate + resolve_target.py 重跑；随后重新打包 skill 分发",
        ],
        "similar": similar_kbs(cfg, args.kb or args.biz_line or ""),
        "known_spaces": [{"space_id": sp.get("space_id") or k,
                          "space_name": sp.get("space_name") or sp.get("name", ""),
                          "kb_names": [kb.get("name") for kb in sp.get("knowledge_bases", [])]}
                         for k, sp in (cfg.get("spaces") or {}).items()],
    }


def resolve(cfg, biz_line=None, product=None, doc_type=None, kb_hint=None):
    if kb_hint:
        hint = norm(kb_hint)
        for key, sp, kb in all_kbs(cfg):
            if hint in (norm(kb.get("name")), norm(kb.get("id"))):
                return [(key, sp, kb, 100)]
        return []
    scored = []
    for key, sp, kb in all_kbs(cfg):
        s = score_kb(kb, biz_line, product, doc_type)
        if s > 0:
            scored.append((key, sp, kb, s))
    scored.sort(key=lambda x: x[3], reverse=True)
    if not scored:
        return []
    top = scored[0][3]
    return [x for x in scored if x[3] == top]


def resolve_tag(cfg, doc_type):
    """文档类型 -> weknora 标签名。标签写入通道由 tags.auto_assign / tags.channel 决定。"""
    tags = cfg.get("tags") or {}
    dt = (doc_type or "").strip()
    mapping = tags.get("map") or {}
    name = mapping.get(dt)
    if not name and tags.get("fallback_same_as_doc_type", True):
        name = dt
    enabled = bool(tags.get("enabled", True))
    auto = bool(tags.get("auto_assign", False)) and enabled
    if not enabled:
        hint = "标签能力已在预设中关闭。"
    elif auto:
        hint = f"上传后自动打标签「{name}」。"
    else:
        hint = (f"当前通道（{tags.get('channel', 'mcp')}）无法写入标签，"
                f"请在 weknora 网页端手工勾选：{tags.get('ui_hint', '勾选文档 -> 标签 -> 选择文档类型 -> 确定')}")
    return {"name": name, "enabled": enabled, "auto": auto, "hint": hint,
            "reason": tags.get("channel_reason", "") if not auto else ""}


def build_title(cfg, kb, requirement, user_story, product, doc_type, date_str):
    naming = cfg.get("naming") or {}
    dt = norm(doc_type)
    if "总结" in (doc_type or ""):
        tpl = naming.get("title_template_summary")
    elif dt == "测试用例":
        tpl = naming.get("title_template")
    else:
        tpl = naming.get("title_template_generic")
    tpl = tpl or "{product}_{user_story}_{requirement}_{doc_type}_{yyyyMMdd}"
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    title = tpl.format(
        product=product or kb.get("product") or "",
        user_story=user_story or "",
        requirement=requirement or "",
        doc_type=doc_type or "",
        yyyyMMdd=date_str,
    )
    while "__" in title:
        title = title.replace("__", "_")
    title = title.strip("_")
    max_len = int(naming.get("max_title_len") or 80)
    if len(title) > max_len:
        title = title[:max_len]
    return title


def main():
    ap = argparse.ArgumentParser(description="业务线 -> weknora 空间/知识库 路由")
    ap.add_argument("--biz-line", help="业务线代码或名称：XD/XR/JWY/XDK/ZHJLS/AIJXC，或 效贷/效融/泾渭云/小贷/智慧记零售/AI进销存")
    ap.add_argument("--product", help="产品名称，如 效贷 / 泾渭云 / AI进销存 / 智慧记零售")
    ap.add_argument("--doc-type", default="测试用例", help="测试用例(默认)、测试总结 等")
    ap.add_argument("--requirement", help="需求名称（用于生成文档标题）")
    ap.add_argument("--user-story", help="用户故事编号，如 PRJ-00770309")
    ap.add_argument("--date", help="日期戳，默认今天(yyyyMMdd)")
    ap.add_argument("--kb", help="直接指定知识库名称或 ID，跳过路由推断")
    ap.add_argument("--space", help="测试人员指定的空间（weknora 空间ID 或空间名称），用于与预设做一致性校验")
    ap.add_argument("--mcp-prefix", help="已知的 MCP 工具前缀（来自 --discover），原样带回输出")
    ap.add_argument("--config", help="指定配置文件路径")
    ap.add_argument("--list", action="store_true", help="列出全部空间与知识库")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    cfg, cfg_path = load_config(args.config)
    if cfg is None:
        print("[错误] 找不到映射配置（skill 内置预设缺失，skill 包可能不完整）", file=sys.stderr)
        raise SystemExit(1)

    if args.list:
        rows = [{
            "space_id": sp.get("space_id") or k,
            "space_name": sp.get("space_name") or sp.get("name"),
            "space_url": sp.get("mcp_url"),
            "mcp_prefix": sp.get("mcp_prefix") or "",
            "kb_name": kb.get("name"), "kb_id": kb.get("id"),
            "biz_line": kb.get("biz_line"), "biz_line_name": kb.get("biz_line_name"),
            "product": kb.get("product"), "doc_type": kb.get("doc_type"),
            "tag": resolve_tag(cfg, kb.get("doc_type"))["name"],
            "expert": kb.get("expert"),
        } for k, sp, kb in all_kbs(cfg)]
        print(json.dumps({"source": config_source(cfg_path), "items": rows}, ensure_ascii=False, indent=2))
        return

    hits = resolve(cfg, args.biz_line, args.product, args.doc_type, args.kb)
    if not hits:
        kind = "kb_not_registered" if args.kb else "no_match"
        detail = (f"指定的知识库「{args.kb}」不在团队预设映射中。"
                  if args.kb else
                  f"业务线「{args.biz_line or args.product or '未指定'}」+ 文档类型「{args.doc_type}」在预设映射中没有对应知识库。")
        msg = mismatch_payload(cfg, args, kind, detail)
        msg["error"] = "未匹配到知识库（疑似新知识库或归属有变）"
        msg["hint"] = "禁止凭相似名称猜测目标库 —— 先与测试人员确认是否新建了知识库，确认后登记再上传。"
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        raise SystemExit(3)

    if len(hits) > 1:
        cands = [{
            "space_id": sp.get("space_id") or k,
            "space_name": sp.get("space_name") or sp.get("name"),
            "kb_name": kb.get("name"), "kb_id": kb.get("id"),
            "biz_line": kb.get("biz_line"), "doc_type": kb.get("doc_type"), "score": sc,
        } for k, sp, kb, sc in hits]
        print(json.dumps({"error": "命中多个知识库，需人工确认", "candidates": cands}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    key, sp, kb, sc = hits[0]

    # ---- 一致性校验：测试人员指定的空间 / 业务线 是否与预设命中结果一致 ----
    conflicts = []
    if args.space:
        want_key = resolve_space_key(cfg.get("spaces") or {}, args.space)
        want_id = (cfg["spaces"].get(want_key, {}) or {}).get("space_id") if want_key else None
        got_id = sp.get("space_id") or key
        if want_id and str(want_id) != str(got_id):
            conflicts.append(
                f"指定空间「{args.space}」= {want_id}，但预设中「{kb.get('name')}」属于 "
                f"{sp.get('space_name')}（{got_id}）")
    if args.biz_line:
        bl = norm(args.biz_line)
        names = [norm(kb.get("biz_line")), norm(kb.get("biz_line_name"))]
        aliases = [norm(a) for a in (kb.get("biz_line_alias") or [])]
        if bl not in names and bl not in aliases and not any(bl in a or a in bl for a in aliases + names if a):
            conflicts.append(
                f"指定业务线「{args.biz_line}」与命中知识库「{kb.get('name')}」的归属业务线"
                f"「{kb.get('biz_line_name') or kb.get('biz_line')}」不一致")
    if conflicts:
        msg = mismatch_payload(cfg, args, "inconsistent", "；".join(conflicts))
        msg["error"] = "命中结果与测试人员指定的空间/业务线不一致"
        msg["hint"] = ("以测试人员说法为准重新核对：若 weknora 里确实新建/调整了知识库，按 new_kb_tip 让测试人员"
                       "一句话告知归属；若只是口误，更正后重跑。未确认前不得上传。")
        msg["resolved_but_rejected"] = {
            "space_id": sp.get("space_id") or key,
            "space_name": sp.get("space_name") or sp.get("name", ""),
            "kb_name": kb.get("name"), "kb_id": kb.get("id"),
            "biz_line": kb.get("biz_line_name") or kb.get("biz_line"),
        }
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        raise SystemExit(4)

    title = build_title(cfg, kb, args.requirement, args.user_story,
                        args.product or kb.get("product"), args.doc_type, args.date)
    tag = resolve_tag(cfg, args.doc_type)
    prefix = args.mcp_prefix or sp.get("mcp_prefix") or ""
    result = {
        "config_path": cfg_path,
        "config_source": config_source(cfg_path),
        "space_id": sp.get("space_id") or key,
        "space_name": sp.get("space_name") or sp.get("name", ""),
        "space_url": sp.get("mcp_url", ""),
        "mcp_server": sp.get("mcp_server", ""),
        "mcp_prefix": prefix,
        "mcp_prefix_hint": "" if prefix else "未识别：先跑 init_config.py --discover 得到工具前缀",
        "kb_id": kb.get("id") or "",
        "kb_name": kb.get("name"),
        "kb_ref": kb.get("id") or kb.get("name"),
        "doc_type": args.doc_type,
        "tag": tag["name"],
        "tag_auto": tag["auto"],
        "tag_hint": tag["hint"],
        "tag_reason": tag["reason"],
        "biz_line": kb.get("biz_line"),
        "biz_line_name": kb.get("biz_line_name") or kb.get("biz_line"),
        "product": args.product or kb.get("product"),
        "expert": kb.get("expert", ""),
        "title": title,
        "confidence": sc,
        "require_confirm": bool((cfg.get("upload") or {}).get("require_confirm", True)),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"目标空间：{result['space_name']}（空间ID {result['space_id']}）")
        print(f"业务线：{result['biz_line_name']}（{result['biz_line']}）")
        print(f"目标知识库：{result['kb_name']}（ID {result['kb_id']}）")
        print(f"文档类型：{result['doc_type']}    对应专家：{result['expert'] or '-'}")
        print(f"weknora 标签：{result['tag']}    "
              f"{'（自动打标签）' if result['tag_auto'] else '（需人工勾选，见 tag_hint）'}")
        print(f"MCP 前缀：{result['mcp_prefix'] or result['mcp_prefix_hint']}")
        print(f"建议文档标题：{result['title']}")
        if not result["tag_auto"] and result["tag_hint"]:
            print(f"标签提示：{result['tag_hint']}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
