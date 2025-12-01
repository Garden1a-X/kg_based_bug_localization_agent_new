#!/usr/bin/env python3
"""
Bug定位分析通用入口脚本

支持两种模式：
1. 基于日志自动推断起止点
2. 手动指定起止点和中间节点

功能：
- 可配置图谱路径
- 可配置是否启用子图自动选择
- 可配置是否启用LLM辅助检测
- 可配置Top-K路径数量
- 支持从文件读取日志
- 输出结果到JSON文件
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, List

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from coordinator.master_coordinator import MasterCoordinator
from utils.logger import setup_logger

try:
    import yaml
except ImportError:
    yaml = None


def load_user_context(context_file: str) -> Optional[dict]:
    """从文件加载用户上下文"""
    if not yaml:
        print("警告: 需要安装 PyYAML 才能使用用户上下文功能")
        print("请运行: pip install pyyaml")
        return None

    if not os.path.exists(context_file):
        raise FileNotFoundError(f"用户上下文文件不存在: {context_file}")

    with open(context_file, 'r', encoding='utf-8') as f:
        context = yaml.safe_load(f)

    return context


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Bug定位分析工具 - 基于知识图谱的调用链追踪',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：

1. 基于日志自动推断（使用子图自动选择）：
   python run_bug_localization.py \\
       --data-dir /data/xuao/code_kg_search/linux_test/data \\
       --log "mmc0: tuning execution failed: -1" \\
       --enable-subgraph-selection \\
       --k 5

2. 基于日志自动推断（指定子图）：
   python run_bug_localization.py \\
       --data-dir /data/xuao/code_kg_search/linux_test/data \\
       --log "mmc0: tuning execution failed: -1" \\
       --enable-subgraph-selection \\
       --subgraph mmc \\
       --k 5

3. 手动指定起止点（使用子图自动选择，无需日志）：
   python run_bug_localization.py \\
       --data-dir /data/xuao/code_kg_search/linux_test/data \\
       --start-func dw_mci_pltfm_probe \\
       --end-func dw_mci_execute_tuning \\
       --intermediate-funcs mmc_attach_mmc mmc_execute_tuning \\
       --enable-subgraph-selection \\
       --k 5

4. 传统方式（直接指定子图路径，不启用子图选择）：
   python run_bug_localization.py \\
       --data-dir /data/xuao/code_kg_search/linux_test/data/mmc \\
       --log "mmc0: tuning execution failed: -1" \\
       --k 5

5. 从文件读取日志：
   python run_bug_localization.py \\
       --data-dir /data/xuao/code_kg_search/linux_test/data \\
       --log-file error.log \\
       --enable-subgraph-selection \\
       --k 5

6. 启用LLM辅助间接调用检测：
   python run_bug_localization.py \\
       --data-dir /data/xuao/code_kg_search/linux_test/data \\
       --log "mmc0: tuning execution failed: -1" \\
       --enable-llm-detection \\
       --enable-subgraph-selection \\
       --k 5
        """
    )

    # 必需参数
    parser.add_argument(
        '--data-dir',
        required=True,
        help='知识图谱数据目录路径（可以是父目录或特定子图目录）'
    )

    # 日志输入（二选一，手动模式下可选）
    log_group = parser.add_mutually_exclusive_group(required=False)
    log_group.add_argument(
        '--log',
        help='错误日志文本（自动推断模式必需，手动模式可选）'
    )
    log_group.add_argument(
        '--log-file',
        help='错误日志文件路径（自动推断模式必需，手动模式可选）'
    )

    # 模式选择
    parser.add_argument(
        '--start-func',
        help='起点函数名（手动指定模式）'
    )
    parser.add_argument(
        '--end-func',
        help='终点函数名（手动指定模式）'
    )
    parser.add_argument(
        '--intermediate-funcs',
        nargs='+',
        help='中间节点函数名列表（手动指定模式，可选）'
    )

    # Top-K配置
    parser.add_argument(
        '--k',
        type=int,
        default=5,
        help='返回路径数量上限（默认：5）'
    )

    # 子图选择
    parser.add_argument(
        '--enable-subgraph-selection',
        action='store_true',
        help='启用子图自动选择（需要data-dir为父目录）'
    )
    parser.add_argument(
        '--subgraph',
        help='手动指定子图名称（如：mmc, usb, net等）'
    )

    # LLM功能
    parser.add_argument(
        '--enable-llm-detection',
        action='store_true',
        help='启用LLM辅助间接调用检测'
    )
    parser.add_argument(
        '--enable-llm-log-analysis',
        action='store_true',
        help='启用LLM辅助日志分析'
    )
    parser.add_argument(
        '--llm-model',
        default='gpt-4o-mini',
        help='LLM模型名称（默认：gpt-4o-mini）'
    )
    parser.add_argument(
        '--llm-base-url',
        default='http://10.12.208.86:8502',
        help='LLM服务地址（默认：http://10.12.208.86:8502）'
    )
    parser.add_argument(
        '--user-context',
        help='用户上下文文件路径（YAML格式，提供平台、驱动等额外信息）'
    )

    # 路径映射
    parser.add_argument(
        '--path-mapping',
        action='append',
        help='路径映射规则，格式：旧路径:新路径（可多次指定）\n'
             '例如：--path-mapping "E:\\\\cpppro\\\\clang_kg\\\\linux:/data/xuao/code_kg/data/linux_data"'
    )

    # 输出配置
    parser.add_argument(
        '--output',
        default='output/result.json',
        help='输出JSON文件路径（默认：output/result.json）'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细日志'
    )

    return parser.parse_args()


