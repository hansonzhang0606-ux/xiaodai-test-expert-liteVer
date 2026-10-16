#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tag_documents.py - 给 weknora 文档打「文档类型」标签（REST 直连通道）。

⚠️ 通道状态：**未联调**。weknora 的标签能力只在 REST 侧开放，MCP 侧（10 个工具）没有
   任何标签参数，且 MCP 令牌对 /api/* 一律 401。本脚本用于「拿到用户级令牌/管理员 API
   Key 之后」立即启用，默认 dry-run，必须显式 --apply 才会写数据。

鉴权（按顺序查找）：
  1) 环境变量 WEKNORA_TOKEN
  2) --token-file 指定的文件（一行，格式 "Bearer xxx" 或仅 "xxx"）
  3) --token 参数（不推荐，会进 shell 历史）
  不接受 MCP 令牌（mcp_xxx）—— 它对 REST 无效。

用法：
  # 0) 通道自检（先做这个）
  python tag_documents.py --check --base-url https://finwiki.kingdee.com

  # 1) 看某知识库现有标签
  python tag_documents.py --kb 5e13077c-225c-4777-b644-528ec4b251e0 --list-tags

  # 2) 确保「测试用例」等 4 个标准标签存在（缺则建）
  python tag_documents.py --kb <KB_ID> --ensure-tags --apply

  # 3) 按文档标题给文档打标签（dry-run 先看计划）
  python tag_documents.py --kb <KB_ID> --title-match "零售版v1.0" --tag 测试用例
  python tag_documents.py --kb <KB_ID> --title-match "零售版v1.0" --tag 测试用例 --apply

  # 4) 或用批量清单（batch_cases.py 产出的 manifest.json）
  python tag_documents.py --kb <KB_ID> --from-manifest batch_manifest.json --apply

退出码：0 成功；2 参数/鉴权问题；3 通道不可用；4 部分条目失败
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://finwiki.kingdee.com"
STANDARD_TAGS = ["测试用例", "测试总结", "测试需求分析", "测试缺陷"]


def load_token(args):
    tok = os.environ.get("WEKNORA_TOKEN")
    if not tok and args.token_file and os.path.isfile(args.token_file):
        with open(args.token_file, "r", encoding="utf-8") as f:
            tok = f.read().strip()
    if not tok:
        tok = (args.token or "").strip()
    if not tok:
        return ""
    if not tok.lower().startswith("bearer "):
        tok = "Bearer " + tok
    return tok


def call(base, path, token, method="GET", body=None, timeout=25):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", token)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw), raw
            except json.JSONDecodeError:
                return r.status, None, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw), raw
        except json.JSONDecodeError:
            return e.code, None, raw
    except Exception as e:
        return -1, None, f"{type(e).__name__}: {e}"


def check_channel(base, token):
    print("=" * 74)
    print("通道自检：REST 是否可用")
    print("=" * 74)
    if not token:
        print("❌ 未提供令牌。请设置环境变量 WEKNORA_TOKEN 或用 --token-file。")
        print("   注意：MCP 令牌（mcp_xxx）对 REST 无效，必须是登录态令牌或管理员 API Key。")
        return False
    code, obj, raw = call(base, "/api/v1/auth/me", token)
    print(f"GET /api/v1/auth/me -> HTTP {code}")
    if code == 200:
        who = (obj or {}).get("data") or (obj or {})
        if isinstance(who, dict):
            print(f"✅ 令牌有效：{who.get('username') or who.get('email') or who.get('id') or '已认证'}")
        else:
            print("✅ 令牌有效")
        return True
    if code == 401:
        print("❌ 401：令牌无效或过期（若你用的是 mcp_xxx，请换成登录态令牌）。")
        return False
    print(f"⚠️  非预期响应：{raw[:200]}")
    return False


def kb_tags(base, token, kb):
    code, obj, raw = call(base, f"/api/v1/knowledge-bases/{kb}/tags", token)
    if code != 200:
        print(f"[错误] 读取标签失败 HTTP {code}：{raw[:200]}", file=sys.stderr)
        return None
    data = (obj or {}).get("data")
    if isinstance(data, dict):
        data = data.get("items") or data.get("tags") or []
    return data or []


def find_tag_id(tags, name):
    for t in tags:
        if (t.get("name") or "").strip() == name.strip():
            return t.get("id")
    return None


def ensure_tags(base, token, kb, names, apply_flag):
    tags = kb_tags(base, token, kb)
    if tags is None:
        return None
    missing = [n for n in names if not find_tag_id(tags, n)]
    if not missing:
        print(f"✅ 标签齐备：{', '.join(names)}")
        return tags
    print(f"待创建标签：{', '.join(missing)}")
    if not apply_flag:
        print("（dry-run：未创建，加 --apply 执行）")
        return tags
    for n in missing:
        code, obj, raw = call(base, f"/api/v1/knowledge-bases/{kb}/tags", token,
                              "POST", {"name": n})
        ok = code in (200, 201)
        print(f"  {'✅' if ok else '❌'} 创建「{n}」 HTTP {code}" + ("" if ok else f" {raw[:160]}"))
    return kb_tags(base, token, kb)


def assign(base, token, kb, tag_id, tag_name, doc_ids, apply_flag):
    ok = fail = 0
    for did in doc_ids:
        body = {"knowledge_base_id": kb, "knowledge_ids": [did], "tag_ids": [tag_id]}
        if not apply_flag:
            print(f"  [dry-run] 给文档 {did} 打标签「{tag_name}」")
            ok += 1
            continue
        code, obj, raw = call(base, "/api/v1/knowledge/tags", token, "PUT", body)
        if code in (200, 201, 204):
            print(f"  ✅ {did} <- {tag_name}")
            ok += 1
        else:
            print(f"  ❌ {did} HTTP {code} {raw[:160]}")
            fail += 1
    return ok, fail


def main():
    ap = argparse.ArgumentParser(description="weknora 文档类型标签写入（REST 通道）")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--token")
    ap.add_argument("--token-file")
    ap.add_argument("--kb", help="知识库 ID 或精确名称")
    ap.add_argument("--list-tags", action="store_true")
    ap.add_argument("--ensure-tags", action="store_true", help="确保 4 个标准标签存在")
    ap.add_argument("--tag", help="要打的标签名，如 测试用例")
    ap.add_argument("--doc-ids", help="逗号分隔的文档 ID")
    ap.add_argument("--title-match", help="按标题子串筛选文档")
    ap.add_argument("--from-manifest", help="batch_cases.py 生成的 manifest.json")
    ap.add_argument("--check", action="store_true", help="仅做通道自检")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    args = ap.parse_args()

    token = load_token(args)
    if args.check:
        raise SystemExit(0 if check_channel(args.base_url, token) else 3)
    if not args.kb:
        print("[错误] 需要 --kb", file=sys.stderr)
        raise SystemExit(2)
    if not check_channel(args.base_url, token):
        raise SystemExit(3)

    if args.list_tags:
        tags = kb_tags(args.base_url, token, args.kb)
        if tags is None:
            raise SystemExit(3)
        print(json.dumps(tags, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    if args.ensure_tags:
        tags = ensure_tags(args.base_url, token, args.kb, STANDARD_TAGS, args.apply)
        raise SystemExit(0 if tags is not None else 3)

    # ---- 打标签 ----
    tags = kb_tags(args.base_url, token, args.kb)
    if tags is None:
        raise SystemExit(3)
    names = [args.tag] if args.tag else []
    if args.from_manifest and not names:
        print("[错误] --from-manifest 需要配合 --tag（或先看 plan 输出）", file=sys.stderr)
        raise SystemExit(2)
    if not names:
        print("[错误] 需要 --tag，或使用 --list-tags / --ensure-tags", file=sys.stderr)
        raise SystemExit(2)

    tag_name = names[0]
    tag_id = find_tag_id(tags, tag_name)
    if not tag_id:
        print(f"[错误] 知识库中不存在标签「{tag_name}」。先跑 --ensure-tags。", file=sys.stderr)
        raise SystemExit(2)

    doc_ids = [d.strip() for d in (args.doc_ids or "").split(",") if d.strip()]
    if args.title_match:
        code, obj, raw = call(
            args.base_url,
            f"/api/v1/knowledge-bases/{args.kb}/knowledge?keyword={urllib.parse.quote(args.title_match)}",
            token)
        data = (obj or {}).get("data") if isinstance(obj, dict) else None
        items = (data or {}).get("items") if isinstance(data, dict) else data
        for it in (items or []):
            if it.get("id"):
                doc_ids.append(it["id"])
        if code != 200:
            print(f"⚠️  列出文档失败 HTTP {code}，请改用 --doc-ids 或 --from-manifest：{raw[:160]}")

    if args.from_manifest:
        with open(args.from_manifest, "r", encoding="utf-8") as f:
            man = json.load(f)
        for it in man.get("items", []):
            if it.get("doc_id"):
                doc_ids.append(it["doc_id"])

    if not doc_ids:
        print("[错误] 没有可打标签的文档（doc-ids / title-match / from-manifest 均为空）",
              file=sys.stderr)
        raise SystemExit(2)

    print(f"知识库：{args.kb}\n标签：{tag_name}（id={tag_id}）\n文档数：{len(doc_ids)}"
          f"{'' if args.apply else '   【dry-run】'}")
    ok, fail = assign(args.base_url, token, args.kb, tag_id, tag_name, doc_ids, args.apply)
    print(f"\n完成：成功 {ok}，失败 {fail}")
    raise SystemExit(0 if fail == 0 else 4)


if __name__ == "__main__":
    main()
