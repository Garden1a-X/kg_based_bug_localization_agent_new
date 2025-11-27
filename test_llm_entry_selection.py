#!/usr/bin/env python3
"""
测试 LLM 入口选择功能
直接调用 LLM 分析日志，查看原始输出和结果
"""
import sys
import yaml
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from llm.llm_client import LLMClient
from config.entry_points import get_candidate_entries_for_subgraph


def load_user_context(context_file: str) -> dict:
    """加载用户上下文文件"""
    with open(context_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_log(log_file: str) -> str:
    """加载日志文件"""
    with open(log_file, 'r', encoding='utf-8') as f:
        return f.read()


def test_llm_entry_selection():
    """测试 LLM 入口选择"""

    print("=" * 80)
    print("LLM 入口选择测试")
    print("=" * 80)

    # 配置
    log_file = "/data/xuao/code_kg_search/kg_based_bug_localization_agent/error.log"
    context_file = "contexts/rk3288.yaml"

    # 读取日志
    print(f"\n📝 读取日志: {log_file}")
    log_text = load_log(log_file)
    print(f"日志内容 ({len(log_text)} 字符):")
    print("-" * 80)
    print(log_text[:500] if len(log_text) > 500 else log_text)
    if len(log_text) > 500:
        print(f"... (省略 {len(log_text) - 500} 字符)")
    print("-" * 80)

    # 读取用户上下文
    print(f"\n📌 读取用户上下文: {context_file}")
    user_context = load_user_context(context_file)
    print("用户上下文内容:")
    print(yaml.dump(user_context, allow_unicode=True, default_flow_style=False))
    print("-" * 80)

    # 获取候选入口
    print("\n🎯 获取候选入口 (mmc 子图)")
    entry_config = get_candidate_entries_for_subgraph('mmc')
    candidate_entries = entry_config.get('ko_init', []) + entry_config.get('sdk_api', [])
    print(f"候选入口数量: {len(candidate_entries)}")
    print(f"候选入口列表: {candidate_entries[:10]}...")  # 只显示前10个
    print("-" * 80)

    # 创建 LLM 客户端
    print("\n🤖 创建 LLM 客户端")
    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }
    llm_client = LLMClient(**llm_config)

    if not llm_client.is_available():
        print("❌ LLM 客户端不可用")
        return

    print("✓ LLM 客户端已就绪")
    print("-" * 80)

    # 测试1: 无用户上下文
    print("\n" + "=" * 80)
    print("测试 1: 无用户上下文")
    print("=" * 80)
    result1 = llm_client.analyze_log(
        log_text=log_text,
        candidate_entries=candidate_entries,
        user_context=None
    )

    if result1:
        print("\n✅ LLM 返回结果:")
        print(yaml.dump(result1, allow_unicode=True, default_flow_style=False, indent=2))

        print("\n关键信息:")
        print(f"  起点函数: {result1.get('start_entity')}")
        print(f"  置信度: {result1.get('start_confidence')}")
        print(f"  需要更多信息: {result1.get('need_more_info')}")

        if result1.get('reasoning'):
            print(f"\n推理过程:")
            for i, step in enumerate(result1['reasoning'], 1):
                print(f"  {i}. {step}")

        if result1.get('suggestions'):
            print(f"\n建议:")
            for suggestion in result1['suggestions']:
                print(f"  • {suggestion}")
    else:
        print("❌ LLM 未返回结果")

    # 测试2: 有用户上下文
    print("\n" + "=" * 80)
    print("测试 2: 提供用户上下文")
    print("=" * 80)
    result2 = llm_client.analyze_log(
        log_text=log_text,
        candidate_entries=candidate_entries,
        user_context=user_context
    )

    if result2:
        print("\n✅ LLM 返回结果:")
        print(yaml.dump(result2, allow_unicode=True, default_flow_style=False, indent=2))

        print("\n关键信息:")
        print(f"  起点函数: {result2.get('start_entity')}")
        print(f"  置信度: {result2.get('start_confidence')}")
        print(f"  需要更多信息: {result2.get('need_more_info')}")

        if result2.get('reasoning'):
            print(f"\n推理过程:")
            for i, step in enumerate(result2['reasoning'], 1):
                print(f"  {i}. {step}")

        if result2.get('suggestions'):
            print(f"\n建议:")
            for suggestion in result2['suggestions']:
                print(f"  • {suggestion}")
    else:
        print("❌ LLM 未返回结果")

    # 对比
    print("\n" + "=" * 80)
    print("对比分析")
    print("=" * 80)

    if result1 and result2:
        print(f"无上下文 -> 有上下文:")
        print(f"  起点函数: {result1.get('start_entity')} -> {result2.get('start_entity')}")
        print(f"  置信度: {result1.get('start_confidence')} -> {result2.get('start_confidence')}")
        print(f"  需要更多信息: {result1.get('need_more_info')} -> {result2.get('need_more_info')}")

        conf1 = result1.get('start_confidence', 0)
        conf2 = result2.get('start_confidence', 0)
        delta = conf2 - conf1

        print(f"\n置信度变化: {delta:+.2f}")
        if conf2 >= 0.6:
            print("✅ 提供用户上下文后，置信度达到阈值 (>= 0.6)")
        else:
            print("⚠️  即使提供了用户上下文，置信度仍然 < 0.6")
            print("   可能原因：")
            print("   - 日志信息过于简单")
            print("   - 用户上下文与日志内容不匹配")
            print("   - LLM 过于保守")