def load_log_from_file(log_file: str) -> str:
    """从文件加载日志"""
    if not os.path.exists(log_file):
        raise FileNotFoundError(f"日志文件不存在: {log_file}")

    with open(log_file, 'r', encoding='utf-8') as f:
        return f.read()


def create_coordinator(args) -> MasterCoordinator:
    """根据参数创建协调器"""
    # 检查数据目录
    if not os.path.exists(args.data_dir):
        raise FileNotFoundError(f"数据目录不存在: {args.data_dir}")

    # LLM配置
    llm_config = None
    if args.enable_llm_detection or args.enable_llm_log_analysis or args.enable_subgraph_selection:
        llm_config = {
            'backend': 'openai',
            'model': args.llm_model,
            'base_url': args.llm_base_url,
            'api_key': ''
        }

    # 解析路径映射
    path_mappings = {}
    if args.path_mapping:
        for mapping in args.path_mapping:
            # 智能分割：处理 Windows 路径中的冒号（如 E:\path）
            # 策略：从右向左查找冒号，如果冒号前面不是单个字母（Windows盘符），则作为分隔符
            colon_index = -1
            for i in range(len(mapping) - 1, -1, -1):
                if mapping[i] == ':':
                    # 检查是否是 Windows 盘符（前面只有一个字母或字母+反斜杠）
                    if i == 1 or (i > 1 and mapping[i-2] in ['\\', '/']):
                        # 这是 Windows 盘符，继续找前一个冒号
                        continue
                    else:
                        # 这是分隔符
                        colon_index = i
                        break

            if colon_index > 0:
                old_path = mapping[:colon_index].strip()
                new_path = mapping[colon_index+1:].strip()
                path_mappings[old_path] = new_path
                print(f"📍 路径映射: {old_path} -> {new_path}")
            else:
                print(f"⚠️  忽略无效的路径映射: {mapping}（格式应为 '旧路径:新路径'）")

    # 创建协调器
    coordinator = MasterCoordinator(
        data_dir=args.data_dir,
        llm_client=None,
        enable_llm_detection=args.enable_llm_detection,
        enable_llm_log_analysis=args.enable_llm_log_analysis,
        enable_subgraph_selection=args.enable_subgraph_selection,
        llm_config=llm_config,
        path_mappings=path_mappings if path_mappings else None
    )

    return coordinator


