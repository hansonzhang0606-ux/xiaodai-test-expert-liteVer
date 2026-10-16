#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_config.py - weknora 归档路由配置：内置预设 + MCP 服务器自动识别。

设计要点（v2.1）:
  * 测试人员**唯一要做的事**是在 AI 工具里配 MCP 连接器（url + Authorization）。
    除此之外没有任何需要人工维护的配置文件。
  * 团队映射表（空间ID / 空间名称 / 业务线 / 知识库 / 知识库ID / 对应专家）内置在
    assets/preset_kb_mapping.json，随 skill 分发，开箱即可路由。
  * MCP 服务器名由各人在连接器中自定义，不是固定值。脚本按 mcp_url 自动识别本机
    服务器名并推导工具前缀（--discover），因此连接器只需保证 url + Authorization 正确。
  * 后续新增知识库：由智能体发现并与测试人员确认归属后，用 --add-kb / --sync-kb
    直接写回**内置预设**（默认 --target preset），随 skill 升级分发给全团队。
    本地覆盖配置（--target local）仅供排障临时使用，不是给测试人员的操作。

用法:
  python init_config.py --list                    # 列出生效映射
  python init_config.py --doctor                  # 体检：映射来源 + 三个空间连接器识别结果
  python init_config.py --discover                # 按 url 识别本机 MCP 服务器名与工具前缀
  python init_config.py --validate
  python init_config.py --diff-kb --space 10004 --from-json kb_list.json
  python init_config.py --add-kb  --space 10004 --name "效贷_测试_测试缺陷" --id <ID>
  python init_config.py --sync-kb --space 10006 --from-json kb_list.json
  python init_config.py --init-local --force      # （智能体排障用）复制预设为本地覆盖