def test_with_custom_log_and_context():
    """使用自定义日志和上下文测试"""
    import argparse

    parser = argparse.ArgumentParser(description='测试 LLM 入口选择')
    parser.add_argument('--log-file', required=True, help='日志文件路径')
    parser.add_argument('--user-context', help='用户上下文文件路径（可选）')
    parser.add_argument('--subgraph', default='mmc', help='子图名称（默认：mmc）')

    args = parser.parse_args()

    print("=" * 80)
    print("LLM 入口选择测试（自定义参数）")
    print("=" * 80)

    # 读取日志
    print(f"\n📝 读取日志: {args.log_file}")
    log_text = load_log(args.log_file)
    print(f"日志内容 ({len(log_text)} 字符):")
    print("-" * 80)
    print(log_text[:500] if len(log_text) > 500 else log_text)
    if len(log_text) > 500:
        print(f"... (省略 {len(log_text) - 500} 字符)")
    print("-" * 80)

    # 读取用户上下文（如果提供）
    user_context = None
    if args.user_context:
        print(f"\n📌 读取用户上下文: {args.user_context}")
        user_context = load_user_context(args.user_context)
        print("用户上下文内容:")
        print(yaml.dump(user_context, allow_unicode=True, default_flow_style=False))
        print("-" * 80)

    # 获取候选入口
    print(f"\n🎯 获取候选入口 ({args.subgraph} 子图)")
    entry_config = get_candidate_entries_for_subgraph(args.subgraph)
    candidate_entries = entry_config.get('ko_init', []) + entry_config.get('sdk_api', [])
    print(f"候选入口数量: {len(candidate_entries)}")
    print(f"候选入口列表: {candidate_entries}")
    print("-" * 80)

    # 创建 LLM 客户端
    print("\n🤖 创建 LLM 客户端")
    llm_config = {
        'backend': 'openai',
        'model': 'gpt-4o-mini',
        'base_url': 'http://10.12.208.86:8502',
        'api_key': ''
    }
    llm_client = LLMClient(**llm_config)

    if not llm_client.is_available():
        print("❌ LLM 客户端不可用")
        return

    print("✓ LLM 客户端已就绪")
    print("-" * 80)

    # 调用 LLM
    print("\n🔍 调用 LLM 分析...")
    result = llm_client.analyze_log(
        log_text=log_text,
        candidate_entries=candidate_entries,
        user_context=user_context
    )

    if result:
        print("\n✅ LLM 返回结果:")
        print(yaml.dump(result, allow_unicode=True, default_flow_style=False, indent=2))

        print("\n" + "=" * 80)
        print("关键信息摘要")
        print("=" * 80)
        print(f"  起点函数: {result.get('start_entity')}")
        print(f"  终点函数: {result.get('end_entity')}")
        print(f"  置信度: {result.get('start_confidence')}")
        print(f"  需要更多信息: {result.get('need_more_info')}")

        if result.get('reasoning'):
            print(f"\n推理过程:")
            for i, step in enumerate(result['reasoning'], 1):
                print(f"  {i}. {step}")

        if result.get('suggestions'):
            print(f"\n建议:")
            for suggestion in result['suggestions']:
                print(f"  • {suggestion}")

        # 判断结果
        print("\n" + "=" * 80)
        print("结果判断")
        print("=" * 80)

        confidence = result.get('start_confidence', 0)
        if confidence >= 0.6:
            print(f"✅ 置信度达标 ({confidence:.2f} >= 0.6)")
            print(f"   将使用入口: {result.get('start_entity')}")
        else:
            print(f"⚠️  置信度不足 ({confidence:.2f} < 0.6)")
            print(f"   将启用降级模式")
            if result.get('need_more_info'):
                print(f"   建议提供更多信息")
    else:
        print("❌ LLM 未返回结果")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # 使用命令行参数模式
        test_with_custom_log_and_context()
    else:
        # 使用默认测试
        test_llm_entry_selection()