def save_result(result: dict, output_path: str):
    """保存结果到JSON文件"""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 结果已保存到: {output_file}")


def extract_call_chain(result: dict) -> List[str]:
    """从结果中提取调用链"""
    if not result.get('success'):
        return []

    # 处理单路径结果
    if 'chain' in result and 'path' in result['chain']:
        return result['chain']['path']

    # 处理多路径结果（Top-K）
    if 'paths' in result and result['paths']:
        # 返回最佳路径（第一条）
        return result['paths'][0]['path']

    return []


def print_summary(result: dict, args):
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


def main():
    """主函数"""
    # 解析参数
    args = parse_args()

    # 配置日志
    setup_logger()

    try:
        # 判断运行模式
        is_manual_mode = args.start_func and args.end_func

        # 验证参数
        if not is_manual_mode and not args.log and not args.log_file:
            print("❌ 错误: 自动推断模式必须提供日志（使用 --log 或 --log-file）")
            print("提示: 如果要手动指定起止点，请使用 --start-func 和 --end-func 参数")
            return 1

        # 加载日志（手动模式下可选）
        log_text = ""
        if args.log:
            log_text = args.log
        elif args.log_file:
            log_text = load_log_from_file(args.log_file)

        # 加载用户上下文（可选）
        user_context = None
        if args.user_context:
            user_context = load_user_context(args.user_context)
            if user_context:
                print(f"📌 用户上下文: {args.user_context}")

        print(f"📋 数据目录: {args.data_dir}")
        if log_text:
            print(f"📝 日志来源: {'命令行' if args.log else args.log_file}")
        else:
            print(f"📝 日志来源: 无（手动模式）")
        print(f"🔢 Top-K: {args.k}")
        print(f"🎯 子图选择: {'✓ 启用' if args.enable_subgraph_selection else '✗ 禁用'}")
        if args.subgraph:
            print(f"📦 指定子图: {args.subgraph}")
        if args.enable_llm_detection:
            print(f"🤖 LLM检测: ✓ 启用")
        if user_context:
            print(f"🔍 用户上下文: ✓ 已提供")
        print()

        # 创建协调器
        coordinator = create_coordinator(args)

        try:
            # 判断模式并执行
            if is_manual_mode and not log_text:
                # 纯手动指定模式（无日志）
                print(f"🎯 模式: 手动指定起止点（无日志）")
                print(f"   起点: {args.start_func}")
                print(f"   终点: {args.end_func}")
                if args.intermediate_funcs:
                    print(f"   中间节点: {', '.join(args.intermediate_funcs)}")
                print()

                result = coordinator.process_top_k_with_specific_functions(
                    log_text,
                    start_func=args.start_func,
                    end_func=args.end_func,
                    intermediate_funcs=args.intermediate_funcs,
                    k=args.k,
                    subgraph_override=args.subgraph,
                    user_context=user_context
                )
            elif is_manual_mode and log_text:
                # 混合模式（日志 + 用户指定起止点）
                print(f"🔄 模式: 混合模式（日志 + 用户指定起止点）")
                print(f"   用户指定起点: {args.start_func}")
                print(f"   用户指定终点: {args.end_func}")
                print(f"   日志解析结果将作为关键节点")
                print()

                result = coordinator.process_top_k(
                    log_text,
                    k=args.k,
                    subgraph_override=args.subgraph,
                    user_context=user_context,
                    user_start_func=args.start_func,
                    user_end_func=args.end_func
                )
            else:
                # 自动推断模式
                print(f"🤖 模式: 基于日志自动推断")
                print()

                result = coordinator.process_top_k(
                    log_text,
                    k=args.k,
                    subgraph_override=args.subgraph,
                    user_context=user_context
                )

            # 保存结果
            save_result(result, args.output)

            # 打印摘要
            print_summary(result, args)

            # 返回状态码
            return 0 if result.get('success') else 1

        finally:
            coordinator.close()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