"""

import argparse
import json
import os
import re
import sys

PRESET_NAME = "preset_kb_mapping.json"
CONFIG_NAME = "weknora_mcp.json"


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
def skill_root():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def preset_path():
    return os.path.normpath(os.path.join(skill_root(), "assets", PRESET_NAME))


def user_config_path():
    return os.path.join(os.path.expanduser("~"), ".workbuddy", CONFIG_NAME)


def workspace_config_path():
    return os.path.join(os.getcwd(), ".workbuddy", CONFIG_NAME)


def candidate_paths():
    """优先级：工作区本地 > 用户级本地 > skill 内置预设。"""
    return [workspace_config_path(), user_config_path(), preset_path()]


def local_config_paths():
    return [workspace_config_path(), user_config_path()]


def find_local_config():
    for p in local_config_paths():
        if os.path.isfile(p):
            return p
    return None


def config_source(p):
    """返回 workspace / user / preset。"""
    if not p:
        return ""
    n = os.path.normpath(p)
    if n == os.path.normpath(workspace_config_path()):
        return "workspace"
    if n == os.path.normpath(user_config_path()):
        return "user"
    if n == os.path.normpath(preset_path()):
        return "preset"
    return "custom"


def is_preset(p):
    return config_source(p) == "preset"


def load_config(path=None):
    """返回 (cfg, path)。cfg 为 None 表示连内置预设都读不到（属异常）。"""
    paths = [path] if path else candidate_paths()
    for p in paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f), p
            except json.JSONDecodeError as e:
                print(f"[错误] 配置文件不是合法 JSON：{p}\n       {e}", file=sys.stderr)
                raise SystemExit(2)
    return None, None


def ensure_writable_config(prefer="user"):
    """（排障用）返回一个可写的本地覆盖配置路径；不存在时从预设复制一份。"""
    existing = find_local_config()
    if existing:
        return existing
    dst = user_config_path() if prefer == "user" else workspace_config_path()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    src = preset_path()
    if os.path.isfile(src):
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"version": "2.0", "spaces": {}}
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[已生成本地覆盖配置] {dst}（仅供排障，日常不需要；删除即回退到内置预设）")
    return dst


def resolve_write_path(args):
    """知识库登记的写入目标。

    默认写回 skill 内置预设（团队标准映射，随 skill 升级分发给全团队，
    测试人员无需任何操作）。仅 --target local 时写本地覆盖（排障用）。
    """
    if getattr(args, "target", "preset") == "local":
        return ensure_writable_config(getattr(args, "scope", "user"))
    src = preset_path()
    if not os.path.isfile(src):
        print(f"[错误] 内置预设不存在，无法写入：{src}", file=sys.stderr)
        raise SystemExit(1)
    return src


# --------------------------------------------------------------------------- #
# 空间工具
# --------------------------------------------------------------------------- #
def resolve_space_key(spaces, s):
    """--space 参数兼容：空间ID / 空间名称 / 端点UUID / 服务器名。"""
    if not s:
        return None
    if s in spaces:
        return s
    t = str(s).strip().lower()
    for k, sp in spaces.items():
        cands = [
            str(k).lower(),
            str(sp.get("space_id") or "").lower(),
            str(sp.get("space_name") or "").lower(),
            str(sp.get("mcp_server") or "").lower(),
            str(sp.get("mcp_server_hint") or "").lower(),
            str(sp.get("mcp_endpoint_uuid") or "").lower(),
        ]
        if t in cands:
            return k
    return None


def space_label(sp, key=None):
    sid = sp.get("space_id") or key or ""
    sname = sp.get("space_name") or sp.get("name") or ""
    return f"{sname}（空间ID {sid}）" if sid else sname


def match_space_by_url(spaces, url):
    u = (url or "").strip().lower()
    if not u:
        return None
    for key, sp in spaces.items():
        uid = str(sp.get("mcp_endpoint_uuid") or "").lower()
        if uid and uid in u:
            return key
    tail = u.rstrip("/").rsplit("/", 1)[-1]
    if tail:
        for key, sp in spaces.items():
            if tail == str(sp.get("mcp_endpoint_uuid") or "").lower():
                return key
    return None


# --------------------------------------------------------------------------- #
# MCP 服务器自动识别
# --------------------------------------------------------------------------- #
def mcp_candidate_files():
    home = os.path.expanduser("~")
    cwd = os.getcwd()
    return [
        ("WorkBuddy", os.path.join(home, ".workbuddy", "mcp.json")),
        ("Claude Code", os.path.join(home, ".claude.json")),
        ("Claude Code", os.path.join(home, ".claude", "mcp.json")),
        ("Cursor", os.path.join(home, ".cursor", "mcp.json")),
        ("Cursor(项目)", os.path.join(cwd, ".cursor", "mcp.json")),
        ("VS Code", os.path.join(cwd, ".vscode", "mcp.json")),
        ("通用", os.path.join(cwd, ".mcp.json")),
    ]


def iter_mcp_servers():
    """产出本机各 AI 工具里已配置的 MCP 服务器（不含令牌明文）。"""
    seen = set()
    for label, f in mcp_candidate_files():
        if not os.path.isfile(f) or f in seen:
            continue
        seen.add(f)
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        if not isinstance(servers, dict):
            continue
        for name, spec in servers.items():
            if not isinstance(spec, dict):
                continue
            url = spec.get("url") or spec.get("serverUrl") or ""
            headers = spec.get("headers") or {}
            if not isinstance(headers, dict):
                headers = {}
            has_auth = any(k.lower() == "authorization" for k in headers)
            yield {
                "client": label,
                "file": f,
                "server_name": name,
                "url": url,
                "has_auth": has_auth,
            }


def discover(cfg):
    """按 url 把本机 MCP 服务器匹配到预设空间。"""
    spaces = cfg.get("spaces") or {}
    matched, unmatched_weknora = {}, []
    for s in iter_mcp_servers():
        key = match_space_by_url(spaces, s.get("url"))
        if key:
            matched.setdefault(key, []).append(s)
        elif "weknora" in (s.get("server_name") or "").lower() or "finwiki" in (s.get("url") or "").lower():
            unmatched_weknora.append(s)
    missing = [k for k in spaces if k not in matched]
    return {"matched": matched, "missing": missing, "unmatched": unmatched_weknora}


def cmd_discover(args):
    cfg, p = load_config(args.config)
    if cfg is None:
        print("[错误] 找不到任何映射配置（内置预设缺失，skill 包可能不完整）", file=sys.stderr)
        raise SystemExit(1)
    spaces = cfg.get("spaces") or {}
    res = discover(cfg)
    print(f"映射来源：{p}（{config_source(p)}）")
    print("=" * 72)
    print("本机 MCP 连接器识别（按 mcp_url 匹配，服务器名可自定义，无需固定）")
    print("=" * 72)

    for key, sp in spaces.items():
        hits = res["matched"].get(key, [])
        print(f"\n空间 {space_label(sp, key)}")
        print(f"  权威标识 url：{sp.get('mcp_url', '') or '(未登记)'}")
        if not hits:
            print("  ❌ 本机未识别到对应连接器 —— 需在连接器中新增该空间的 MCP（url + Authorization）")
            continue
        for h in hits:
            is_wb = h["client"] == "WorkBuddy"
            prefix = f"mcp__{h['server_name']}__" if is_wb else ""
            auth = "✅ 已含 Authorization" if h["has_auth"] else "⚠️  未检测到 Authorization 头"
            print(f"  ✅ 服务器名：{h['server_name']}｜{h['client']}｜{auth}")
            if prefix:
                print(f"     工具前缀：{prefix}")
            else:
                print("     工具前缀：非 WorkBuddy 客户端，实际工具名以其宿主为准（请在会话中确认可用工具）")
        if len(hits) > 1:
            print(f"  ⚠️  识别到 {len(hits)} 个条目指向同一空间，请确认使用哪一个")

    if res["unmatched"]:
        print("\n⚠️  以下 weknora 类服务器无法与预设空间对应（url 端点不匹配，可能是测试环境或已改名）：")
        for s in res["unmatched"]:
            print(f"  - {s['server_name']}（{s['client']}）url={s['url']}")

    if res["missing"]:
        print("\n⚠️  以下空间在本机没有连接器：", "、".join(space_label(spaces[k], k) for k in res["missing"]))
        print("   配置要点：url 必须与上表「权威标识 url」一致；Authorization 填 Bearer <令牌>（向团队管理员索取）。")

    # 不写任何本地文件：服务器名因人而异（各人自定义），写成配置反而会在
    # skill 升级预设后被旧副本覆盖。每次进入跑一次 --discover 即可，成本极低。
    if args.write:
        print("\n[提示] --write 已废弃：识别结果不落盘，避免本地旧副本覆盖 skill 升级后的预设。")
    return res


# --------------------------------------------------------------------------- #
# 知识库条目构造
# --------------------------------------------------------------------------- #
def parse_kb_name(name):
    """AI零售_测试_测试缺陷 -> (AI零售, 测试缺陷)"""
    m = re.match(r"^(.+?)_测试_(.+)$", name or "")
    if m:
        return m.group(1), m.group(2)
    return (name or ""), ""


def infer_from_siblings(space, prefix):
    for kb in (space.get("knowledge_bases") or []):
        p, _ = parse_kb_name(kb.get("name", ""))
        if p == prefix:
            return {
                "biz_line": kb.get("biz_line", ""),
                "biz_line_name": kb.get("biz_line_name", ""),
                "biz_line_alias": kb.get("biz_line_alias", []),
                "product": kb.get("product", ""),
                "product_alias": kb.get("product_alias", []),
                "expert": kb.get("expert", ""),
            }
    return {}


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def cmd_create(scope, force):
    src = preset_path()
    if not os.path.isfile(src):
        print(f"[错误] 未找到内置预设：{src}", file=sys.stderr)
        raise SystemExit(1)
    dst = workspace_config_path() if scope == "workspace" else user_config_path()
    if os.path.isfile(dst) and not force:
        print(f"[跳过] 本地配置已存在：{dst}（如需覆盖请加 --force）")
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[已生成] {dst}")
    print("  说明：日常无需这一步。只有要新增知识库或覆盖预设映射时才需要本地配置。")
    return dst


def cmd_add_kb(args):
    cfg, p = load_config(args.config)
    if cfg is None:
        print("[错误] 找不到映射配置", file=sys.stderr)
        raise SystemExit(1)
    key = resolve_space_key(cfg.get("spaces") or {}, args.space)
    if key is None:
        print(f"[错误] 没有空间 {args.space}；可用：{', '.join((cfg.get('spaces') or {}).keys())}", file=sys.stderr)
        raise SystemExit(2)
    # 写入目标：默认 skill 内置预设（团队标准），--target local 时才写本地覆盖
    p = resolve_write_path(args)
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    space = cfg["spaces"][key]
    kbs = space.setdefault("knowledge_bases", [])
    for kb in kbs:
        if kb.get("name") == args.name or (args.id and kb.get("id") == args.id):
            if not args.force:
                print(f"[跳过] 知识库已存在：{kb.get('name')}（如需更新请加 --force）")
                return
            kb["id"] = args.id or kb.get("id", "")
            for fld, val in (("doc_type", args.doc_type), ("biz_line", args.biz_line), ("product", args.product)):
                if val:
                    kb[fld] = val
            break
    else:
        prefix, dtype = parse_kb_name(args.name)
        inh = infer_from_siblings(space, prefix)
        kbs.append({
            "id": args.id or "",
            "name": args.name,
            "biz_line": args.biz_line or inh.get("biz_line", ""),
            "biz_line_name": inh.get("biz_line_name", ""),
            "biz_line_alias": inh.get("biz_line_alias", []),
            "product": args.product or inh.get("product", ""),
            "product_alias": inh.get("product_alias", []),
            "doc_type": args.doc_type or dtype,
            "expert": inh.get("expert", ""),
            "_added": "用户新增",
        })
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tag = "内置预设（团队标准，随 skill 升级分发）" if is_preset(p) else "本地覆盖配置（排障用）"
    print(f"[已登记] {space_label(space, key)} / {args.name}（id={args.id or '空->用名称'}）")
    print(f"  写入：{p}｜{tag}")


def cmd_sync_kb(args):
    cfg, p = load_config(args.config)
    if cfg is None:
        print("[错误] 找不到映射配置", file=sys.stderr)
        raise SystemExit(1)
    key = resolve_space_key(cfg.get("spaces") or {}, args.space)
    if key is None:
        print(f"[错误] 没有空间 {args.space}", file=sys.stderr)
        raise SystemExit(2)
    p = resolve_write_path(args)
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    with open(args.from_json, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("knowledge_bases", raw) if isinstance(raw, dict) else raw
    space = cfg["spaces"][key]
    kbs = space.setdefault("knowledge_bases", [])
    known = {(kb.get("name") or "").lower() for kb in kbs}
    known_ids = {(kb.get("id") or "").lower() for kb in kbs if kb.get("id")}
    added, updated = [], []
    for it in items:
        name, kid = it.get("name", ""), it.get("id", "")
        if not name:
            continue
        prefix, dtype = parse_kb_name(name)
        inh = infer_from_siblings(space, prefix)
        if name.lower() in known:
            for kb in kbs:
                if (kb.get("name") or "").lower() == name.lower() and kid and not kb.get("id"):
                    kb["id"] = kid
                    updated.append(name)
            continue
        if kid and kid.lower() in known_ids:
            continue
        kbs.append({
            "id": kid, "name": name,
            "biz_line": inh.get("biz_line", ""),
            "biz_line_name": inh.get("biz_line_name", ""),
            "biz_line_alias": inh.get("biz_line_alias", []),
            "product": inh.get("product", ""),
            "product_alias": inh.get("product_alias", []),
            "doc_type": dtype,
            "expert": inh.get("expert", ""),
        })
        known.add(name.lower())
        added.append(f"{name}(doc_type={dtype})")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tag = "内置预设（团队标准，随 skill 升级分发）" if is_preset(p) else "本地覆盖配置（排障用）"
    print(f"[同步完成] {p}｜{tag}\n  新增 {len(added)}：{added}\n  补ID {len(updated)}：{updated}")
    if added:
        print("  提示：新增条目继承同前缀知识库的业务线/产品/别名；为空时请用 --add-kb 补。")


def cmd_diff_kb(args):
    cfg, p = load_config(args.config)
    if cfg is None:
        print("[错误] 找不到映射配置", file=sys.stderr)
        raise SystemExit(1)
    key = resolve_space_key(cfg.get("spaces") or {}, args.space)
    if key is None:
        print(f"[错误] 没有空间 {args.space}", file=sys.stderr)
        raise SystemExit(2)
    with open(args.from_json, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("knowledge_bases", raw) if isinstance(raw, dict) else raw
    space = cfg["spaces"][key]
    kbs = space.get("knowledge_bases", [])
    cfg_names = {(kb.get("name") or "").lower(): kb for kb in kbs}
    wek_names = {(it.get("name") or "").lower() for it in items if it.get("name")}

    unregistered = []
    for it in items:
        name = it.get("name", "")
        if not name or name.lower() in cfg_names:
            continue
        prefix, dtype = parse_kb_name(name)
        inh = infer_from_siblings(space, prefix)
        unregistered.append({
            "name": name, "id": it.get("id", ""), "description": it.get("description", ""),
            "suggested_doc_type": dtype, "suggested_biz_line": inh.get("biz_line", ""),
            "suggested_product": inh.get("product", ""),
        })
    orphan = [{"name": kb.get("name"), "id": kb.get("id")}
              for n, kb in cfg_names.items() if n not in wek_names]

    out = {"config_path": p, "source": config_source(p), "space": key,
           "space_id": space.get("space_id"), "space_name": space.get("space_name"),
           "unregistered": unregistered, "missing_in_weknora": orphan}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if unregistered:
        print("\n⚠️  发现未在映射中登记的知识库，上传前必须与测试人员确认归属：")
        for u in unregistered:
            print(f"  - {u['name']}（id={u['id']}）建议 doc_type={u['suggested_doc_type']} / biz_line={u['suggested_biz_line'] or '待补'}")
        print(f"  登记命令：python init_config.py --add-kb --space {key} --name \"<名称>\" --id <ID>")
    if orphan:
        print("\n⚠️  映射里有但 weknora 中不存在的知识库（可能已改名/删除，建议人工核实）：")
        for o in orphan:
            print(f"  - {o['name']}（id={o['id']}）")
    if not unregistered and not orphan:
        print("\n✅ 该空间的知识库与映射完全一致。")


def preset_equivalent(cfg):
    """本地配置是否是内置预设的冗余副本（没有预设之外的条目）。"""
    try:
        with open(preset_path(), "r", encoding="utf-8") as f:
            pre = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    def sig(c):
        return {(kb.get("name"), kb.get("id", ""))
                for s in (c.get("spaces") or {}).values()
                for kb in s.get("knowledge_bases", [])}
    return sig(cfg) <= sig(pre)


def cmd_doctor(args):
    cfg, p = load_config(args.config)
    local = find_local_config()
    print("=" * 72)
    print("weknora 归档接入体检")
    print("=" * 72)
    print("\n测试人员只需做一件事：在 AI 工具里配好 MCP 连接器（url + Authorization）。")
    print("映射表内置在 skill 中，不需要任何本地 json 配置。")

    if cfg is None:
        print("\n① 团队映射表：❌ 找不到内置预设 assets/%s" % PRESET_NAME)
        print("   skill 包不完整，请重新解压安装。")
        raise SystemExit(1)

    src = config_source(p)
    if src == "preset":
        print(f"\n① 团队映射表：✅ 使用 skill 内置预设（团队标准映射，无需配置）")
        print(f"   文件：{p}")
    else:
        print(f"\n① 团队映射表：✅ 使用本地配置（{src}）")
        print(f"   文件：{p}")
        if preset_equivalent(cfg):
            print("   ⚠️  该本地配置与内置预设没有差异，属于冗余副本")
            print("       它会盖住 skill 升级后的新预设 —— 建议删除，直接删：")
            print(f"       rm \"{p}\"")
        else:
            print("   ⚠️  本地配置优先于内置预设：skill 升级后新增的知识库不会生效，")
            print("       排障结束后建议删除它（或把新增条目并入内置预设）。")

    spaces = cfg.get("spaces") or {}
    total_kb = sum(len(s.get("knowledge_bases", [])) for s in spaces.values())
    print(f"   空间 {len(spaces)} 个 / 知识库 {total_kb} 条")

    res = discover(cfg)
    print("\n② MCP 连接器（按 url 自动识别，服务器名可自定义，无需与预设一致）")
    for key, sp in spaces.items():
        hits = res["matched"].get(key, [])
        kb_n = len(sp.get("knowledge_bases", []))
        if hits:
            names = "、".join(h["server_name"] for h in hits)
            auth_ok = all(h["has_auth"] for h in hits)
            flag = "✅" if auth_ok else "⚠️ "
            print(f"   {flag} {space_label(sp, key)}：{kb_n} 个知识库｜连接器 {names}"
                  + ("" if auth_ok else "（未检测到 Authorization 头）"))
        else:
            print(f"   ❌ {space_label(sp, key)}：{kb_n} 个知识库｜本机未配置连接器")
            print(f"        需要配置的 url：{sp.get('mcp_url', '') or '(未登记)'}")
            print(f"        headers：Authorization = Bearer <令牌>（向团队管理员索取）")
    if not res["matched"]:
        print("\n   提醒：若本机确实已在 WorkBuddy 连接器中配好，可能是配置文件位置不是默认路径；")
        print("        也可直接在会话里调用 mcp__<服务器名>__list_knowledge_bases 验证连通性。")

    print("\n③ 验证命令")
    print("   python scripts/init_config.py --discover   # 重点：看连接器是否识别到、工具前缀是什么")
    print("   python scripts/init_config.py --list       # 看内置映射（3 空间 / 8 知识库）")
    print("   python scripts/init_config.py --validate")
    print("   MCP 连通后：python scripts/init_config.py --diff-kb --space <空间ID> --from-json kb_list.json")
    print("\n② 里出现 ❌ 即该空间还没配连接器 —— 按 references/first_use_checklist.md 配置即可。")
    raise SystemExit(0)


def cmd_validate(path=None):
    cfg, p = load_config(path)
    if cfg is None:
        print("[错误] 找不到任何映射配置（内置预设缺失）")
        raise SystemExit(1)
    problems, warnings = [], []
    spaces = cfg.get("spaces") or {}
    if not spaces:
        problems.append("spaces 为空")
    for key, sp in spaces.items():
        if not sp.get("space_id") and not key.isdigit():
            warnings.append(f"空间 {key} 缺少 space_id（空间身份应以 weknora 空间ID 为准）")
        if not sp.get("mcp_url"):
            warnings.append(f"空间 {key}（{sp.get('space_name', '')}）缺少 mcp_url，无法自动识别连接器")
        kbs = sp.get("knowledge_bases", [])
        if not kbs:
            warnings.append(f"空间 {key} 没有任何知识库条目")
        for kb in kbs:
            if not kb.get("name"):
                problems.append(f"[{sp.get('space_name', key)}] 存在缺少 name 的知识库条目")
            if not kb.get("id"):
                warnings.append(f"[{sp.get('space_name', key)}] 知识库「{kb.get('name')}」id 为空 -> 将用名称调用 MCP")
            if not kb.get("biz_line"):
                warnings.append(f"[{sp.get('space_name', key)}] 知识库「{kb.get('name')}」缺少 biz_line，路由只能靠名称/别名匹配")
    print(f"映射来源：{p}（{config_source(p)}）")
    print(f"空间数量：{len(spaces)}  知识库数量：{sum(len(s.get('knowledge_bases', [])) for s in spaces.values())}")
    for w in warnings:
        print(f"  [提示] {w}")
    for pr in problems:
        print(f"  [错误] {pr}")
    if problems:
        raise SystemExit(1)
    print("校验通过。")


def cmd_list(path=None, as_json=False):
    cfg, p = load_config(path)
    if cfg is None:
        print("[错误] 找不到映射配置", file=sys.stderr)
        raise SystemExit(1)
    rows = []
    for key, sp in (cfg.get("spaces") or {}).items():
        for kb in sp.get("knowledge_bases", []):
            rows.append({
                "space_id": sp.get("space_id") or key,
                "space_name": sp.get("space_name") or sp.get("name", ""),
                "biz_line": kb.get("biz_line", ""),
                "biz_line_name": kb.get("biz_line_name", ""),
                "kb_name": kb.get("name", ""),
                "kb_id": kb.get("id", ""),
                "doc_type": kb.get("doc_type", ""),
                "expert": kb.get("expert", ""),
            })
    if as_json:
        print(json.dumps({"source": config_source(p), "path": p, "items": rows}, ensure_ascii=False, indent=2))
        return
    print(f"映射来源：{p}（{config_source(p)}）")
    for key, sp in (cfg.get("spaces") or {}).items():
        print(f"\n空间 {space_label(sp, key)}")
        print(f"  url：{sp.get('mcp_url', '') or '(未登记)'}"
              + (f"｜服务器名 {sp.get('mcp_server')}" if sp.get("mcp_server") else "｜服务器名：未识别（跑 --discover）"))
        for kb in sp.get("knowledge_bases", []):
            print(f"  - {kb.get('name')}｜id={kb.get('id') or '(空->用名称)'}"
                  f"｜业务线={kb.get('biz_line_name') or kb.get('biz_line', '')}"
                  f"｜类型={kb.get('doc_type', '')}"
                  + (f"｜专家={kb.get('expert')}" if kb.get("expert") else ""))


def main():
    ap = argparse.ArgumentParser(description="weknora 归档路由配置（内置预设 + MCP 自动识别；测试人员只需配 MCP 连接器）")
    ap.add_argument("--scope", choices=["workspace", "user"], default="user", help="本地覆盖配置写入位置（仅 --target local 时有效）")
    ap.add_argument("--target", choices=["preset", "local"], default="preset",
                    help="知识库登记的写入目标：preset=写回 skill 内置预设（默认，团队共享）/ local=本地覆盖（排障用）")
    ap.add_argument("--init-local", action="store_true", help="（排障用）把内置预设复制为本地覆盖配置")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的本地配置/知识库条目")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json", action="store_true", help="配合 --list 输出 JSON")
    ap.add_argument("--doctor", action="store_true", help="体检：映射来源 + 连接器识别结果")
    ap.add_argument("--discover", action="store_true", help="按 url 识别本机 MCP 服务器名与工具前缀")
    ap.add_argument("--write", action="store_true", help="配合 --discover：把识别结果写入本地配置")
    ap.add_argument("--config", help="指定配置文件路径")
    sub = ap.add_argument_group("知识库扩展")
    sub.add_argument("--add-kb", action="store_true", help="登记一个知识库（需 --space --name）")
    sub.add_argument("--sync-kb", action="store_true", help="用 MCP list_knowledge_bases 输出批量补齐（需 --space --from-json）")
    sub.add_argument("--diff-kb", action="store_true", help="对比 weknora 与映射，列出未登记/失效知识库（需 --space --from-json）")
    sub.add_argument("--space", help="空间：weknora 空间ID（10004/10003/10006）或空间名称")
    sub.add_argument("--name", help="知识库名称")
    sub.add_argument("--id", help="知识库 ID")
    sub.add_argument("--doc-type", help="文档类型，如 测试用例/测试总结/测试缺陷/测试需求分析")
    sub.add_argument("--biz-line", help="业务线代码，如 XD/XR/JWY/XDK/ZHJLS/AIJXC")
    sub.add_argument("--product", help="产品名称")
    sub.add_argument("--from-json", help="MCP list_knowledge_bases 输出保存的 JSON 文件")
    args = ap.parse_args()

    if args.doctor:
        cmd_doctor(args)
    elif args.discover:
        cmd_discover(args)
    elif args.validate:
        cmd_validate(args.config)
    elif args.list:
        cmd_list(args.config, args.json)
    elif args.add_kb:
        if not args.space or not args.name:
            print("[错误] --add-kb 需要 --space 与 --name", file=sys.stderr)
            raise SystemExit(2)
        cmd_add_kb(args)
    elif args.sync_kb:
        if not args.space or not args.from_json:
            print("[错误] --sync-kb 需要 --space 与 --from-json", file=sys.stderr)
            raise SystemExit(2)
        cmd_sync_kb(args)
    elif args.diff_kb:
        if not args.space or not args.from_json:
            print("[错误] --diff-kb 需要 --space 与 --from-json", file=sys.stderr)
            raise SystemExit(2)
        cmd_diff_kb(args)
    elif args.init_local:
        cmd_create(args.scope, args.force)
    else:
        print("本技能无需生成任何配置：团队映射已内置在 assets/preset_kb_mapping.json。")
        print("测试人员唯一要做的事 = 在 AI 工具里配好 MCP 连接器（url + Authorization）。")
        print()
        print("常用命令：")
        print("  python init_config.py --doctor     # 一键体检（映射 + 三个空间连接器）")
        print("  python init_config.py --discover   # 按 url 识别本机连接器与工具前缀")
        print("  python init_config.py --list       # 查看内置映射")
        print("  python init_config.py --validate   # 校验映射")
        print("  python init_config.py --add-kb  --space <空间ID> --name \"<知识库名>\" --id <ID>")
        print("  python init_config.py --sync-kb --space <空间ID> --from-json kb_list.json")
        print("  python init_config.py --diff-kb --space <空间ID> --from-json kb_list.json")
        print()
        print("（排障才需要：--init-local 复制预设为本地覆盖配置）")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
