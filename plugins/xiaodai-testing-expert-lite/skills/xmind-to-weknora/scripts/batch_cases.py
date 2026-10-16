#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_cases.py - 批量把本地某目录下的历史 xmind 用例转 MD，并准备上传到 weknora。

设计原则：本脚本只做「扫描 / 转换 / 进度记录」，上传动作仍由智能体调用 MCP 完成，
因为 add_document 需要走 MCP 工具，脚本无法直接调用。

典型流程:
  1) python batch_cases.py scan   --dir D:/历史用例 --biz-line XD --product 效贷 --out manifest.json
  2) 人工确认清单与目标知识库（脚本会打印预览表 + 疑似错线告警）
  3) python batch_cases.py convert --manifest manifest.json
  4) 智能体按清单逐条 add_document，每成功一条：
     python batch_cases.py mark --manifest manifest.json --id 3 --status uploaded --doc-id <id>
  5) python batch_cases.py report --manifest manifest.json

退出码: 0 正常；2 参数/配置问题；3 路由未命中或多候选
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from init_config import load_config, config_source     # noqa: E402
from resolve_target import resolve, build_title, norm, all_kbs, resolve_tag  # noqa: E402
from xmind_to_md import convert                      # noqa: E402

XMINDS = (".xmind",)
MDS = (".md", ".markdown")
NOISE_TOKENS = ["测试用例", "测试案例", "测试点", "用例", "终版", "终稿", "最终版", "final",
                "testcase", "test_case", "xmind", "v1", "v2", "v3"]
STORY_PATTERNS = [r"PRJ-\d+", r"prj-\d+", r"\b\d{6,}\b"]


# ---------------------------------------------------------------- 工具
def extract_user_story(text):
    for pat in STORY_PATTERNS:
        m = re.search(pat, text)
        if m:
            s = m.group(0)
            return s.upper() if s.lower().startswith("prj") else s
    return ""


def extract_requirement(stem, user_story, extra_noise=None):
    s = stem
    if user_story:
        s = s.replace(user_story, "")
    low = s.lower()
    for tok in NOISE_TOKENS:
        low = low.replace(tok.lower(), " ")
    # 去掉文件名里重复出现的业务线/产品名，避免标题出现「效贷_..._效贷 xxx」
    for tok in (extra_noise or []):
        if tok and len(str(tok)) >= 2:
            low = low.replace(str(tok).lower(), " ")
    s = low
    s = re.sub(r"[_\-\[\]（）()【】\s]+", " ", s).strip()
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" -_") or stem


def alias_conflicts(cfg, chosen_biz_line, text):
    """检查文件名是否出现了别的业务线关键词，提示可能选错业务线。"""
    chosen = norm(chosen_biz_line)
    hits = {}
    for key, sp, kb in all_kbs(cfg):
        bl = norm(kb.get("biz_line"))
        if not bl or bl == chosen:
            continue
        cands = [bl] + [norm(a) for a in (kb.get("biz_line_alias") or [])]
        for c in cands:
            if c and len(c) >= 2 and c in norm(text):
                label = kb.get("biz_line_name") or kb.get("biz_line")
                hits.setdefault(label, set()).add(kb.get("name"))
                break
    # 按业务线去重（同一业务线可能有多个知识库，逐个列出反而干扰判断）
    return [f"{label}（可能应传到：{'、'.join(sorted(names))}）"
            for label, names in sorted(hits.items())]


def iter_files(root, recursive, include_md):
    exts = XMINDS + (MDS if include_md else ())
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("~$") or fn.startswith("."):
                    continue
                if os.path.splitext(fn)[1].lower() in exts:
                    yield os.path.join(dirpath, fn)
    else:
        for fn in sorted(os.listdir(root)):
            p = os.path.join(root, fn)
            if os.path.isfile(p) and not fn.startswith("~$") and os.path.splitext(fn)[1].lower() in exts:
                yield p


