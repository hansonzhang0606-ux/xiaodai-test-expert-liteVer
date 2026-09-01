#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XMind 评审标记解析脚本

解析评审后的 XMind 文件，提取评审标记（新增/修改/删除）
输出测试点列表和评审标记统计

支持两种测试点识别模式：
- 模式1 - 关键词模式：叶子节点 + 标题含关键词（来自 md-to-xmind-testcase skill）
- 模式2 - 叶子节点模式：所有叶子节点都是测试点（来自人工手绘流程图）

新增功能（2026-06-05）：
- 自动检测评审标记：无需重命名为 *reviewed.xmind
- 智能输出命名：有标记时生成 *_reviewed.json，无标记时生成 *_parsed.json
"""

import zipfile
import json
import os
import argparse


def detect_review_markers(xmind_path):
    """
    检测 XMind 是否包含评审标记
    
    Args:
        xmind_path: XMind 文件路径
    
    Returns:
        bool: True=包含评审标记，False=无评审标记
    """
    try:
        with zipfile.ZipFile(xmind_path, 'r') as z:
            content = json.loads(z.read('content.json'))
        
        # 递归检查所有节点的 markers
        def check_markers(node):
            markers = node.get('markers', [])
            for marker in markers:
                marker_id = marker.get('markerId', '')
                # 检查是否包含颜色标签
                if any(color in marker_id for color in ['tag-blue', 'tag-orange', 'tag-grey', 'tag-gray', 'tag-green']):
                    return True
            
            # 递归检查子节点
            children = node.get('children', {}).get('attached', [])
            for child in children:
                if check_markers(child):
                    return True
            
            return False
        
        root = content[0].get('rootTopic', content[0])
        return check_markers(root)
    
    except Exception as e:
        print(f"[WARN] 检测评审标记失败: {e}")
        return False


def extract_nodes(node, path='', results=None, parent_marker=None):
    """递归提取节点信息"""
    if results is None:
        results = []

    title = node.get('title', '')
    current_path = f"{path}/{title}" if path else title

    # 提取评审标记信息（markers 字段）
    markers = node.get('markers', [])
    marker_type = parent_marker  # 默认继承父节点标记

    # 检查 markers 判断标记类型
    for marker in markers:
        marker_id = marker.get('markerId', '')
        if 'tag-blue' in marker_id or 'blue' in marker_id:
            marker_type = '新增'
        elif 'tag-orange' in marker_id or 'orange' in marker_id:
            marker_type = '修改'
        elif 'tag-grey' in marker_id or 'grey' in marker_id or 'gray' in marker_id:
            marker_type = '删除'

    # 如果没有标记，默认为确认
    if marker_type is None:
        marker_type = '确认'

    # 判断是否为具体测试点（兼容两种模式）：
    # 模式1 - 关键词模式：叶子节点 + 标题含关键词
    # 模式2 - 叶子节点模式：所有叶子节点都是测试点（支持流程图）
    # 通用规则：带有评审标记（新增/修改）的节点也识别为测试点
    children = node.get('children', {}).get('attached', [])
    has_review_marker = marker_type in ['新增', '修改']
    is_leaf_node = len(children) == 0

    # 关键词模式判定
    keyword_patterns = (
        title.startswith(('验证', '检查', '测试', '校验', '确认', '展示', '显示', '状态', '匹配')) or
        '验证' in title or '校验' in title or '检查' in title or
        title.endswith(('验证', '校验', '测试', '校验'))
    )
    is_keyword_testpoint = is_leaf_node and keyword_patterns

    # 叶子节点模式判定（支持流程图）
    # 过滤掉纯流程标题（如"是"、"否"等简单分支标签）
    simple_branch_labels = ['是', '否', '通过', '不通过', '成功', '失败']
    is_leaf_testpoint = is_leaf_node and title.strip() not in simple_branch_labels and len(title.strip()) >= 2

    # 综合判定
    is_testpoint = is_keyword_testpoint or is_leaf_testpoint or has_review_marker

    results.append({
        'title': title,
        'path': current_path,
        'marker_type': marker_type,
        'markers': markers,
        'is_testpoint': is_testpoint,
        'level': len(current_path.split('/')) - 1
    })

    # 递归子节点（继承父节点的删除标记）
    child_parent_marker = marker_type if marker_type == '删除' else None
    for child in children:
        extract_nodes(child, current_path, results, child_parent_marker)

    return results


def parse_xmind(xmind_path):
    """解析 XMind 文件"""
    with zipfile.ZipFile(xmind_path, 'r') as z:
        content = json.loads(z.read('content.json'))

    # XMind 结构：rootTopic 包含实际内容
    root = content[0].get('rootTopic', content[0])
    nodes = extract_nodes(root)

    # 统计和筛选
    stats = {'新增': 0, '修改': 0, '删除': 0, '确认': 0}
    testpoints = []
    deleted_modules = []

    for node in nodes:
        stats[node['marker_type']] = stats.get(node['marker_type'], 0) + 1
        if node['is_testpoint'] and node['marker_type'] != '删除':
            testpoints.append(node)
        elif node['marker_type'] == '删除' and node['level'] <= 2:
            deleted_modules.append(node['title'])

    return {
        'statistics': stats,
        'total_nodes': len(nodes),
        'testpoints': testpoints,
        'deleted_modules': deleted_modules,
        'nodes': nodes,
        'xmind_path': xmind_path
    }


def main():
    parser = argparse.ArgumentParser(description='XMind 评审标记解析脚本')
    parser.add_argument('input', help='XMind 文件路径（AI 生成版或评审后版均可）')
    parser.add_argument('-o', '--output', help='输出 JSON 文件路径（默认自动命名）')

    args = parser.parse_args()

    # 自动检测评审标记
    has_review = detect_review_markers(args.input)
    
    # 解析 XMind
    result = parse_xmind(args.input)

    # 智能输出路径
    if args.output:
        output_path = args.output
    else:
        input_dir = os.path.dirname(args.input)
        base_name = os.path.basename(args.input).replace('.xmind', '')
        
        if has_review:
            # 有评审标记 → 生成 reviewed.json（评审后快照）
            output_path = os.path.join(input_dir, f"{base_name}_reviewed.json")
            print("[OK] 检测到评审标记，按评审后版本解析")
        else:
            # 无评审标记 → 生成 parsed.json（仅解析）
            output_path = os.path.join(input_dir, f"{base_name}_parsed.json")
            print("[WARN] 未检测到评审标记，按 AI 原始版本解析")

    # 保存解析结果
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 输出统计（处理 Windows GBK 编码问题）
    print("=" * 60)
    print("XMind 评审标记解析结果")
    print("=" * 60)
    print(f"总节点数: {result['total_nodes']}")
    print(f"\n评审标记统计:")
    for k, v in result['statistics'].items():
        print(f"  - {k}: {v}")
    print(f"\n有效测试点数: {len(result['testpoints'])}")

    if result['deleted_modules']:
        print(f"\n删除的模块:")
        for m in result['deleted_modules']:
            # 移除 emoji 字符，避免 Windows GBK 编码错误
            safe_m = m.encode('gbk', errors='ignore').decode('gbk')
            print(f"  - {safe_m}")

    print("=" * 60)
    print(f"解析结果已保存: {output_path}")


if __name__ == '__main__':
    main()
