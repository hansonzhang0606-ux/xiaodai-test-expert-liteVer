#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试用例规则细化脚本

将解析后的测试点细化为详细测试用例
脚本负责结构化兜底、质量校验和 Excel 前置 JSON 生成；业务级细化仍应由 AI
读取整理版 MD 后完成。脚本不得悄悄产出明显泛化的低质量用例。
"""

import json
import os
import sys
import argparse
from datetime import datetime

# 导入配置加载器
try:
    from config_loader import get_config
except ImportError as e:
    print(f"❌ config_loader 导入失败: {e}")
    print("   请确保 scripts/ 目录完整，且 config_loader.py 存在")
    sys.exit(1)


def classify_testcase(title, path):
    """根据测试点内容和路径判断用例类型

    用例类型枚举（测试平台标准）：
    - 功能测试、易用性测试、安全测试、性能测试、大数据测试、
      兼容性测试、并发测试、接口测试、可靠性测试、集成测试
    """
    combined = f"{title} {path}"

    # 安全测试（优先级最高）
    if any(kw in combined for kw in ['加密', '权限控制', '安全漏洞', '敏感数据', '脱敏', '越权']):
        return '安全测试'

    # 并发测试
    if any(kw in combined for kw in ['并发', '同时', '竞争', '锁', '分布式锁']):
        return '并发测试'

    # 性能测试
    if any(kw in combined for kw in ['性能', '吞吐', '资源占用', '响应时间']):
        return '性能测试'

    # 大数据测试
    if any(kw in combined for kw in ['大数据', '海量数据', '大量数据', '数据量', '批处理']):
        return '大数据测试'

    # 兼容性测试
    if any(kw in combined for kw in ['兼容', '浏览器', '移动端', '分辨率', '版本兼容']):
        return '兼容性测试'

    # 易用性测试（UI/交互类）- 优先级高于接口测试
    functional_ui_keywords = [
        '展示', '显示', '按钮', '文案', '字段', '状态', '点击', '查看',
        '校验', '输入', '选择', '勾选', '跳转', '页面', '弹框', '提示',
        '收起', '展开', '置灰', '高亮', 'Toast', '倒计时', '隐藏',
        'UI', '样式', '布局', '体验', '易用'
    ]
    if any(kw in title for kw in functional_ui_keywords):
        return '易用性测试'

    # 接口测试（接口调用类）
    integration_keywords = [
        '接口', '调用', '推送', '通知', '第三方', '跨系统',
        '签署', '授权', '人脸', '采集', '定时任务',
        '数据同步', '端到端', '联调', 'API'
    ]
    if any(kw in combined for kw in integration_keywords):
        return '接口测试'

    # 集成测试（多模块流程类）
    integration_flow_keywords = [
        '流程', '流转', '端到端', '跨模块', '联调', '集成'
    ]
    if any(kw in combined for kw in integration_flow_keywords):
        return '集成测试'

    # 可靠性测试（异常/容错类）
    reliability_keywords = [
        '异常', '失败', '超时', '重试', '容错', '恢复', '中断', '降级'
    ]
    if any(kw in combined for kw in reliability_keywords):
        return '可靠性测试'

    # 默认：根据路径判断来源类型
    if '需求文档' in path or '前端页面' in path:
        return '功能测试'
    elif '技术方案' in path or '接口设计' in path or '定时任务' in path:
        return '接口测试'

    return '功能测试'


def generate_case_level(title, case_type):
    """生成用例级别 - P0仅限核心主流程"""
    p0_core_keywords = [
        '完整流程', '完整流转', '主流程', '端到端', '跨系统流程',
        '正常发起完整流程', '核心流程'
    ]
    if any(kw in title for kw in p0_core_keywords):
        return 'P0'
    return 'P1'


def generate_source(path):
    """根据路径判断来源"""
    if '评审问题验证' in path:
        return '评审报告'
    elif '技术方案' in path:
        return '技术方案'
    else:
        return '需求文档'


CATEGORY_TITLES = {
    '功能流程', '正常流程', '业务规则', '边界与组合', '边界与组合场景',
    '异常场景', '回归影响', '下游影响', '关联流程', '子功能点', '子场景',
    '前置条件', '公共前置', '配置规则', '状态规则', '时间口径', '字段口径',
}

VAGUE_TESTPOINT_TITLES = {
    '单客户最多5次', '调用授信接口后开始预警', '未完成征信授权不预警',
    '预警触发', '预警停止', '预警次数', '预警频率', '最新结果识别',
    '历史结果查询', '历史结果追溯', '重复测额', '新增流水记录',
}

SIMPLE_BRANCH_LABELS = {'是', '否', '通过', '不通过', '成功', '失败'}

ACTION_KEYWORDS = [
    '验证', '校验', '检查', '确认', '触发', '发送', '生成', '新增', '更新',
    '展示', '显示', '不发送', '不触发', '停止', '记录', '返回', '置为',
    '写入', '调用', '保存', '拦截', '提示', '计算', '识别', '查询', '同步',
    '创建', '不再', '继续', '进入', '发起', '完成', '失败', '超时', '过期',
]


def validate_testpoint_leaf_quality(testpoints):
    """Excel 前复检：不把分类节点或泛化叶子节点直接生成用例。"""
    issues = []
    for index, tp in enumerate(testpoints, 1):
        title = (tp.get('title') or '').strip()
        path = tp.get('path', '')
        if not title:
            issues.append({
                'id': f'TP-{index:03d}',
                'name': title,
                'path': path,
                'reason': '叶子节点标题为空'
            })
        elif title in SIMPLE_BRANCH_LABELS:
            issues.append({
                'id': f'TP-{index:03d}',
                'name': title,
                'path': path,
                'reason': '叶子节点是简单分支标签，不是测试点'
            })
        elif title in CATEGORY_TITLES:
            issues.append({
                'id': f'TP-{index:03d}',
                'name': title,
                'path': path,
                'reason': '叶子节点是分类目录，不是具体测试点'
            })
        elif title in VAGUE_TESTPOINT_TITLES:
            issues.append({
                'id': f'TP-{index:03d}',
                'name': title,
                'path': path,
                'reason': '叶子节点是规则标题，需展开为可执行、可验证的测试点'
            })
        elif len(title) < 6 and not any(ch.isdigit() for ch in title) and not any(kw in title for kw in ACTION_KEYWORDS):
            issues.append({
                'id': f'TP-{index:03d}',
                'name': title,
                'path': path,
                'reason': '叶子节点描述过短且缺少可执行动作'
            })

    return issues


def extract_context_from_path(path):
    """从路径提取业务流程上下文（通用方法）"""
    nodes = path.split('/')
    context_nodes = []
    for node in nodes:
        # 跳过根节点和简单分支标签
        if node.startswith('【') or node in ['是', '否', '通过', '不通过', '成功', '失败']:
            continue
        if node.strip():
            context_nodes.append(node.strip())
    return context_nodes


def generate_refinement(title, path, case_type):
    """生成测试用例基础框架。

    这里是兜底模板，不替代 AI 读取整理版 MD 后做业务细化。模板必须避免
    "进入相关页面/符合预期" 这类无法执行和验证的泛化表达。
    """
    import re

    # 从路径提取前置流程
    context_nodes = extract_context_from_path(path)

    # 提取前置条件：路径中的前置节点
    pre_nodes = context_nodes[:-1] if len(context_nodes) > 1 else []
    if pre_nodes:
        # 取最近3个前置节点作为前置条件描述
        pre_context = ' → '.join(pre_nodes[-3:]) if len(pre_nodes) >= 3 else ' → '.join(pre_nodes)
        preCondition = f"测试账号已登录并具备当前功能权限，已完成前置流程：{pre_context}"
    else:
        preCondition = f"测试账号已登录并具备当前功能权限，可访问「{title}」对应功能入口"

    parent_node = context_nodes[-2] if len(context_nodes) >= 2 else '当前功能'
    input_steps = (
        f"1、打开业务系统并进入「{parent_node}」功能区域\n"
        f"2、按前置流程定位到「{title}」对应节点\n"
        f"3、执行或查看「{title}」对应操作结果"
    )
    output_results = (
        f"1、成功进入「{parent_node}」功能区域，页面无报错\n"
        f"2、当前页面或数据状态已到达「{title}」对应节点\n"
        f"3、「{title}」对应的按钮、状态、跳转或数据变化与需求规则一致"
    )

    # 状态展示类测试点细化
    if '状态' in title and '展示' in title:
        status_match = re.search(r'状态[=＝]?(\S+)', title)
        status_value = status_match.group(1) if status_match else '指定值'
        preCondition = f"测试账号已登录并具备当前功能权限，已准备状态={status_value} 的测试数据"
        input_steps = f"1、进入包含「{title}」的业务功能\n2、查看状态字段展示"
        output_results = f"1、业务功能打开成功，测试数据状态为 {status_value}\n2、状态字段展示为需求定义的 {status_value} 对应文案"

    elif '过期' in title or '有效期' in title:
        preCondition = "登录系统，数据状态为有效状态"
        input_steps = "1、进入页面\n2、查看状态字段\n3、验证有效期配置生效"
        output_results = "1、成功进入页面\n2、状态在有效期内正常显示\n3、有效期配置正确生效"

    elif '重新' in title:
        preCondition = "登录系统，数据状态为可重新操作状态"
        input_steps = f"1、进入页面\n2、点击重新操作按钮\n3、{title}"
        output_results = "1、成功进入页面\n2、按钮正确展示\n3、重新操作流程发起成功"

    elif 'toast' in title.lower() or '提示' in title:
        preCondition = "登录系统，完成相关操作流程"
        input_steps = "1、完成操作流程\n2、观察提示内容"
        output_results = "1、操作成功\n2、提示内容正确展示"

    elif '完整流程' in title or '流转' in title:
        preCondition = "登录系统，数据预置完成"
        input_steps = "1、点击发起流程按钮\n2、依次完成各步骤\n3、观察页面流转过程"
        output_results = "1、成功发起流程\n2、页面按顺序流转\n3、最终展示正确结果"

    elif '接口' in title and '失败' in title:
        preCondition = "登录系统，接口配置正确"
        input_steps = f"1、发起流程\n2、模拟接口失败\n3、{title}"
        output_results = "1、流程发起成功\n2、系统检测到失败\n3、按预期处理失败场景"

    elif '问题验证' in path:
        preCondition = "登录系统或后台管理系统"
        input_steps = f"1、进入评审问题「{title}」涉及的功能或后台配置\n2、按评审处理意见执行验证操作"
        output_results = f"1、功能或配置入口打开成功，具备验证「{title}」的测试条件\n2、系统表现与评审处理意见一致，问题项已被验证"

    return preCondition, input_steps, output_results


def _split_steps(text):
    return [line.strip() for line in (text or '').splitlines() if line.strip()]


def validate_testcase_quality(testcases):
    """检查脚本输出是否仍包含不可执行的泛化用例。"""
    import re

    generic_patterns = [
        r'进入相关页面',
        r'验证「.*」场景',
        r'验证结果符合预期',
        r'结果符合预期',
    ]

    issues = []
    for tc in testcases:
        text = '\n'.join([
            tc.get('name', ''),
            tc.get('preCondition', ''),
            tc.get('input', ''),
            tc.get('output', ''),
        ])
        matched = [p for p in generic_patterns if re.search(p, text)]
        input_steps = _split_steps(tc.get('input', ''))
        output_steps = _split_steps(tc.get('output', ''))

        if matched:
            issues.append({
                'id': tc.get('id'),
                'name': tc.get('name'),
                'reason': f"包含泛化表达：{', '.join(matched)}"
            })
        elif len(input_steps) < 2:
            issues.append({
                'id': tc.get('id'),
                'name': tc.get('name'),
                'reason': '步骤少于 2 步'
            })
        elif len(input_steps) != len(output_steps):
            issues.append({
                'id': tc.get('id'),
                'name': tc.get('name'),
                'reason': f"步骤数({len(input_steps)})与预期结果数({len(output_steps)})不一致"
            })

    return issues


def build_statistics(testcases):
    by_type = {}
    for tc in testcases:
        case_type = tc.get('caseType', '')
        by_type[case_type] = by_type.get(case_type, 0) + 1

    return {
        'total_cases': len(testcases),
        'functional': by_type.get('功能测试', 0),
        'integration': by_type.get('集成测试', 0),
        'security': by_type.get('安全测试', 0),
        'performance': by_type.get('性能测试', 0),
        'by_type': by_type,
        'by_marker': {
            '新增': len([tc for tc in testcases if tc['marker_type'] == '新增']),
            '修改': len([tc for tc in testcases if tc['marker_type'] == '修改']),
            '确认': len([tc for tc in testcases if tc['marker_type'] == '确认'])
        }
    }


def refine_testcases_data(parsed_data, user_config):
    testpoints = parsed_data.get('testpoints', [])
    leaf_issues = validate_testpoint_leaf_quality(testpoints)
    if leaf_issues:
        return [], {
            'total_cases': 0,
            'functional': 0,
            'integration': 0,
            'security': 0,
            'performance': 0,
            'by_type': {},
            'by_marker': {'新增': 0, '修改': 0, '确认': 0},
            'quality_issues': len(leaf_issues)
        }, leaf_issues

    refined_testcases = []
    for i, tp in enumerate(testpoints, 1):
        refined = refine_testpoint(tp, i, user_config)
        refined_testcases.append(refined)

    p0_cases = [tc for tc in refined_testcases if tc['caseLevel'] == 'P0']
    if len(p0_cases) > 3:
        p0_cases.sort(key=lambda tc: (
            '完整流程' in tc['name'],
            '主流程' in tc['name'],
            '端到端' in tc['name']
        ), reverse=True)
        for tc in refined_testcases:
            if tc['caseLevel'] == 'P0' and tc not in p0_cases[:3]:
                tc['caseLevel'] = 'P1'

    quality_issues = validate_testcase_quality(refined_testcases)
    statistics = build_statistics(refined_testcases)
    statistics['quality_issues'] = len(quality_issues)

    return refined_testcases, statistics, quality_issues


def refine_testcases_file(input_path, output_path, **kwargs):
    """测试用例细化主入口，由 AI 直接调用。"""
    with open(input_path, 'r', encoding='utf-8-sig') as f:
        parsed_data = json.load(f)

    config = get_config()
    defaults = config.get_defaults()
    user_config = {
        'team': kwargs.get('team') or defaults.get('team', ''),
        'product': kwargs.get('product') or defaults.get('product', ''),
        'modulePath': kwargs.get('modulePath') or defaults.get('modulePath', ''),
        'caseGroup': kwargs.get('caseGroup', ''),
        'version': kwargs.get('version', ''),
        'manager': kwargs.get('manager', ''),
        'relateReqCode': kwargs.get('relateReqCode', '')
    }

    refined_testcases, statistics, quality_issues = refine_testcases_data(parsed_data, user_config)
    if quality_issues:
        sample = '\n'.join(
            f"- {item['id']} {item['name']}: {item['reason']}"
            for item in quality_issues[:10]
        )
        raise ValueError(
            "测试用例质量门禁失败：XMind 叶子节点不合格，或脚本输出仍包含泛化/不可执行用例。\n"
            "请先修正 XMind 叶子节点，或由 AI 读取整理版 MD 进行业务细化后再生成 Excel。\n"
            f"{sample}"
        )

    output = {
        'metadata': {
            'title': '测试用例',
            'source_xmind': parsed_data.get('xmind_path', ''),
            'generated_date': datetime.now().strftime('%Y-%m-%d'),
            'generated_by': 'AI规则细化',
            'statistics': statistics,
            'user_config': user_config
        },
        'testcases': refined_testcases
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output_path


def refine_testpoint(tp, index, user_config):
    """细化单个测试点"""
    title = tp['title']
    path = tp['path']
    marker_type = tp['marker_type']

    case_type = classify_testcase(title, path)
    case_level = generate_case_level(title, case_type)
    source = generate_source(path)

    # 生成细化内容
    preCondition, input_steps, output_results = generate_refinement(title, path, case_type)

    # 生成用例编号
    prefix_map = {
        '功能测试': 'FUNC', '易用性测试': 'USAB', '安全测试': 'SEC',
        '性能测试': 'PERF', '大数据测试': 'BIGD', '兼容性测试': 'COMP',
        '并发测试': 'CONC', '接口测试': 'API', '可靠性测试': 'RELI',
        '集成测试': 'INTG'
    }
    case_id = f"TC-{prefix_map.get(case_type, 'FUNC')}-{str(index).zfill(3)}"

    return {
        'id': case_id,
        'team': user_config.get('team', ''),
        'caseGroup': user_config.get('caseGroup', ''),
        'name': title,
        'preCondition': preCondition,
        'input': input_steps,
        'output': output_results,
        'product': user_config.get('product', ''),
        'modulePath': user_config.get('modulePath', ''),
        'version': user_config.get('version', ''),
        'caseType': case_type,
        'source': source,
        'caseLevel': case_level,
        'manager': user_config.get('manager', ''),
        'autoState': '否',
        'relateReqCode': user_config.get('relateReqCode', ''),
        'workload': '',
        'remarks': f"评审标记：{marker_type}",
        'separator': '\n',
        'marker_type': marker_type,
        'original_path': path
    }


def main():
    parser = argparse.ArgumentParser(description='测试用例智能细化脚本')
    parser.add_argument('input', help='解析后的测试点 JSON 文件路径')
    parser.add_argument('-o', '--output', help='输出测试用例 JSON 文件路径（默认与输入同目录）')
    parser.add_argument('--caseGroup', default='', help='功能路径（用例分组）')
    parser.add_argument('--version', default='', help='适用版本')
    parser.add_argument('--manager', default='', help='责任人')
    parser.add_argument('--relateReqCode', default='', help='关联用户故事')
    parser.add_argument('--team', default='', help='项目组')
    parser.add_argument('--product', default='', help='产品')
    parser.add_argument('--modulePath', default='', help='模块路径')

    args = parser.parse_args()

    # 加载解析后的测试点
    with open(args.input, 'r', encoding='utf-8-sig') as f:
        parsed_data = json.load(f)

    testpoints = parsed_data.get('testpoints', [])

    # 获取配置
    config = get_config()
    defaults = config.get_defaults()

    # 用户配置（优先使用参数，其次使用配置文件）
    user_config = {
        'team': args.team or defaults.get('team', ''),
        'product': args.product or defaults.get('product', ''),
        'modulePath': args.modulePath or defaults.get('modulePath', ''),
        'caseGroup': args.caseGroup,
        'version': args.version,
        'manager': args.manager,
        'relateReqCode': args.relateReqCode
    }

    refined_testcases, statistics, quality_issues = refine_testcases_data(parsed_data, user_config)
    if quality_issues:
        print("=" * 60)
        print("测试用例质量门禁失败")
        print("=" * 60)
        for item in quality_issues[:10]:
            print(f"- {item['id']} {item['name']}: {item['reason']}")
        print("请先修正 XMind 叶子节点，或由 AI 读取整理版 MD 进行业务细化后再生成 Excel。")
        return

    # 输出结果
    output = {
        'metadata': {
            'title': '测试用例',
            'source_xmind': parsed_data.get('xmind_path', ''),
            'generated_date': datetime.now().strftime('%Y-%m-%d'),
            'generated_by': 'AI智能细化',
            'statistics': statistics,
            'user_config': user_config
        },
        'testcases': refined_testcases
    }

    # 输出路径
    if args.output:
        output_path = args.output
    else:
        input_dir = os.path.dirname(args.input)
        base_name = os.path.basename(args.input).replace('_parsed.json', '')
        output_path = os.path.join(input_dir, f"{base_name}_测试用例.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("AI 智能细化完成")
    print("=" * 60)
    print(f"总用例数: {statistics['total_cases']}")
    print(f"\n按类型统计:")
    print(f"  - 功能测试: {statistics['functional']}")
    print(f"  - 集成测试: {statistics['integration']}")
    print(f"  - 安全测试: {statistics['security']}")
    print(f"  - 性能测试: {statistics['performance']}")
    print(f"\n按评审标记统计:")
    print(f"  - 新增: {statistics['by_marker']['新增']}")
    print(f"  - 修改: {statistics['by_marker']['修改']}")
    print(f"  - 确认: {statistics['by_marker']['确认']}")
    print("=" * 60)
    print(f"细化结果已保存: {output_path}")


if __name__ == '__main__':
    main()
