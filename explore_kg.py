#!/usr/bin/env python3
"""
KG 探索脚本
用法: python explore_kg.py <data_dir>
"""
import sys
import json
from pathlib import Path
from collections import defaultdict, Counter


def load_kg_raw(data_dir: str):
    data_dir = Path(data_dir)
    entity_file   = data_dir / 'entity.json'
    rel_jsonl     = data_dir / 'relation.jsonl'
    rel_json      = data_dir / 'relation.json'

    if not entity_file.exists():
        sys.exit(f"[ERROR] entity.json not found in {data_dir}")
    with open(entity_file, 'r', encoding='utf-8') as f:
        entities_raw = json.load(f)

    if rel_jsonl.exists():
        with open(rel_jsonl, 'r', encoding='utf-8') as f:
            relations_raw = [json.loads(l) for l in f if l.strip()]
    elif rel_json.exists():
        with open(rel_json, 'r', encoding='utf-8') as f:
            relations_raw = json.load(f)
    else:
        sys.exit("[ERROR] relation.json / relation.jsonl not found")

    return entities_raw, relations_raw


def build_id_map(entities_raw):
    """id -> entity，不做任何分组假设"""
    m = {}
    def add(e):
        eid = str(e.get('id', ''))
        if eid:
            m[eid] = e
    if isinstance(entities_raw, dict):
        for v in entities_raw.values():
            if isinstance(v, list):
                for e in v: add(e)
            elif isinstance(v, dict):
                add(v)
    elif isinstance(entities_raw, list):
        for e in entities_raw: add(e)
    return m


def all_entities(entities_raw):
    """返回所有实体的平铺列表"""
    result = []
    if isinstance(entities_raw, dict):
        for v in entities_raw.values():
            if isinstance(v, list):
                result.extend(v)
            elif isinstance(v, dict):
                result.append(v)
    elif isinstance(entities_raw, list):
        result = entities_raw
    return result


def group_relations(raw):
    g = defaultdict(list)
    if isinstance(raw, dict):
        for rtype, lst in raw.items():
            for r in lst: g[rtype].append(r)
    else:
        for r in raw:
            rtype = r.get('type') or r.get('relation_type') or 'UNKNOWN'
            g[rtype].append(r)
    return g


def main():
    if len(sys.argv) < 2:
        print("用法: python explore_kg.py <kg_data_dir>")
        sys.exit(1)

    entities_raw, relations_raw = load_kg_raw(sys.argv[1])
    ID = build_id_map(entities_raw)
    entities = all_entities(entities_raw)
    R = group_relations(relations_raw)

    total_e = len(entities)
    total_r = sum(len(v) for v in R.values())
    print(f"\n=== KG 概览: {total_e} 实体 / {total_r} 关系 ===")

    # ── 1. entity.json 顶层结构 ──────────────────────────────────────
    print("\n【entity.json 顶层结构】")
    if isinstance(entities_raw, dict):
        print(f"  格式: dict，共 {len(entities_raw)} 个 key")
        for k, v in list(entities_raw.items())[:10]:
            cnt = len(v) if isinstance(v, list) else 1
            print(f"  key={k!r:30s}  count={cnt}")
    else:
        print(f"  格式: list，共 {total_e} 个实体")

    # ── 2. 实体字段分布（看看有哪些字段，不做分组） ──────────────────
    print(f"\n【实体字段出现频率】(共 {total_e} 个实体)")
    fc = Counter()
    for e in entities:
        for k, v in e.items():
            if v not in (None, ''):
                fc[k] += 1
    for k, c in fc.most_common():
        print(f"  {k:25s} {c:7d} ({c/total_e*100:.0f}%)")

    # ── 3. 关键字段的值分布（各取 top-10） ───────────────────────────
    for field in ('type', 'entity_type', 'scope', 'is_declaration', 'style'):
        vals = Counter(str(e[field]) for e in entities if field in e and e[field] not in (None, ''))
        if not vals:
            continue
        print(f"\n【字段 '{field}' 的值分布 (top 10)】")
        for val, cnt in vals.most_common(10):
            print(f"  {val:30s} {cnt:7d}")
        if len(vals) > 10:
            print(f"  ... 共 {len(vals)} 种值")

    # ── 4. 关系统计 ──────────────────────────────────────────────────
    print(f"\n【关系类型】(共 {total_r} 条)")
    for rtype, lst in sorted(R.items(), key=lambda x: -len(x[1])):
        head_types = Counter(ID.get(str(r.get('head','')), {}).get('type','?') for r in lst)
        tail_types = Counter(ID.get(str(r.get('tail','')), {}).get('type','?') for r in lst)
        rel_keys = sorted({k for r in lst for k in r} - {'head','tail','type','relation_type'})
        print(f"\n  {rtype}  ({len(lst)} 条)")
        print(f"  附加字段: {rel_keys}")
        print(f"  head.type top3: {head_types.most_common(3)}")
        print(f"  tail.type top3: {tail_types.most_common(3)}")
        # 1 个例子
        r = lst[0]
        h = ID.get(str(r.get('head','')), {})
        t = ID.get(str(r.get('tail','')), {})
        print(f"  例: [{h.get('type')}:{h.get('name')}] → [{t.get('type')}:{t.get('name')}]"
              + (f"  line={r['call_line']}" if 'call_line' in r else ""))

    # ── 5. ioctl 专项 ─────────────────────────────────────────────────
    print("\n【ioctl 专项】")
    ioctl_ents = [e for e in entities if 'ioctl' in str(e.get('name','')).lower()]
    print(f"  名称含'ioctl'的实体: {len(ioctl_ents)} 个")
    if ioctl_ents:
        skip = {'code','body'}
        e = ioctl_ents[0]
        print("  例: " + "  ".join(f"{k}={v}" for k,v in e.items() if k not in skip and v not in (None,'')))

    assigned = R.get('ASSIGNED_TO', [])
    ioctl_asgn = [r for r in assigned
                  if 'ioctl' in ID.get(str(r.get('tail','')), {}).get('name','').lower()]
    print(f"\n  ASSIGNED_TO tail含'ioctl': {len(ioctl_asgn)} 条")
    if ioctl_asgn:
        r = ioctl_asgn[0]
        h = ID.get(str(r.get('head','')), {})
        t = ID.get(str(r.get('tail','')), {})
        print(f"  例: [{h.get('type')}:{h.get('name')} scope={h.get('scope')}  file={h.get('source_file','')}]")
        print(f"      → [{t.get('type')}:{t.get('name')}  file={t.get('source_file','')}]")

    calls = R.get('CALLS', [])
    ioctl_calls = [r for r in calls
                   if ID.get(str(r.get('tail','')), {}).get('name','') == 'ioctl']
    print(f"\n  CALLS callee名=='ioctl': {len(ioctl_calls)} 条")
    if ioctl_calls:
        r = ioctl_calls[0]
        h = ID.get(str(r.get('head','')), {})
        print(f"  例: caller={h.get('name')}  file={h.get('source_file','')}  call_line={r.get('call_line')}")


if __name__ == '__main__':
    main()
