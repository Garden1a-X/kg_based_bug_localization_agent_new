#!/usr/bin/env python3
"""
KG 探索脚本 - 理解图谱结构（精简输出版）
用法: python explore_kg.py <data_dir>
"""
import sys
import json
from pathlib import Path
from collections import defaultdict


def load_kg_raw(data_dir: str):
    data_dir = Path(data_dir)
    entity_file = data_dir / 'entity.json'
    rel_file_jsonl = data_dir / 'relation.jsonl'
    rel_file_json  = data_dir / 'relation.json'

    if not entity_file.exists():
        sys.exit(f"[ERROR] entity.json not found in {data_dir}")

    with open(entity_file, 'r', encoding='utf-8') as f:
        entities_raw = json.load(f)

    if rel_file_jsonl.exists():
        with open(rel_file_jsonl, 'r', encoding='utf-8') as f:
            relations_raw = [json.loads(l) for l in f if l.strip()]
    elif rel_file_json.exists():
        with open(rel_file_json, 'r', encoding='utf-8') as f:
            relations_raw = json.load(f)
    else:
        sys.exit("[ERROR] relation.json / relation.jsonl not found")

    return entities_raw, relations_raw


def group_entities(raw):
    g = defaultdict(list)
    if isinstance(raw, dict):
        for etype, lst in raw.items():
            for e in lst:
                e['_t'] = etype
                g[etype].append(e)
    else:
        for e in raw:
            etype = e.get('type') or e.get('entity_type') or 'Unknown'
            e['_t'] = etype
            g[etype].append(e)
    return g


def group_relations(raw):
    g = defaultdict(list)
    if isinstance(raw, dict):
        for rtype, lst in raw.items():
            for r in lst:
                r['_t'] = rtype
                g[rtype].append(r)
    else:
        for r in raw:
            rtype = r.get('type') or r.get('relation_type') or 'UNKNOWN'
            r['_t'] = rtype
            g[rtype].append(r)
    return g


def build_id_map(entities_by_type):
    m = {}
    for lst in entities_by_type.values():
        for e in lst:
            eid = str(e.get('id', ''))
            if eid:
                m[eid] = e
    return m


def fmt_entity(e):
    """单行摘要：跳过 code/body 字段"""
    skip = {'_t', 'code', 'body'}
    parts = [f"{k}={v}" for k, v in e.items() if k not in skip and v not in (None, '')]
    return '  ' + '  '.join(parts)


def fmt_rel(r, id_map):
    h = id_map.get(str(r.get('head', '')), {})
    t = id_map.get(str(r.get('tail', '')), {})
    skip = {'_t', 'head', 'tail', 'type', 'relation_type'}
    extra = {k: v for k, v in r.items() if k not in skip}
    return (f"  [{h.get('type','?')}:{h.get('name','?')}] "
            f"--{r.get('type') or r.get('relation_type','')}-> "
            f"[{t.get('type','?')}:{t.get('name','?')}]"
            + (f"  {extra}" if extra else ""))


