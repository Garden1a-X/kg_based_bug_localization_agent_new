#!/usr/bin/env python3
"""
KG 探索脚本 - 理解图谱结构和内容
用法: python explore_kg.py <data_dir>
"""
import sys
import json
import os
from pathlib import Path
from collections import defaultdict

# ─────────────────────────────────────────
# 1. 加载数据
# ─────────────────────────────────────────
def load_kg_raw(data_dir: str):
    data_dir = Path(data_dir)
    entity_file = data_dir / 'entity.json'
    rel_file_jsonl = data_dir / 'relation.jsonl'
    rel_file_json  = data_dir / 'relation.json'

    if not entity_file.exists():
        print(f"[ERROR] entity.json not found in {data_dir}")
        sys.exit(1)

    with open(entity_file, 'r', encoding='utf-8') as f:
        entities_raw = json.load(f)

    if rel_file_jsonl.exists():
        with open(rel_file_jsonl, 'r', encoding='utf-8') as f:
            relations_raw = [json.loads(l) for l in f if l.strip()]
    elif rel_file_json.exists():
        with open(rel_file_json, 'r', encoding='utf-8') as f:
            relations_raw = json.load(f)
    else:
        print("[ERROR] relation.json / relation.jsonl not found")
        sys.exit(1)

    return entities_raw, relations_raw


def group_entities(entities_raw):
    """将实体列表/字典统一成 {type: [entity, ...]}"""
    grouped = defaultdict(list)
    if isinstance(entities_raw, dict):
        # {type: [list]}
        for etype, lst in entities_raw.items():
            for e in lst:
                e['_type'] = etype
                grouped[etype].append(e)
    elif isinstance(entities_raw, list):
        for e in entities_raw:
            etype = e.get('type') or e.get('entity_type') or 'Unknown'
            e['_type'] = etype
            grouped[etype].append(e)
    return grouped


def group_relations(relations_raw):
    """将关系列表统一成 {rel_type: [rel, ...]}"""
    grouped = defaultdict(list)
    if isinstance(relations_raw, dict):
        for rtype, lst in relations_raw.items():
            for r in lst:
                r['_type'] = rtype
                grouped[rtype].append(r)
    elif isinstance(relations_raw, list):
        for r in relations_raw:
            rtype = r.get('type') or r.get('relation_type') or 'UNKNOWN'
            r['_type'] = rtype
            grouped[rtype].append(r)
    return grouped


def build_id_map(entities_by_type):
    id_map = {}
    for etype, lst in entities_by_type.items():
        for e in lst:
            eid = str(e.get('id', ''))
            if eid:
                id_map[eid] = e
    return id_map


# ─────────────────────────────────────────
# 2. 辅助打印
# ─────────────────────────────────────────
SEP = "─" * 70

def section(title):
    print(f"\n{'═'*70}")
    print(f"  {title}")
    print('═'*70)

