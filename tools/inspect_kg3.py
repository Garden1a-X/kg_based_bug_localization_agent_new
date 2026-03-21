#!/usr/bin/env python3
"""
探查 KG 中 fops 挂载关系（ASSIGNED_TO）。
重点：cap_ioctl_unlocked / fw_mgmt_ioctl 等函数是否通过 ASSIGNED_TO 挂载到 unlocked_ioctl 字段。
用法：python inspect_kg3.py
"""
import json
from collections import defaultdict

ENTITY_FILE = "/data/xuao/code_kg/data/linux/entity.json"
RELATION_FILE = "/data/xuao/code_kg/data/linux/relation.jsonl"


print("加载实体...")
with open(ENTITY_FILE) as f:
    raw = json.load(f)
entities = raw if isinstance(raw, dict) else {str(i): e for i, e in enumerate(raw)}
print(f"总实体数: {len(entities)}")

# 找到所有名字含 unlocked_ioctl 的实体
print("\n--- 名字含 'unlocked_ioctl' 的实体 ---")
unlocked_ioctl_ids = set()
for eid, e in entities.items():
    if "unlocked_ioctl" in e.get("name", ""):
        unlocked_ioctl_ids.add(eid)
        print(f"  [{eid}] type={e.get('type')} style={e.get('style')} name={e['name']} "
              f"scope={e.get('scope')} @ {e.get('source_file','').split('linux-5.10/')[-1]}:{e.get('start_line')}")

# 找到 cap_ioctl_unlocked 实体
print("\n--- 名字含 'cap_ioctl' 的实体 ---")
cap_ids = set()
for eid, e in entities.items():
    if "cap_ioctl" in e.get("name", "").lower():
        cap_ids.add(eid)
        print(f"  [{eid}] type={e.get('type')} name={e['name']} "
              f"@ {e.get('source_file','').split('linux-5.10/')[-1]}:{e.get('start_line')}")

# 找到 fw_mgmt ioctl 相关函数实体（greybus staging）
print("\n--- greybus staging 中 ioctl 相关函数实体 ---")
fw_ioctl_ids = set()
for eid, e in entities.items():
    src = e.get("source_file", "")
    name = e.get("name", "")
    if "staging/greybus" in src and e.get("type") == "FUNCTION" and "ioctl" in name.lower():
        fw_ioctl_ids.add(eid)
        print(f"  [{eid}] {name} @ {src.split('linux-5.10/')[-1]}:{e.get('start_line')}")

all_target_ids = unlocked_ioctl_ids | cap_ids | fw_ioctl_ids
print(f"\n目标实体共 {len(all_target_ids)} 个，扫描 ASSIGNED_TO 关系...")

# 扫描 ASSIGNED_TO 关系
assigned_rels = []
with open(RELATION_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        if '"ASSIGNED_TO"' not in line:
            continue
        rel = json.loads(line)
        h, t = str(rel["head"]), str(rel["tail"])
        if h in all_target_ids or t in all_target_ids:
            assigned_rels.append(rel)

print(f"相关 ASSIGNED_TO 关系: {len(assigned_rels)} 条")
for r in assigned_rels:
    h, t = str(r["head"]), str(r["tail"])
    h_e = entities.get(h, {})
    t_e = entities.get(t, {})
    print(f"  [{h}]{h_e.get('name','?')}(type={h_e.get('type')}, scope={h_e.get('scope')}) "
          f"--ASSIGNED_TO--> "
          f"[{t}]{t_e.get('name','?')}(type={t_e.get('type')}, scope={t_e.get('scope')}) "
          f"@ {r.get('source_path','').split('linux-5.10/')[-1]}")

# 额外：直接搜所有 greybus staging 的 ASSIGNED_TO，找 unlocked_ioctl 挂载
print("\n--- greybus staging 中所有 ASSIGNED_TO 关系（head 或 tail 在 staging/greybus）---")
greybus_ids = {eid for eid, e in entities.items() if "staging/greybus" in e.get("source_file", "")}
count = 0
with open(RELATION_FILE) as f:
    for line in f:
        if '"ASSIGNED_TO"' not in line:
            continue
        rel = json.loads(line)
        h, t = str(rel["head"]), str(rel["tail"])
        if h in greybus_ids or t in greybus_ids:
            h_e = entities.get(h, {})
            t_e = entities.get(t, {})
            print(f"  {h_e.get('name','?')}(scope={h_e.get('scope')}) "
                  f"--> {t_e.get('name','?')}(scope={t_e.get('scope')}) "
                  f"@ {rel.get('source_path','').split('linux-5.10/')[-1]}")
            count += 1
            if count >= 30:
                print("  ... (只展示前30条)")
                break

print("\n探查完成。")