def load_manifest(path):
    if not os.path.isfile(path):
        print(f"[错误] 清单文件不存在：{path}", file=sys.stderr)
        raise SystemExit(2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def print_table(items, limit=20):
    print(f"{'ID':>3} | {'状态':<8} | 文件")
    print("-" * 78)
    for it in items[:limit]:
        print(f"{it['id']:>3} | {it['status']:<8} | {it['name']}")
        print(f"    标题 -> {it['title']}")
        if it.get("warn"):
            print(f"    ⚠️  {it['warn']}")
    if len(items) > limit:
        print(f"... 其余 {len(items) - limit} 条（见清单文件）")


# ---------------------------------------------------------------- 子命令
def cmd_scan(args):
    cfg, cfg_path = load_config(args.config)
    if cfg is None:
        print("[错误] 找不到映射配置（skill 内置预设缺失，skill 包可能不完整）", file=sys.stderr)
        raise SystemExit(2)
    if not os.path.isdir(args.dir):
        print(f"[错误] 目录不存在：{args.dir}", file=sys.stderr)
        raise SystemExit(2)

    hits = resolve(cfg, args.biz_line, args.product, args.doc_type, args.kb)
    if not hits:
        print("[错误] 未匹配到知识库 —— 疑似 weknora 里新建了知识库，或归属有变。", file=sys.stderr)
        print("  请询问测试人员：是否新建了知识库？若有，让他只需说一句"
              "「新增了 XX 库，归属 效贷/效融/泾渭云/小贷/智慧记零售/AI进销存」。", file=sys.stderr)
        print("  确认后用：python init_config.py --diff-kb --space <空间ID> --from-json kb_list.json 对账，"
              "再 --add-kb 登记。禁止凭相似名称猜测目标库。", file=sys.stderr)
        raise SystemExit(3)
    if len(hits) > 1:
        print(json.dumps({"error": "命中多个知识库，请用 --kb 指定",
                          "candidates": [f"{k}/{kb.get('name')}" for k, sp, kb, sc in hits]},
                         ensure_ascii=False, indent=2))
        raise SystemExit(3)
    key, sp, kb, _ = hits[0]

    files = list(iter_files(args.dir, args.recursive, args.include_md))
    if not files:
        print("[提示] 目录下没有找到 .xmind 文件（如需包含 md 请加 --include-md）")
        raise SystemExit(2)

    items = []
    for idx, path in enumerate(sorted(files), start=1):
        stem = os.path.splitext(os.path.basename(path))[0]
        story = extract_user_story(stem)
        req = extract_requirement(stem, story,
                                  extra_noise=[args.product, kb.get("product"), args.biz_line])
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        date_str = mtime.strftime("%Y%m%d") if args.date_from == "mtime" else datetime.now().strftime("%Y%m%d")
        title = build_title(cfg, kb, req, story, args.product or kb.get("product"), args.doc_type, date_str)
        warn = ""
        conflicts = alias_conflicts(cfg, args.biz_line or kb.get("biz_line", ""), stem)
        if conflicts:
            warn = f"文件名疑似属于其他业务线：{ '、'.join(conflicts) }，请人工确认"
        items.append({
            "id": idx,
            "source": os.path.abspath(path),
            "name": os.path.basename(path),
            "size": os.path.getsize(path),
            "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
            "user_story": story,
            "requirement": req,
            "title": title,
            "md_path": "",
            "status": "pending",
            "doc_id": "",
            "error": "",
            "warn": warn,
            "updated_at": "",
            # 方案 C：标签名 = 文档类型，人工在网页端勾选；tag_status 记录进度
            "tag": resolve_tag(cfg, args.doc_type)["name"],
            "tag_status": "na",
        })

    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config_path": cfg_path,
        "root": os.path.abspath(args.dir),
        "target": {
            "space_id": sp.get("space_id") or key,
            "space_name": sp.get("space_name") or sp.get("name"),
            "space_url": sp.get("mcp_url", ""),
            "mcp_server": sp.get("mcp_server", ""),
            "mcp_prefix": sp.get("mcp_prefix", ""),
            "kb_id": kb.get("id") or "",
            "kb_name": kb.get("name"),
            "kb_ref": kb.get("id") or kb.get("name"),
            "biz_line": args.biz_line or kb.get("biz_line"),
            "biz_line_name": kb.get("biz_line_name") or kb.get("biz_line"),
            "product": args.product or kb.get("product"),
            "doc_type": args.doc_type,
            "tag": resolve_tag(cfg, args.doc_type)["name"],
            "tag_auto": resolve_tag(cfg, args.doc_type)["auto"],
            "expert": kb.get("expert", ""),
        },
        "md_out_dir": os.path.abspath(args.out_dir) if args.out_dir else os.path.join(os.path.abspath(args.dir), "_weknora_md"),
        "items": items,
    }
    out = args.out or "weknora_batch_manifest.json"
    save_manifest(out, manifest)

    t = manifest["target"]
    print(f"扫描目录：{manifest['root']}")
    print(f"目标空间：{t['space_name']}（空间ID {t['space_id']}）   来源：{config_source(cfg_path)}")
    print(f"业务线：{t.get('biz_line_name')}（{t.get('biz_line')}）   文档类型：{args.doc_type}"
          + (f"   对应专家：{t.get('expert')}" if t.get("expert") else ""))
    print(f"目标知识库：{t['kb_name']}（ID {t['kb_id']}）")
    print(f"weknora 标签：{t.get('tag')}"
          + ("（上传后自动打标）" if t.get("tag_auto")
             else "（当前通道无法写入，上传后需人工在 weknora 页面勾选）"))
    print(f"MCP 前缀：{t.get('mcp_prefix') or '未识别 -> 先跑 init_config.py --discover'}")
    print(f"命中文件：{len(items)}  清单：{os.path.abspath(out)}")
    warns = [i for i in items if i["warn"]]
    if warns:
        print(f"\n⚠️  {len(warns)} 个文件名疑似跨业务线，上传前请逐条确认：")
        for i in warns:
            print(f"  - {i['name']} -> {i['warn']}")
    print()
    print_table(items, limit=args.preview)
    print("\n下一步：确认无误后运行 convert 转 MD；如需调整标题请直接编辑清单 items[].title。")
    if not t.get("tag_auto"):
        print(f"提醒：本次文档类型为「{args.doc_type}」，上传后需在 weknora 网页端给它们打上标签"
              f"「{t.get('tag')}」，打完用 mark --tag-status done 回写进度。")