def main():
    if len(sys.argv) < 2:
        print("用法: python explore_kg.py <kg_data_dir>")
        sys.exit(1)

    entities_raw, relations_raw = load_kg_raw(sys.argv[1])
    E = group_entities(entities_raw)
    R = group_relations(relations_raw)
    ID = build_id_map(E)

    total_e = sum(len(v) for v in E.values())
    total_r = sum(len(v) for v in R.values())
    print(f"\n=== KG 概览: {total_e} 实体 / {total_r} 关系 ===\n")

    # ── 1. 实体类型统计 + 1个例子 + 字段列表 ──────────────────────────
    print("【实体类型】")
    for etype, lst in sorted(E.items(), key=lambda x: -len(x[1])):
        all_keys = sorted({k for e in lst for k in e if k != '_t'})
        print(f"  {etype:20s} {len(lst):7d} 个  字段: {all_keys}")

    # ── 2. 关系类型统计 + 1个例子 + head→tail类型 ────────────────────
    print("\n【关系类型】")
    for rtype, lst in sorted(R.items(), key=lambda x: -len(x[1])):
        pairs = defaultdict(int)
        for r in lst:
            h = ID.get(str(r.get('head','')), {}).get('type','?')
            t = ID.get(str(r.get('tail','')), {}).get('type','?')
            pairs[f"{h}→{t}"] += 1
        top_pairs = ', '.join(f"{p}:{c}" for p,c in sorted(pairs.items(), key=lambda x:-x[1])[:3])
        print(f"  {rtype:25s} {len(lst):7d} 条  [{top_pairs}]")

    # ── 3. FUNCTION 字段覆盖率 ────────────────────────────────────────
    funcs = E.get('FUNCTION', [])
    if funcs:
        print(f"\n【FUNCTION 字段覆盖率】(共 {len(funcs)} 个)")
        fc = defaultdict(int)
        for f in funcs:
            for k, v in f.items():
                if k != '_t' and v not in (None, ''):
                    fc[k] += 1
        for k, c in sorted(fc.items(), key=lambda x: -x[1]):
            print(f"  {k:25s} {c:7d} ({c/len(funcs)*100:.0f}%)")

    # ── 4. ioctl 专项 ─────────────────────────────────────────────────
    print("\n【ioctl 专项】")

    # 4a. 含 ioctl 的函数数量 + 1例
    ioctl_funcs = [f for f in funcs if 'ioctl' in f.get('name','').lower()]
    print(f"  含'ioctl'的FUNCTION实体: {len(ioctl_funcs)} 个")
    if ioctl_funcs:
        f = ioctl_funcs[0]
        print(f"  例: name={f.get('name')}  id={f.get('id')}  is_decl={f.get('is_declaration')}  "
              f"start={f.get('start_line')}  end={f.get('end_line')}  file={f.get('source_file','')}")

    # 4b. 同名函数有多少有歧义（只打数量 + 1例）
    name_ids = defaultdict(list)
    for f in funcs:
        name_ids[f.get('name','')].append(str(f.get('id','')))
    dups = {n: ids for n, ids in name_ids.items() if len(ids) > 1}
    print(f"\n  同名多ID的函数: {len(dups)} 个")
    if dups:
        name, ids = next(iter(dups.items()))
        print(f"  例: '{name}' 有 {len(ids)} 个实体:")
        for eid in ids[:3]:
            e = ID.get(eid, {})
            print(f"    id={eid}  is_decl={e.get('is_declaration')}  "
                  f"start={e.get('start_line')}  end={e.get('end_line')}  file={e.get('source_file','')}")

    # 4c. ASSIGNED_TO 中 tail 含 ioctl（fops handler 映射）
    assigned = R.get('ASSIGNED_TO', [])
    ioctl_asgn = [r for r in assigned if 'ioctl' in ID.get(str(r.get('tail','')), {}).get('name','').lower()]
    print(f"\n  ASSIGNED_TO tail含'ioctl': {len(ioctl_asgn)} 条")
    if ioctl_asgn:
        r = ioctl_asgn[0]
        h = ID.get(str(r.get('head','')), {})
        t = ID.get(str(r.get('tail','')), {})
        print(f"  例: {h.get('type')}:{h.get('name')} (scope={h.get('scope')}, file={h.get('source_file','')})")
        print(f"      → FUNCTION:{t.get('name')} (file={t.get('source_file','')})")
        extra = {k: v for k, v in r.items() if k not in ('head','tail','type','_t','relation_type')}
        if extra:
            print(f"      关系附加字段: {extra}")

    # 4d. CALLS 中 callee == 'ioctl'
    calls = R.get('CALLS', [])
    ioctl_calls = [r for r in calls if ID.get(str(r.get('tail','')), {}).get('name','') == 'ioctl']
    print(f"\n  CALLS callee=='ioctl': {len(ioctl_calls)} 条")
    if ioctl_calls:
        r = ioctl_calls[0]
        caller = ID.get(str(r.get('head','')), {})
        print(f"  例: caller={caller.get('name')} (file={caller.get('source_file','')})  call_line={r.get('call_line')}")

    # 4e. CALLS 结构
    if calls:
        call_types = defaultdict(int)
        has_line = sum(1 for r in calls if r.get('call_line'))
        for r in calls:
            call_types[r.get('call_type','<none>')] += 1
        all_keys = sorted({k for r in calls for k in r} - {'_t'})
        print(f"\n  CALLS 关系字段: {all_keys}")
        print(f"  call_type分布: {dict(call_types)}")
        print(f"  有call_line: {has_line}/{len(calls)}")


if __name__ == '__main__':
    main()
