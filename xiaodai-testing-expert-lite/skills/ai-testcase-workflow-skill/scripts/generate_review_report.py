#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
需求评审报告生成脚本
将 AI 评审生成的 JSON 数据转换为结构化的 Markdown 评审报告

特性：
- 自动统计 severity 数量，不依赖 AI 手动填写的 summary
- 自动处理 categories 嵌套结构
- 自动生成缺失的 title 字段
- 兼容处理 document_status 字段类型

支持 SKILL.md 定义的 8 个必选状态标记：
1. 知识库读取状态
2. 关联文档读取状态
3. 图片解析状态
4. 附件解析状态
5. 需求-技术方案对比分析
6. 历史对比分析
7. 技术风险提示
8. 问题处理状态标记
"""

import json
import argparse
import os
from datetime import datetime


def normalize_categories(json_data):
    """标准化 categories 结构，处理嵌套情况"""
    # 如果顶层已有 categories 数组，直接使用
    if 'categories' in json_data and isinstance(json_data['categories'], list):
        return json_data['categories']
    
    # 处理嵌套在 requirement_review/technical_review 下的情况
    all_categories = []
    
    # 从 requirement_review.categories 提取
    req_review = json_data.get('requirement_review', {})
    if isinstance(req_review, dict) and 'categories' in req_review:
        req_cats = req_review.get('categories', [])
        if isinstance(req_cats, list):
            all_categories.extend(req_cats)
    
    # 从 technical_review.categories 提取
    tech_review = json_data.get('technical_review', {})
    if isinstance(tech_review, dict) and 'categories' in tech_review:
        tech_cats = tech_review.get('categories', [])
        if isinstance(tech_cats, list):
            all_categories.extend(tech_cats)
    
    return all_categories


def normalize_document_status(json_data):
    """标准化 document_status 结构"""
    doc_status = json_data.get('document_status', {})
    
    # 处理 related_documents 类型（可能是字符串）
    related_docs = doc_status.get('related_documents', [])
    if isinstance(related_docs, str):
        # 字符串转换为数组
        doc_status['related_documents'] = [
            {'type': '文档', 'filename': '未知', 'status': related_docs, 'remark': ''}
        ]
    
    # 处理 images 类型（可能是对象）
    images = doc_status.get('images', [])
    if isinstance(images, dict):
        # 对象转换为数组
        doc_status['images'] = [
            {'name': '图片', 'location': '', 'status': images.get('status', '未知'), 
             'type': images.get('type', ''), 'info': images.get('info', ''), 'reason': images.get('reason', '')}
        ]
    
    # 处理 attachments 类型
    attachments = doc_status.get('attachments', [])
    if isinstance(attachments, str):
        doc_status['attachments'] = []
    
    return doc_status


def count_severity(categories):
    """自动统计各 severity 数量"""
    critical_count = 0
    major_count = 0
    minor_count = 0
    
    for category in categories:
        items = category.get('items', [])
        for item in items:
            severity = item.get('severity', '')
            if severity == 'critical':
                critical_count += 1
            elif severity == 'major':
                major_count += 1
            elif severity == 'minor':
                minor_count += 1
    
    return {
        'total_issues': critical_count + major_count + minor_count,
        'critical': critical_count,
        'major': major_count,
        'minor': minor_count
    }


def get_item_title(item):
    """自动生成问题标题（从 description 截取）"""
    title = item.get('title', '')
    if title:
        return title
    
    desc = item.get('description', '')
    if len(desc) > 30:
        return desc[:30] + "..."
    return desc if desc else "未命名问题"


def generate_review_report(json_data, output_path):
    """将评审 JSON 数据转换为 Markdown 格式报告"""
    lines = []
    
    # 标准化数据结构
    categories = normalize_categories(json_data)
    doc_status = normalize_document_status(json_data)
    summary = count_severity(categories)  # 自动统计
    
    # 文档头部
    lines.append("# 📋 需求评审报告\n")
    lines.append(f"> 文档名称：{json_data.get('doc_title', '未知')}")
    lines.append(f"> 评审日期：{json_data.get('review_date', datetime.now().strftime('%Y-%m-%d'))}")
    lines.append(f"> 评审人：{json_data.get('reviewer', 'AI 评审助手')}\n")
    lines.append("---\n")

    # 1. 知识库读取状态（必选）
    kb_status = doc_status.get('knowledge_base', {})
    lines.append("## 📚 知识库读取状态\n")
    if kb_status.get('exists'):
        history_items = kb_status.get('history_items', [])
        if history_items:
            lines.append("| 知识库内容 | 文档名称 | 读取状态 | 提取内容 |")
            lines.append("|-----------|---------|---------|---------|")
            for item in history_items:
                lines.append(f"| {item.get('type', '')} | {item.get('name', '')} | {item.get('status', '')} | {item.get('content', '')} |")
        else:
            lines.append("| 状态 | 说明 |")
            lines.append("|------|------|")
            lines.append(f"| ✅ 知识库已初始化 | {kb_status.get('message', '暂无历史文档')} |")
    else:
        lines.append("| 状态 | 说明 |")
        lines.append("|------|------|")
        lines.append("| ❌ 知识库未初始化 | 项目根目录未找到 .skill/knowledge-base |")
    lines.append("")
    lines.append("---\n")

    # 2. 关联文档读取状态（必选）
    related_docs = doc_status.get('related_documents', [])
    lines.append("## 📄 关联文档读取状态\n")
    if related_docs:
        lines.append("| 文档类型 | 文件名 | 读取状态 | 备注 |")
        lines.append("|---------|--------|---------|------|")
        for doc in related_docs:
            lines.append(f"| {doc.get('type', '')} | {doc.get('filename', '')} | {doc.get('status', '')} | {doc.get('remark', '')} |")
    else:
        lines.append("| 状态 | 说明 |")
        lines.append("|------|------|")
        lines.append("| ⚠️ 未提供 | JSON 中缺少 related_documents 字段 |")
    lines.append("")
    lines.append("---\n")

    # 3. 图片解析状态（必选）
    images = doc_status.get('images', [])
    lines.append("## 🖼️ 图片解析状态\n")
    if images:
        unparsed_count = sum(1 for img in images if '❌' in img.get('status', '') or '未解析' in img.get('status', ''))
        if unparsed_count > 0:
            lines.append("| 图片名称 | 引用位置 | 解析状态 | 内容类型 | 未解析原因/关键信息 |")
            lines.append("|---------|---------|---------|---------|-------------------|")
            for img in images:
                status = img.get('status', '')
                info = img.get('info', '')
                reason = img.get('reason', '')
                display_info = reason if ('❌' in status or '未解析' in status) else info
                lines.append(f"| {img.get('name', '')} | {img.get('location', '')} | {status} | {img.get('type', '')} | {display_info} |")
            lines.append(f"\n> ⚠️ **影响提示**：{unparsed_count} 张图片未解析，流程图、界面原型等关键信息可能遗漏。建议：切换到支持图片的模型重新评审，或手动补充图片内容描述。")
        else:
            lines.append("| 图片名称 | 引用位置 | 解析状态 | 内容类型 | 关键信息 |")
            lines.append("|---------|---------|---------|---------|---------|")
            for img in images:
                lines.append(f"| {img.get('name', '')} | {img.get('location', '')} | {img.get('status', '')} | {img.get('type', '')} | {img.get('info', '')} |")
    else:
        lines.append("| 状态 | 说明 |")
        lines.append("|------|------|")
        lines.append("| ⚠️ 无图片 | 文档中未引用图片 |")
    lines.append("")
    lines.append("---\n")

    # 4. 附件解析状态（如有附件）
    attachments = doc_status.get('attachments', [])
    if attachments:
        lines.append("## 📎 附件解析状态\n")
        lines.append("| 附件名称 | 引用位置 | 解析状态 | 附件类型 | 提取内容 |")
        lines.append("|---------|---------|---------|---------|---------|")
        for att in attachments:
            lines.append(f"| {att.get('name', '')} | {att.get('location', '')} | {att.get('status', '')} | {att.get('type', '')} | {att.get('content', '')} |")
        lines.append("")
        lines.append("---\n")

    # 5. 需求-技术方案对比分析
    comparison = json_data.get('comparison', {})
    diff_items = comparison.get('diff_items', [])
    if diff_items:
        lines.append("## 🔍 需求-技术方案对比分析\n")
        lines.append("> 基于需求文档和技术方案对比，识别不一致项：\n")
        lines.append("| 序号 | 差异类型 | 需求文档描述 | 技术方案描述 | 影响 |")
        lines.append("|------|----------|-------------|-------------|------|")
        for idx, diff in enumerate(diff_items, 1):
            lines.append(f"| {idx} | {diff.get('type', '')} | {diff.get('req_desc', '')} | {diff.get('tech_desc', '')} | {diff.get('impact', '')} |")
        lines.append("")
        lines.append("---\n")

    # 6. 历史对比分析
    historical = json_data.get('historical_comparison', {})
    hist_items = historical.get('items', [])
    if hist_items:
        lines.append("## 📋 历史对比分析\n")
        lines.append("基于知识库历史评审报告对比：\n")
        lines.append("| 对比维度 | 历史评审问题 | 本次文档是否解决 | 状态 |")
        lines.append("|---------|-------------|----------------|------|")
        for item in hist_items:
            lines.append(f"| {item.get('dimension', '')} | {item.get('history_issue', '')} | {item.get('resolved', '')} | {item.get('status', '')} |")
        lines.append("")
        lines.append("---\n")

    # 7. 技术风险提示（必选）
    tech_risks = json_data.get('tech_risks', [])
    if tech_risks:
        lines.append("## ⚠️ 技术风险提示\n")
        lines.append("| 风险项 | 风险等级 | 建议措施 |")
        lines.append("|--------|---------|---------|")
        for risk in tech_risks:
            lines.append(f"| {risk.get('risk', '')} | {risk.get('level', '')} | {risk.get('suggestion', '')} |")
        lines.append("")
        lines.append("---\n")

    # 8. 评审概览 - 自动统计
    lines.append("## 📊 评审概览\n")
    lines.append("| 指标 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 问题总数 | {summary['total_issues']} |")
    lines.append(f"| 🔴 严重 | {summary['critical']} |")
    lines.append(f"| 🟡 重要 | {summary['major']} |")
    lines.append(f"| 🟢 一般 | {summary['minor']} |\n")
    lines.append("---\n")

    # 按严重程度分组输出问题
    severity_order = ['critical', 'major', 'minor']
    severity_titles = {
        'critical': '🔴 严重问题',
        'major': '🟡 重要问题',
        'minor': '🟢 一般问题'
    }

    for severity in severity_order:
        items_by_category = []
        for category in categories:
            cat_items = [item for item in category.get('items', [])
                        if item.get('severity') == severity]
            if cat_items:
                items_by_category.append({
                    'category': category.get('name'),
                    'items': cat_items
                })

        if items_by_category:
            lines.append(f"## {severity_titles.get(severity, '问题')}\n")
            item_index = 1
            for cat_data in items_by_category:
                for item in cat_data['items']:
                    title = get_item_title(item)  # 自动生成标题
                    lines.append(f"### {item_index}. [{cat_data['category']}] {title}\n")
                    lines.append(f"- **位置**：{item.get('location', '未知')}")
                    lines.append(f"- **描述**：{item.get('description', '')}")
                    if item.get('suggestion'):
                        lines.append(f"- **建议**：{item['suggestion']}")
                    lines.append("")
                    status = item.get('status', '待讨论')
                    lines.append(f"> 💡 **处理状态**：{status}\n")
                    lines.append("")
                    item_index += 1
            lines.append("---\n")

    # 总结建议
    lines.append("## 💡 总结建议\n")
    lines.append(generate_summary_suggestions(categories))
    lines.append("")
    lines.append("---\n")
    lines.append("*本报告由 AI 评审助手自动生成，需人工审核确认*\n")

    # 写入文件
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    # 输出统计信息
    print(f"✅ 评审报告已生成：{output_path}")
    print(f"   问题总数：{summary['total_issues']}")
    print(f"   严重：{summary['critical']}, 重要：{summary['major']}, 一般：{summary['minor']}")
    
    # 验证输出完整性
    print("\n📋 8 个必选状态标记验证：")
    print(f"   1. 知识库读取状态：{'✅' if kb_status else '⚠️ 缺少'}")
    print(f"   2. 关联文档读取状态：{'✅' if related_docs else '⚠️ 缺少'}")
    print(f"   3. 图片解析状态：{'✅' if images else '⚠️ 无图片'}")
    print(f"   4. 附件解析状态：{'✅' if attachments else '️ 无附件'}")
    print(f"   5. 需求-技术方案对比：{'✅' if diff_items else '⚠️ 无技术方案'}")
    print(f"   6. 历史对比分析：{'✅' if hist_items else '⚠️ 无历史记录'}")
    print(f"   7. 技术风险提示：{'✅' if tech_risks else '⚠️ 缺少'}")
    print(f"   8. 问题处理状态标记：✅ 每个问题已包含")


def generate_summary_suggestions(categories):
    """生成总结建议"""
    suggestions = []
    
    critical_items = []
    major_items = []
    minor_items = []

    for category in categories:
        for item in category.get('items', []):
            severity = item.get('severity', '')
            suggestion = item.get('suggestion', item.get('description', ''))
            if severity == 'critical':
                critical_items.append(suggestion)
            elif severity == 'major':
                major_items.append(suggestion)
            else:
                minor_items.append(suggestion)

    if critical_items:
        suggestions.append("1. **高优先级**：" + "；".join(critical_items[:3]))
    if major_items:
        suggestions.append("2. **中优先级**：" + "；".join(major_items[:3]))
    if minor_items:
        suggestions.append("3. **低优先级**：" + "；".join(minor_items[:3]))

    if not suggestions:
        suggestions.append("无特别建议，需求文档质量较好")

    return "\n".join(suggestions)


def main():
    parser = argparse.ArgumentParser(description='生成需求评审报告')
    parser.add_argument('--input', '-i', required=True, help='评审 JSON 文件路径')
    parser.add_argument('--output', '-o', required=True, help='输出报告文件路径')

    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    generate_review_report(json_data, args.output)


if __name__ == '__main__':
    main()