def subsection(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def show_entity(e, prefix="  "):
    """打印实体的所有字段，跳过过长的 code 字段"""
    for k, v in e.items():
        if k == 'code' or k == 'body':
            snippet = str(v)[:120].replace('\n', '↵') + ('...' if len(str(v)) > 120 else '')
            print(f"{prefix}{k}: {snippet}")
        elif k == '_type':
            continue
        else:
            print(f"{prefix}{k}: {v}")

def show_relation_with_entities(r, id_map, prefix="  "):
    """打印关系及其头尾实体摘要"""
    head_id = str(r.get('head', ''))
    tail_id = str(r.get('tail', ''))
    head = id_map.get(head_id, {})
    tail = id_map.get(tail_id, {})

    for k, v in r.items():
        if k in ('_type', 'head', 'tail'):
            continue
        print(f"{prefix}{k}: {v}")

    head_desc = f"{head.get('type','?')}:{head.get('name','?')} (id={head_id}, file={head.get('source_file','')})"
    tail_desc = f"{tail.get('type','?')}:{tail.get('name','?')} (id={tail_id}, file={tail.get('source_file','')})"
    print(f"{prefix}head → {head_desc}")
    print(f"{prefix}tail → {tail_desc}")


# ─────────────────────────────────────────
# 3. 分析模块
# ─────────────────────────────────────────
def analyze_entities(entities_by_type):
    section("实体类型统计 (Entity Types)")
    total = sum(len(v) for v in entities_by_type.values())
    print(f"  总实体数: {total}")
    for etype, lst in sorted(entities_by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {etype:20s}: {len(lst):6d} 个")

    for etype, lst in entities_by_type.items():
        subsection(f"实体类型: {etype}  (共 {len(lst)} 个，展示前 2 个)")
        for e in lst[:2]:
            print("  ┌─ 实体字段:")
            show_entity(e, "  │  ")
            print("  └─")

        # 统计该类型下所有出现的字段
        all_keys = set()
        for e in lst:
            all_keys.update(e.keys())
        all_keys.discard('_type')
        print(f"\n  【字段总览】: {sorted(all_keys)}")


def analyze_relations(relations_by_type, id_map):
    section("关系类型统计 (Relation Types)")
    total = sum(len(v) for v in relations_by_type.values())
    print(f"  总关系数: {total}")
    for rtype, lst in sorted(relations_by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {rtype:25s}: {len(lst):7d} 条")

    for rtype, lst in relations_by_type.items():
        subsection(f"关系类型: {rtype}  (共 {len(lst)} 条，展示前 2 条)")
        for r in lst[:2]:
            print("  ┌─ 关系字段:")
            show_relation_with_entities(r, id_map, "  │  ")
            print("  └─")

        # 统计 head/tail 的实体类型组合
        pairs = defaultdict(int)
        for r in lst:
            h = id_map.get(str(r.get('head', '')), {})
            t = id_map.get(str(r.get('tail', '')), {})
            ht = f"{h.get('type','?')} → {t.get('type','?')}"
            pairs[ht] += 1
        print(f"\n  【head→tail 类型组合】:")
        for pair, cnt in sorted(pairs.items(), key=lambda x: -x[1])[:8]:
            print(f"    {pair}: {cnt}")


def analyze_ioctl_specific(entities_by_type, relations_by_type, id_map):
    """专项：与 ioctl 相关的结构"""
    section("ioctl 专项分析")

    # 3a. 找所有名字含 ioctl 的 FUNCTION 实体
    funcs = entities_by_type.get('FUNCTION', [])
    ioctl_funcs = [f for f in funcs if 'ioctl' in f.get('name','').lower()]
    subsection(f"名称含 'ioctl' 的 FUNCTION 实体: {len(ioctl_funcs)} 个")
    for f in ioctl_funcs[:5]:
        print(f"  name={f.get('name')}  id={f.get('id')}  is_decl={f.get('is_declaration')}  "
              f"start={f.get('start_line')}  end={f.get('end_line')}  file={f.get('source_file','')}")

    # 3b. 同名函数多实体（歧义问题核心）
    name_to_ids = defaultdict(list)
    for f in funcs:
        name_to_ids[f.get('name','')].append(str(f.get('id','')))
    duplicates = {n: ids for n, ids in name_to_ids.items() if len(ids) > 1}
    subsection(f"同名 FUNCTION 实体（歧义情况）: {len(duplicates)} 个函数有多个 ID")
    # 展示前 5 个
    for name, ids in list(duplicates.items())[:5]:
        entities = [id_map.get(i, {}) for i in ids]
        print(f"  函数名: {name}  ({len(ids)} 个实体)")
        for e in entities:
            print(f"    id={e.get('id')}  is_decl={e.get('is_declaration')}  "
                  f"start={e.get('start_line')}  end={e.get('end_line')}  "
                  f"file={e.get('source_file','')}")

    # 3c. ASSIGNED_TO 关系（fops → ioctl handler）
    assigned = relations_by_type.get('ASSIGNED_TO', [])
    ioctl_assigned = []
    for r in assigned:
        tail = id_map.get(str(r.get('tail','')), {})
        if 'ioctl' in tail.get('name','').lower():
            ioctl_assigned.append(r)
    subsection(f"ASSIGNED_TO 关系中 tail 含 'ioctl': {len(ioctl_assigned)} 条")
    for r in ioctl_assigned[:5]:
        head = id_map.get(str(r.get('head','')), {})
        tail = id_map.get(str(r.get('tail','')), {})
        print(f"  {head.get('type','?')}:{head.get('name','?')} "
              f"(scope={head.get('scope','?')}, file={head.get('source_file','')}) "
              f"─ASSIGNED_TO→ "
              f"FUNCTION:{tail.get('name','?')} (file={tail.get('source_file','')})")
        # 关系本身有没有额外字段？
        extra = {k: v for k, v in r.items() if k not in ('head','tail','type','_type','relation_type')}
        if extra:
            print(f"    关系附加字段: {extra}")

    # 3d. CALLS 关系中 callee 是 'ioctl'（用户态ioctl()调用痕迹）
    calls = relations_by_type.get('CALLS', [])
    ioctl_calls = []
    for r in calls:
        tail = id_map.get(str(r.get('tail','')), {})
        if tail.get('name','') == 'ioctl':
            ioctl_calls.append(r)
    subsection(f"CALLS 关系中 callee 名称 == 'ioctl': {len(ioctl_calls)} 条")
    for r in ioctl_calls[:5]:
        caller = id_map.get(str(r.get('head','')), {})
        callee = id_map.get(str(r.get('tail','')), {})
        print(f"  caller: {caller.get('name','?')} (file={caller.get('source_file','')})")
        print(f"  callee: {callee.get('name','?')}  call_line={r.get('call_line','?')}")
        extra = {k: v for k, v in r.items() if k not in ('head','tail','type','_type','relation_type','call_line')}
        if extra:
            print(f"  关系附加字段: {extra}")
        print()


def analyze_calls_structure(relations_by_type, id_map):
    """CALLS 关系的详细结构"""
    section("CALLS 关系结构分析")
    calls = relations_by_type.get('CALLS', [])
    if not calls:
        print("  [无 CALLS 关系]")
        return

    # 关系本身有哪些字段？
    all_keys = set()
    for r in calls:
        all_keys.update(r.keys())
    all_keys -= {'_type'}
    print(f"  CALLS 关系字段: {sorted(all_keys)}")

    # call_type / target_type 分布
    call_types = defaultdict(int)
    target_types = defaultdict(int)
    has_call_line = 0
    for r in calls:
        call_types[r.get('call_type','<none>')] += 1
        target_types[r.get('target_type','<none>')] += 1
        if r.get('call_line'):
            has_call_line += 1

    print(f"\n  call_type 分布: {dict(call_types)}")
    print(f"  target_type 分布: {dict(target_types)}")
    print(f"  有 call_line 的关系: {has_call_line} / {len(calls)}")

    # 举例：一个 indirect call 的完整关系
    indirect = [r for r in calls if r.get('call_type') == 'indirect']
    if indirect:
        subsection(f"间接调用示例 (共 {len(indirect)} 条)，展示 2 条:")
        for r in indirect[:2]:
            show_relation_with_entities(r, id_map, "  ")
            print()


def analyze_function_entity_fields(entities_by_type):
    """FUNCTION 实体字段完整性检查"""
    section("FUNCTION 实体字段完整性")
    funcs = entities_by_type.get('FUNCTION', [])
    if not funcs:
        print("  [无 FUNCTION 实体]")
        return

    field_presence = defaultdict(int)
    for f in funcs:
        for k in f.keys():
            if k != '_type' and f[k] is not None and f[k] != '':
                field_presence[k] += 1

    total = len(funcs)
    print(f"  总 FUNCTION 实体数: {total}")
    print(f"\n  字段覆盖率（有值的比例）:")
    for k, cnt in sorted(field_presence.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        print(f"    {k:25s}: {cnt:6d} / {total} ({pct:.1f}%)")


# ─────────────────────────────────────────
# 4. main
# ─────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("用法: python explore_kg.py <kg_data_dir>")
        print("示例: python explore_kg.py /data/xuao/code_kg_search/linux_test/data")
        sys.exit(1)

    data_dir = sys.argv[1]
    print(f"加载 KG 数据: {data_dir}")

    entities_raw, relations_raw = load_kg_raw(data_dir)
    entities_by_type = group_entities(entities_raw)
    relations_by_type = group_relations(relations_raw)
    id_map = build_id_map(entities_by_type)

    print(f"加载完成: {sum(len(v) for v in entities_by_type.values())} 个实体, "
          f"{sum(len(v) for v in relations_by_type.values())} 条关系")

    analyze_entities(entities_by_type)
    analyze_function_entity_fields(entities_by_type)
    analyze_relations(relations_by_type, id_map)
    analyze_calls_structure(relations_by_type, id_map)
    analyze_ioctl_specific(entities_by_type, relations_by_type, id_map)

    section("完成")
    print("  探索完毕。关键问题参考上面输出：")
    print("  1. FUNCTION 实体有没有 start_line/end_line？")
    print("  2. CALLS 关系有没有 call_line？head/tail 是实体ID还是名字？")
    print("  3. 同名函数的多个实体如何区分（靠 source_file + is_declaration）？")
    print("  4. ioctl() 调用在 CALLS 里有没有记录？还是只有 ASSIGNED_TO？")
    print("  5. 扫描到的 caller_func 在 KG 里能找到吗（名字 + 文件 双重匹配）？")


if __name__ == '__main__':
    main()
