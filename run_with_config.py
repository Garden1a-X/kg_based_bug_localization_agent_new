#!/usr/bin/env python3
"""
基于配置文件的Bug定位分析入口脚本

使用方式：
1. 复制 config/bug_localization_config.example.yaml 为 config/bug_localization_config.yaml
2. 根据需要修改配置
3. 运行脚本：
   python run_with_config.py
   python run_with_config.py --config my_config.yaml
   python run_with_config.py --scenario mmc_manual
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from coordinator.master_coordinator import MasterCoordinator
from utils.logger import setup_logger

try:
    import yaml
except ImportError:
    print("错误: 需要安装 PyYAML")
    print("请运行: pip install pyyaml")
    sys.exit(1)


def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def load_log_from_file(log_file: str) -> str:
    """从文件加载日志"""
    if not os.path.exists(log_file):
        raise FileNotFoundError(f"日志文件不存在: {log_file}")

    with open(log_file, 'r', encoding='utf-8') as f:
        return f.read()


def create_coordinator(config: Dict[str, Any]) -> MasterCoordinator:
    """根据配置创建协调器"""
    data_dir = config['data_dir']
    if not os.path.exists(data_dir):
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    # LLM配置
    llm_config = None
    llm_cfg = config.get('llm', {})
    subgraph_enabled = config.get('subgraph_selection', {}).get('enabled', False)

    if llm_cfg.get('detection', {}).get('enabled') or \
       llm_cfg.get('log_analysis', {}).get('enabled') or \
       subgraph_enabled:
        llm_config = {
            'backend': 'openai',
            'model': llm_cfg.get('model', 'gpt-4o-mini'),
            'base_url': llm_cfg.get('base_url', 'http://10.12.208.86:8502'),
            'api_key': llm_cfg.get('api_key', '')
        }

    # 创建协调器
    coordinator = MasterCoordinator(
        data_dir=data_dir,
        llm_client=None,
        enable_llm_detection=llm_cfg.get('detection', {}).get('enabled', False),
        enable_llm_log_analysis=llm_cfg.get('log_analysis', {}).get('enabled', False),
        enable_subgraph_selection=subgraph_enabled,
        llm_config=llm_config
    )

    return coordinator


def save_result(result: dict, config: Dict[str, Any]):
    """保存结果到JSON文件"""
    output_cfg = config.get('output', {})
    output_dir = output_cfg.get('directory', 'output')
    output_filename = output_cfg.get('filename', 'result.json')

    output_file = Path(output_dir) / output_filename
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 结果已保存到: {output_file}")


def print_config_summary(config: Dict[str, Any], scenario: Optional[Dict[str, Any]] = None):
    """打印配置摘要"""
    print("=" * 80)
    print("配置信息")
    print("=" * 80)
    print(f"📋 数据目录: {config['data_dir']}")
    print(f"🔢 Top-K: {config.get('top_k', 5)}")

    subgraph_cfg = config.get('subgraph_selection', {})
    print(f"🎯 子图选择: {'✓ 启用' if subgraph_cfg.get('enabled') else '✗ 禁用'}")
    if subgraph_cfg.get('manual_subgraph'):
        print(f"📦 指定子图: {subgraph_cfg['manual_subgraph']}")

    llm_cfg = config.get('llm', {})
    if llm_cfg.get('detection', {}).get('enabled'):
        print(f"🤖 LLM间接调用检测: ✓ 启用")
    if llm_cfg.get('log_analysis', {}).get('enabled'):
        print(f"🤖 LLM日志分析: ✓ 启用")

    if scenario:
        print(f"\n📌 场景: {scenario.get('description', 'N/A')}")
        print(f"🎯 模式: {scenario.get('mode', 'auto')}")
        if scenario.get('mode') == 'manual':
            print(f"   起点: {scenario.get('start_func')}")
            print(f"   终点: {scenario.get('end_func')}")
            if scenario.get('intermediate_funcs'):
                print(f"   中间节点: {', '.join(scenario['intermediate_funcs'])}")

    print("=" * 80)
    print()


def print_summary(result: dict):
    """打印结果摘要"""
    print("\n" + "=" * 80)
    print("分析结果摘要")
    print("=" * 80)

    if not result.get('success'):
        print("❌ 分析失败")
        if 'error' in result:
            print(f"   错误: {result['error']}")
        return

    print("✅ 分析成功")

    # 显示路径信息
    if 'paths' in result:
        # Top-K模式
        path_count = result.get('path_count', 0)
        print(f"   找到 {path_count} 条路径")

        if result['paths']:
            best_path = result['paths'][0]
            print(f"   最佳路径长度: {best_path['length']}")
            print(f"   间接调用数: {best_path.get('indirect_count', 0)}")
            print(f"   得分: {best_path.get('score', 0):.2f}")

            # 显示调用链（简化）
            call_chain = best_path['path']
            if len(call_chain) <= 10:
                print(f"   调用链: {' → '.join(call_chain)}")
            else:
                print(f"   调用链: {' → '.join(call_chain[:5])} → ... → {' → '.join(call_chain[-3:])}")
    elif 'chain' in result:
        # 单路径模式
        chain = result['chain']
        print(f"   路径长度: {chain.get('length', 0)}")
        print(f"   总断点数: {chain.get('stats', {}).get('total_breaks', 0)}")

        call_chain = chain.get('path', [])
        if len(call_chain) <= 10:
            print(f"   调用链: {' → '.join(call_chain)}")
        else:
            print(f"   调用链: {' → '.join(call_chain[:5])} → ... → {' → '.join(call_chain[-3:])}")

    print("=" * 80)


def run_with_scenario(config: Dict[str, Any], scenario_name: str):
    """使用预设场景运行"""
    scenarios = config.get('scenarios', {})
    if scenario_name not in scenarios:
        raise ValueError(f"场景不存在: {scenario_name}\n可用场景: {', '.join(scenarios.keys())}")

    scenario = scenarios[scenario_name]

    # 打印配置摘要
    print_config_summary(config, scenario)

    # 判断运行模式
    mode = scenario.get('mode', 'auto')
    is_manual_mode = mode == 'manual'

    # 加载日志（手动模式下可选）
    log_file = scenario.get('log_file')
    log_text = ""

    if log_file:
        log_text = load_log_from_file(log_file)
        print(f"📝 日志来源: {log_file}\n")
    elif not is_manual_mode:
        # 自动模式必须提供日志
        raise ValueError(f"场景 {scenario_name} 是自动推断模式，必须指定 log_file")
    else:
        # 手动模式，日志可选
        print(f"📝 日志来源: 无（手动模式）\n")

    # 加载用户上下文（可选）
    user_context = None
    context_file = scenario.get('user_context_file')
    if context_file:
        if not os.path.exists(context_file):
            raise FileNotFoundError(f"用户上下文文件不存在: {context_file}")
        with open(context_file, 'r', encoding='utf-8') as f:
            user_context = yaml.safe_load(f)
        print(f"🔍 用户上下文: {context_file}\n")

    # 创建协调器
    coordinator = create_coordinator(config)

    try:
        # 根据模式执行
        k = config.get('top_k', 5)
        manual_subgraph = config.get('subgraph_selection', {}).get('manual_subgraph')

        if is_manual_mode:
            # 手动指定模式
            result = coordinator.process_top_k_with_specific_functions(
                log_text,
                start_func=scenario['start_func'],
                end_func=scenario['end_func'],
                intermediate_funcs=scenario.get('intermediate_funcs'),
                k=k,
                subgraph_override=manual_subgraph,
                user_context=user_context
            )
        else:
            # 自动推断模式
            result = coordinator.process_top_k(
                log_text,
                k=k,
                subgraph_override=manual_subgraph,
                user_context=user_context
            )

        # 保存结果
        save_result(result, config)

        # 打印摘要
        print_summary(result)

        return 0 if result.get('success') else 1

    finally:
        coordinator.close()


def run_with_log_input(config: Dict[str, Any], log_text: str):
    """使用直接输入的日志运行"""
    # 打印配置摘要
    print_config_summary(config)

    print(f"📝 日志来源: 命令行输入\n")

    # 创建协调器
    coordinator = create_coordinator(config)

    try:
        k = config.get('top_k', 5)
        manual_subgraph = config.get('subgraph_selection', {}).get('manual_subgraph')

        # 自动推断模式
        result = coordinator.process_top_k(
            log_text,
            k=k,
            subgraph_override=manual_subgraph
        )

        # 保存结果
        save_result(result, config)

        # 打印摘要
        print_summary(result)

        return 0 if result.get('success') else 1

    finally:
        coordinator.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='基于配置文件的Bug定位分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--config',
        default='config/bug_localization_config.yaml',
        help='配置文件路径（默认：config/bug_localization_config.yaml）'
    )
    parser.add_argument(
        '--scenario',
        help='使用预设场景（如：mmc_auto, mmc_manual, usb_auto等）'
    )
    parser.add_argument(
        '--log',
        help='直接输入日志文本（不使用场景）'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细日志'
    )

    args = parser.parse_args()

    # 配置日志
    setup_logger()

    try:
        # 加载配置
        config = load_config(args.config)

        # 应用命令行参数覆盖
        if args.verbose:
            config.setdefault('logging', {})['verbose'] = True

        # 执行
        if args.scenario:
            # 使用预设场景
            return run_with_scenario(config, args.scenario)
        elif args.log:
            # 使用直接输入的日志
            return run_with_log_input(config, args.log)
        else:
            # 默认：列出可用场景
            scenarios = config.get('scenarios', {})
            if not scenarios:
                print("❌ 配置文件中没有定义场景")
                print("提示：使用 --log 参数直接输入日志，或使用 --scenario 指定场景")
                return 1

            print("可用场景：")
            print("=" * 80)
            for name, scenario in scenarios.items():
                desc = scenario.get('description', 'N/A')
                mode = scenario.get('mode', 'auto')
                print(f"  {name:15} - {desc} ({mode})")
            print("=" * 80)
            print("\n使用方式：")
            print(f"  python {sys.argv[0]} --scenario mmc_auto")
            print(f"  python {sys.argv[0]} --log \"mmc0: tuning execution failed: -1\"")
            return 0

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
