#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xmind_to_md.py - 将 xmind 测试用例转换为可上传到 weknora 的 Markdown。

支持输入:
  *.xmind      新版(XMind Zen / 2020+, zip 内 content.json) 与旧版(zip 内 content.xml)
  *.md/*.markdown  直接透传(仅补齐元信息头)

仅依赖标准库。输出 Markdown 保留脑图层级结构、节点备注、标签与标记。

用法:
  python xmind_to_md.py input.xmind -o output.md
  python xmind_to_md.py input.xmind -o output.md --meta 业务线=效贷 --meta 用户故事=PRJ-00770309
  python xmind_to_md.py draft.md -o final.md --meta 产品=效贷
  python xmind_to_md.py input.xmind --stdout
"""

import argparse
import json
import os
import sys
import zipfile
from datetime import datetime
import xml.etree.ElementTree as ET

MD_EXT = (".md", ".markdown", ".txt")


# ---------------------------------------------------------------- 解析新版 content.json
def _json_topic(node, depth, lines):
    title = (node.get("title") or "").strip()
    if not title:
        title = "(未命名节点)"
    lines.append((depth, title))

    notes = ""
    try:
        notes = (node.get("notes", {}).get("plain", {}).get("content") or "").strip()
    except AttributeError:
        notes = ""
    if not notes:
        try:
            notes = (node.get("notes", {}).get("realHTMLContent") or "").strip()
        except AttributeError:
            notes = ""
    labels = node.get("labels") or []
    markers = [m.get("markerId") for m in (node.get("markers") or []) if isinstance(m, dict)]

    extra = []
    if labels:
        extra.append("标签：" + "、".join(str(x) for x in labels))
    if markers:
        extra.append("标记：" + "、".join(str(x) for x in markers))
    if notes:
        note_line = notes.replace("\r\n", "\n").replace("\r", "\n")
        for seg in note_line.split("\n"):
            seg = seg.strip()
            if seg:
                extra.append("备注：" + seg)
    for e in extra:
        lines.append((depth + 1, e))

    children = (node.get("children") or {}).get("attached") or []
    for child in children:
        if isinstance(child, dict):
            _json_topic(child, depth + 1, lines)


def parse_content_json(data, lines):
    sheets = data if isinstance(data, list) else [data]
    sheet_titles = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        sheet_title = (sheet.get("title") or "").strip()
        root = sheet.get("rootTopic")
        if not root:
            continue
        if sheet_title:
            sheet_titles.append(sheet_title)
            lines.append((0, sheet_title))
            base = 1
        else:
            base = 0
        _json_topic(root, base, lines)
    return sheet_titles


# ---------------------------------------------------------------- 解析旧版 content.xml
def _strip_ns(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _find_child(node, name):
    """按忽略命名空间的标签名查找直接子元素。"""
    for child in node:
        if _strip_ns(child.tag) == name:
            return child
    return None


def _xml_topic(node, depth, lines):
    title = ""
    notes = ""
    labels = []
    children = []
    for child in node:
        tag = _strip_ns(child.tag)
        if tag == "title":
            title = (child.text or "").strip()
        elif tag == "notes":
            for sub in child.iter():
                if _strip_ns(sub.tag) == "plain" and sub.text:
                    notes = sub.text.strip()
        elif tag == "labels":
            for sub in child:
                labels.append((sub.text or "").strip())
        elif tag == "children":
            for sub in child:
                if _strip_ns(sub.tag) == "topics":
                    children.extend(list(sub))
    lines.append((depth, title or "(未命名节点)"))
    if labels:
        lines.append((depth + 1, "标签：" + "、".join(labels)))
    if notes:
        for seg in notes.replace("\r\n", "\n").split("\n"):
            seg = seg.strip()
            if seg:
                lines.append((depth + 1, "备注：" + seg))
    for c in children:
        _xml_topic(c, depth + 1, lines)


def parse_content_xml(xml_text, lines):
    root = ET.fromstring(xml_text)
    sheet_titles = []
    for sheet in root.iter():
        if _strip_ns(sheet.tag) != "sheet":
            continue
        title_el = _find_child(sheet, "title")
        sheet_title = (title_el.text or "").strip() if title_el is not None else ""
        topic = _find_child(sheet, "topic")
        if topic is None:
            continue
        if sheet_title:
            sheet_titles.append(sheet_title)
            lines.append((0, sheet_title))
            _xml_topic(topic, 1, lines)
        else:
            _xml_topic(topic, 0, lines)
    return sheet_titles


# ---------------------------------------------------------------- 渲染 Markdown
def render_markdown(lines, style="list"):
    """style=list -> 缩进列表；style=heading -> 前3层用标题、其余用列表。"""
    out = []
    for depth, text in lines:
        if style == "heading" and depth < 3:
            out.append("#" * (depth + 1) + " " + text)
            out.append("")
        else:
            indent = "  " * min(depth, 12)
            out.append(f"{indent}- {text}")
    return "\n".join(out)


def build_meta_block(meta, source_name):
    if not meta:
        meta = {}
    meta.setdefault("生成日期", datetime.now().strftime("%Y-%m-%d"))
    meta.setdefault("来源文件", source_name)
    parts = [f"{k}：{v}" for k, v in meta.items() if v]
    return "> " + " | ".join(parts) if parts else ""


def convert(path, meta=None, style="list"):
    ext = os.path.splitext(path)[1].lower()
    base_name = os.path.basename(path)

    if ext in MD_EXT:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
        lines_cnt = body.count("\n") + 1
        md_body = body
        fmt = "markdown(透传)"
    elif ext == ".xmind":
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "content.json" in names:
                data = json.loads(z.read("content.json").decode("utf-8"))
                lines = []
                parse_content_json(data, lines)
                fmt = "xmind(content.json)"
            elif "content.xml" in names:
                lines = []
                parse_content_xml(z.read("content.xml").decode("utf-8"), lines)
                fmt = "xmind(content.xml)"
            else:
                raise SystemExit("无法识别的 xmind 结构：zip 内既无 content.json 也无 content.xml")
        md_body = render_markdown(lines, style=style)
        lines_cnt = len(lines)
    else:
        raise SystemExit(f"不支持的输入类型：{ext}（仅支持 .xmind / .md / .markdown）")

    head = build_meta_block(meta, base_name)
    doc_title = (meta or {}).get("标题") or os.path.splitext(base_name)[0]
    parts = [f"# {doc_title}", ""]
    if head:
        parts += [head, ""]
    parts += [md_body, ""]
    return "\n".join(parts), {"format": fmt, "nodes": lines_cnt, "source": base_name}


def main():
    ap = argparse.ArgumentParser(description="xmind 测试用例 -> Markdown（供 weknora 上传）")
    ap.add_argument("input", help=".xmind 或 .md 文件路径")
    ap.add_argument("-o", "--output", help="输出 Markdown 路径；缺省为输入同目录同名 .md")
    ap.add_argument("--meta", action="append", default=[], metavar="KEY=VALUE",
                    help="元信息，可重复，如 --meta 业务线=效贷 --meta 用户故事=PRJ-00770309")
    ap.add_argument("--style", choices=["list", "heading"], default="list",
                    help="list=缩进列表(默认, 保留完整层级)；heading=前3层渲染为标题")
    ap.add_argument("--stdout", action="store_true", help="仅打印到标准输出，不落盘")
    args = ap.parse_args()

    meta = {}
    for item in args.meta:
        if "=" in item:
            k, v = item.split("=", 1)
            meta[k.strip()] = v.strip()

    md, stat = convert(args.input, meta=meta, style=args.style)

    if args.stdout:
        sys.stdout.write(md)
        return

    out = args.output or os.path.splitext(args.input)[0] + ".md"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)

    print(json.dumps({"output": os.path.abspath(out), **stat}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