def cmd_convert(args):
    m = load_manifest(args.manifest)
    out_dir = m.get("md_out_dir") or os.path.join(m["root"], "_weknora_md")
    os.makedirs(out_dir, exist_ok=True)
    ok = fail = skip = 0
    for it in m["items"]:
        if it["status"] in ("converted", "uploaded") and not args.overwrite:
            skip += 1
            continue
        meta = {
            "业务线": m["target"].get("biz_line", ""),
            "产品": m["target"].get("product", ""),
            "用户故事": it.get("user_story", ""),
            "需求": it.get("requirement", ""),
            "标题": it["title"],
            # 方案 C：标签需人工在网页端勾选，写进 MD 头部便于打标时一眼看到该勾哪个
            "weknora标签": m["target"].get("tag") or m["target"].get("doc_type", ""),
        }
        try:
            md, stat = convert(it["source"], meta=meta, style=args.style)
            safe = re.sub(r'[\\/:*?"<>|]', "_", it["title"])
            md_path = os.path.join(out_dir, safe + ".md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            it["md_path"] = md_path
            it["status"] = "converted"
            it["error"] = ""
            it["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ok += 1
        except Exception as e:  # noqa: BLE001
            it["status"] = "failed"
            it["error"] = f"{type(e).__name__}: {e}"
            fail += 1
    save_manifest(args.manifest, m)
    print(json.dumps({"converted": ok, "failed": fail, "skipped": skip,
                      "md_out_dir": out_dir, "manifest": os.path.abspath(args.manifest)},
                     ensure_ascii=False, indent=2))
    for it in m["items"]:
        if it["status"] == "failed":
            print(f"  [失败] {it['name']} -> {it['error']}")


def cmd_mark(args):
    m = load_manifest(args.manifest)
    targets = []
    if args.id:
        ids = {int(x) for x in args.id.split(",")}
        targets = [i for i in m["items"] if i["id"] in ids]
    elif args.name:
        targets = [i for i in m["items"] if args.name.lower() in i["name"].lower()]
    else:
        print("[错误] 需指定 --id 或 --name", file=sys.stderr)
        raise SystemExit(2)
    if not targets:
        print("[错误] 未匹配到清单条目", file=sys.stderr)
        raise SystemExit(2)
    if not args.status and not args.tag_status:
        print("[错误] 需指定 --status 或 --tag-status", file=sys.stderr)
        raise SystemExit(2)
    for it in targets:
        if args.status:
            it["status"] = args.status
        it["doc_id"] = args.doc_id or it.get("doc_id", "")
        if args.title:
            it["title"] = args.title
        if args.error:
            it["error"] = args.error
        # 标签进度：上传成功即待人工打标；未上传无需打标
        if args.status == "uploaded":
            it.setdefault("tag_status", "pending")
            if it.get("tag_status") == "na":
                it["tag_status"] = "pending"
        elif args.status in ("pending", "skipped"):
            it["tag_status"] = "na"
        if args.tag_status:
            it["tag_status"] = args.tag_status
        it["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_manifest(args.manifest, m)
    desc = " / ".join(x for x in [args.status,
                                  f"标签={args.tag_status}" if args.tag_status else ""] if x)
    print(f"[已更新] {len(targets)} 条 -> {desc or '（无变更）'}")
    untag = [i for i in m["items"] if i["status"] == "uploaded" and i.get("tag_status") != "done"]
    if untag:
        tag = m["target"].get("tag") or m["target"].get("doc_type", "")
        print(f"  ⚠️  清单中还有 {len(untag)} 份已上传未打标签「{tag}」，"
              f"打完后执行：mark --id <逗号分隔> --tag-status done")


def cmd_report(args):
    m = load_manifest(args.manifest)
    counts = {}
    for it in m["items"]:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    uploaded = [it for it in m["items"] if it["status"] == "uploaded"]
    untagged = [it for it in uploaded if it.get("tag_status") != "done"]
    tagged = [it for it in uploaded if it.get("tag_status") == "done"]
    default_tag = m["target"].get("tag") or m["target"].get("doc_type", "")

    lines = [f"# 批量上传报告（{m['generated_at']}）", "",
             f"- 源目录：{m['root']}",
             f"- 目标知识库：{m['target']['kb_name']}（空间：{m['target']['space_name']}）",
             f"- weknora 标签：{default_tag}（人工勾选，MCP 无法自动写入）",
             f"- 总数：{len(m['items'])}   " + "  ".join(
                 f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: str(x[0]))),
             f"- 打标进度：已打标 {len(tagged)} / 待打标 {len(untagged)}", "",
             "| ID | 文件 | 标题 | 状态 | 标签 | 文档ID | 备注 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for it in m["items"]:
        ts = it.get("tag_status")
        tag_mark = {"done": "已打标", "na": "—"}.get(ts, "待打标") if ts else "—"
        lines.append(f"| {it['id']} | {it['name']} | {it['title']} | {it['status']} | "
                     f"{tag_mark} | {it.get('doc_id','')} | {it.get('error','')} |")

    # 标签勾选清单：按标签分组，方便在网页端一次勾一类
    if not m["target"].get("tag_auto"):
        lines += ["", "## 待手工打标签勾选清单", "",
                  "weknora 当前 MCP 通道无法写入标签，请在网页端逐类勾选：",
                  "（知识库页 → 勾选下列文档 → 标签 → 添加标签 → 选择对应标签 → 确定）", ""]
        groups = {}
        for it in untagged:
            groups.setdefault(it.get("tag") or default_tag, []).append(it)
        if groups:
            for tag, items in sorted(groups.items()):
                lines.append(f"### 标签「{tag}」（{len(items)} 份）")
                lines.append("")
                for it in items:
                    lines.append(f"- [ ] {it['title']}（文档ID: {it.get('doc_id','') or '-'}）")
                lines.append("")
            lines.append("勾选完成后回写进度：")
            lines.append("")
            lines.append("```")
            lines.append("python scripts/batch_cases.py mark --manifest <清单> --id "
                        + ",".join(str(i["id"]) for i in untagged) + " --tag-status done")
            lines.append("```")
        else:
            lines.append("- （本次没有需要打标签的文档，或已全部打标完成）")
    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n[已写入] {os.path.abspath(args.out)}")
    if untagged:
        print(f"\n⚠️  还有 {len(untagged)} 份已上传但未打标签，请在网页端勾选后回写进度。")


def main():
    ap = argparse.ArgumentParser(description="批量 xmind 用例 -> weknora 上传准备")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="扫描目录并生成上传清单")
    s.add_argument("--dir", required=True, help="历史用例所在目录")
    s.add_argument("--biz-line", help="业务线代码或名称，如 XD / JWY / AIJXC / ZHJLS")
    s.add_argument("--product", help="产品名称")
    s.add_argument("--doc-type", default="测试用例")
    s.add_argument("--kb", help="直接指定知识库名称或 ID（跳过路由推断）")
    s.add_argument("--recursive", action="store_true", help="递归子目录")
    s.add_argument("--include-md", action="store_true", help="同时纳入 .md/.markdown 文件")
    s.add_argument("--date-from", choices=["mtime", "today"], default="mtime", help="标题日期戳来源")
    s.add_argument("--out", help="清单输出路径，默认 ./weknora_batch_manifest.json")
    s.add_argument("--out-dir", help="MD 输出目录，默认 <源目录>/_weknora_md")
    s.add_argument("--preview", type=int, default=20, help="预览条数")
    s.add_argument("--config", help="指定配置文件路径")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("convert", help="按清单批量转 MD")
    c.add_argument("--manifest", required=True)
    c.add_argument("--overwrite", action="store_true", help="已转换的也重新转换")
    c.add_argument("--style", choices=["list", "heading"], default="list")
    c.set_defaults(func=cmd_convert)

    k = sub.add_parser("mark", help="更新清单条目状态")
    k.add_argument("--manifest", required=True)
    k.add_argument("--id", help="条目 ID，多个用逗号分隔")
    k.add_argument("--name", help="按文件名关键字匹配")
    k.add_argument("--status", choices=["pending", "converted", "uploaded", "failed", "skipped"])
    k.add_argument("--tag-status", dest="tag_status", choices=["pending", "done", "na"],
                   help="weknora 标签进度：pending 待人工打标 / done 已打标 / na 无需打标")
    k.add_argument("--doc-id", help="weknora 文档 ID")
    k.add_argument("--title", help="覆盖标题")
    k.add_argument("--error", help="失败原因")
    k.set_defaults(func=cmd_mark)

    r = sub.add_parser("report", help="输出上传结果报告")
    r.add_argument("--manifest", required=True)
    r.add_argument("--out", help="报告输出为 Markdown 文件")
    r.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
