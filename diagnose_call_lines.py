#!/usr/bin/env python3
"""
诊断脚本：检查CALLS关系中是否包含call_line信息
"""
import sys
import json
from pathlib import Path
from collections import Counter

def main():
    if len(sys.argv) < 2:
        print("用法: python diagnose_call_lines.py <data_dir>")
        print("示例: python diagnose_call_lines.py /data/xuao/code_kg_search/subgraph/drivers/mmc")
        sys.exit(1)

    data_dir = Path(sys.argv[1])

    print("=" * 80)
    print("检查 CALLS 关系中的 call_line 信息")
    print("=" * 80)
    print(f"数据目录: {data_dir}")
    print()

    # 检查文件格式
    relation_file = data_dir / 'relation.json'
    if not relation_file.exists():
        print(f"❌ 未找到 relation.json 文件")
        print(f"   查找的路径: {relation_file}")

        # 尝试查找其他文件
        print(f"\n查找数据目录中的文件:")
        if data_dir.exists():
            for f in data_dir.iterdir():
                print(f"  - {f.name}")
        else:
            print(f"❌ 数据目录不存在: {data_dir}")
        return

    print(f"✓ 找到 relation.json")

    # 加载关系数据
    with open(relation_file, 'r', encoding='utf-8') as f:
        relations_data = json.load(f)

    print(f"✓ 关系数据类型: {type(relations_data).__name__}")

    # 提取 CALLS 关系
    calls_relations = []
    if isinstance(relations_data, dict):
        # 字典格式
        calls_relations = relations_data.get('CALLS', [])
        print(f"✓ 格式: 字典格式")
    elif isinstance(relations_data, list):
        # 列表格式
        calls_relations = [r for r in relations_data if r.get('type') == 'CALLS']
        print(f"✓ 格式: 列表格式")

    print(f"✓ CALLS 关系总数: {len(calls_relations)}")
    print()

    if not calls_relations:
        print("❌ 没有找到 CALLS 关系!")
        return

    # 统计 call_line 信息
    call_line_stats = {
        'has_call_line': 0,      # 有 call_line 字段
        'no_call_line': 0,       # 没有 call_line 字段
        'call_line_none': 0,     # call_line 是 None
        'call_line_zero': 0,     # call_line 是 0
        'call_line_positive': 0, # call_line > 0
    }

    call_line_values = []

    for rel in calls_relations:
        if 'call_line' in rel:
            call_line_stats['has_call_line'] += 1
            call_line = rel['call_line']

            if call_line is None:
                call_line_stats['call_line_none'] += 1
            elif call_line == 0:
                call_line_stats['call_line_zero'] += 1
            elif call_line > 0:
                call_line_stats['call_line_positive'] += 1
                call_line_values.append(call_line)
        else:
            call_line_stats['no_call_line'] += 1

    # 打印统计结果
    print("📊 call_line 字段统计:")
    print(f"  ✓ 有 call_line 字段:    {call_line_stats['has_call_line']:6d} ({call_line_stats['has_call_line']/len(calls_relations)*100:.1f}%)")
    print(f"  ✗ 无 call_line 字段:    {call_line_stats['no_call_line']:6d} ({call_line_stats['no_call_line']/len(calls_relations)*100:.1f}%)")
    print()
    print("📊 call_line 值分布:")
    print(f"  - call_line = None:     {call_line_stats['call_line_none']:6d} ({call_line_stats['call_line_none']/len(calls_relations)*100:.1f}%)")
    print(f"  - call_line = 0:        {call_line_stats['call_line_zero']:6d} ({call_line_stats['call_line_zero']/len(calls_relations)*100:.1f}%)")
    print(f"  - call_line > 0:        {call_line_stats['call_line_positive']:6d} ({call_line_stats['call_line_positive']/len(calls_relations)*100:.1f}%)")
    print()

    if call_line_values:
        print("📊 call_line 有效值统计:")
        print(f"  - 最小值: {min(call_line_values)}")
        print(f"  - 最大值: {max(call_line_values)}")
        print(f"  - 平均值: {sum(call_line_values)/len(call_line_values):.1f}")
        print()

    # 显示示例
    print("📝 示例 CALLS 关系 (前10个):")
    for i, rel in enumerate(calls_relations[:10], 1):
        head = rel.get('head', 'N/A')
        tail = rel.get('tail', 'N/A')
        call_line = rel.get('call_line', 'N/A')
        call_type = rel.get('call_type', 'N/A')

        print(f"  [{i}] head={head}, tail={tail}, call_line={call_line}, call_type={call_type}")

    # 结论
    print()
    print("=" * 80)
    print("诊断结论:")
    print("=" * 80)

    if call_line_stats['call_line_positive'] > 0:
        ratio = call_line_stats['call_line_positive'] / len(calls_relations) * 100
        print(f"✓ 数据中有 {call_line_stats['call_line_positive']} 个有效的 call_line (>{ratio:.1f}%)")
        print("  建议：检查代码是否正确读取了这些行号")
    elif call_line_stats['has_call_line'] > 0:
        print(f"⚠ 数据中有 call_line 字段，但都是 None 或 0")
        print("  原因：知识图谱提取时可能没有记录调用行号")
        print("  解决：需要重新提取知识图谱，确保记录 call_line 信息")
    else:
        print("❌ 数据中没有 call_line 字段")
        print("  原因：知识图谱版本过旧，不支持 call_line")
        print("  解决：需要使用新版本的知识图谱提取工具重新提取")


if __name__ == '__main__':
    main()
