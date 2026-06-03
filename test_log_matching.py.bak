#!/usr/bin/env python3
"""
测试日志匹配逻辑
演示如何从日志逐行匹配到FAIL_MESSAGE实体，推断关键函数
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.mock_indirect_calls import (
    MOCK_FAIL_MESSAGES,
    _extract_message_pattern
)
from openai import OpenAI
from loguru import logger
import re
import json
import os


def match_log_line_to_fail_message(log_line: str, fail_messages: dict) -> list:
    """
    尝试将一行日志匹配到FAIL_MESSAGE实体

    Args:
        log_line: 单行日志文本
        fail_messages: FAIL_MESSAGE实体字典

    Returns:
        匹配到的消息列表 [(msg_id, msg_data, matched_text, similarity), ...]
    """
    matches = []

    for msg_id, msg_data in fail_messages.items():
        # 从name字段提取匹配模式
        pattern = _extract_message_pattern(msg_data.get('name', ''))
        if not pattern:
            continue

        # 尝试匹配
        match_obj = re.search(pattern, log_line, re.IGNORECASE)
        if match_obj:
            matched_text = match_obj.group(0)

            # 计算相似度（匹配长度占日志行的比例）
            similarity = len(matched_text) / len(log_line.strip()) if log_line.strip() else 0

            matches.append((msg_id, msg_data, matched_text, similarity))

    # 按相似度排序（从高到低）
    matches.sort(key=lambda x: x[3], reverse=True)

    return matches


def analyze_log_by_lines(log_text: str) -> dict:
    """
    逐行分析日志，匹配FAIL_MESSAGE

    Args:
        log_text: 完整日志文本

    Returns:
        分析结果
    """
    lines = [line.strip() for line in log_text.strip().split('\n') if line.strip()]

    result = {
        'total_lines': len(lines),
        'line_matches': [],
        'all_functions': []
    }

    print("=" * 70)
    print("逐行分析日志")
    print("=" * 70)

    for idx, line in enumerate(lines, 1):
        print(f"\n【第{idx}行】 {line}")

        matches = match_log_line_to_fail_message(line, MOCK_FAIL_MESSAGES)

        if matches:
            # 取最佳匹配（相似度最高）
            best_msg_id, best_msg, matched_text, similarity = matches[0]
            func_name = best_msg.get('scope')

            print(f"  ✓ 匹配成功!")
            print(f"    匹配文本: '{matched_text}'")
            print(f"    相似度: {similarity:.2%}")
            print(f"    推断函数: {func_name}")
            print(f"    源文件: {best_msg.get('source_file')}:{best_msg.get('start_line')}")

            # 显示FAIL_MESSAGE的原始name
            print(f"    原始代码: {best_msg.get('name')}")

            # 记录所有候选函数（用于LLM分析）
            candidates = []
            for msg_id, msg, txt, sim in matches:
                candidates.append({
                    'function': msg.get('scope'),
                    'message_id': msg_id,
                    'source_file': msg.get('source_file'),
                    'start_line': msg.get('start_line'),
                    'similarity': sim,
                    'matched_text': txt
                })

            result['line_matches'].append({
                'line_number': idx,
                'log_line': line,
                'matched_text': matched_text,
                'similarity': similarity,
                'function': func_name,
                'message_id': best_msg_id,
                'source_file': best_msg.get('source_file'),
                'start_line': best_msg.get('start_line'),
                'candidates': candidates  # 所有候选函数
            })

            if func_name and func_name not in result['all_functions']:
                result['all_functions'].append(func_name)

            # 如果有多个匹配，显示其他候选
            if len(matches) > 1:
                print(f"    其他候选:")
                for msg_id, msg, txt, sim in matches[1:]:
                    print(f"      - {msg.get('scope')} (相似度: {sim:.2%})")
        else:
            print(f"  ✗ 未匹配到FAIL_MESSAGE")

    return result


def display_summary(result: dict):
    """显示分析汇总"""
    print("\n" + "=" * 70)
    print("分析汇总")
    print("=" * 70)

    print(f"\n总日志行数: {result['total_lines']}")
    print(f"成功匹配: {len(result['line_matches'])} 行")
    print(f"推断出的函数: {len(result['all_functions'])} 个")

    if result['all_functions']:
        print("\n关键函数列表（按日志出现顺序）:")
        for idx, func in enumerate(result['all_functions'], 1):
            print(f"  {idx}. {func}")

        print("\n💡 调用链顺序（逆序，因为日志是栈式）:")
        print(f"  入口 → {' → '.join(reversed(result['all_functions']))} → 错误点")


def analyze_log_with_llm(log_text: str, result: dict) -> dict:
    """
    使用LLM分析日志，进行候选函数消歧和入口点推断

    Args:
        log_text: 完整日志文本
        result: analyze_log_by_lines()的结果

    Returns:
        LLM分析结果 {start_entity, end_entity, intermediate_entities, reasoning}
    """
    # 初始化OpenAI客户端
    try:
        client = OpenAI(api_key="", base_url="http://10.12.208.86:8502")
    except Exception as e:
        logger.error(f"初始化OpenAI客户端失败: {e}")
        return {
            "error": f"初始化OpenAI客户端失败: {e}",
            "start_entity": None,
            "end_entity": None,
            "intermediate_entities": []
        }

    # 构建提示词
    prompt = f"""你是一个Linux内核驱动错误分析专家。请分析以下错误日志，完成两个任务：

## 错误日志
```
{log_text.strip()}
```

## 日志匹配结果
每行日志已匹配到代码中的FAIL_MESSAGE实体（错误打印语句）：

"""

    # 添加每行的匹配信息
    for match in result['line_matches']:
        if not match.get('candidates'):
            continue

        prompt += f"**第{match['line_number']}行**: `{match['log_line']}`\n"

        if len(match['candidates']) > 1:
            prompt += f"  有 {len(match['candidates'])} 个候选函数（需要消歧）:\n"
            for cand in match['candidates']:
                prompt += f"    - {cand['function']} ({cand['source_file']}:{cand['start_line']}) 相似度={cand['similarity']:.2%}\n"
        else:
            cand = match['candidates'][0]
            prompt += f"  匹配函数: {cand['function']} ({cand['source_file']}:{cand['start_line']})\n"

        prompt += "\n"

    # 添加任务说明
    prompt += """
## 任务

1. **消歧**: 对于有多个候选的日志行，选择最可能的函数
2. **推断入口点**: 推断这个驱动代码在用户态可能的入口函数（通常是probe/init类函数）
3. **识别错误点**: 识别实际发生错误的函数（通常是最底层/最具体的函数）
4. **识别中间点**: 识别调用链中的关键中间函数

## 背景知识
- 这是一个MMC/SD卡驱动错误
- 日志通常是栈式的（最深的函数错误先打印）
- 驱动通常从probe函数开始初始化
- 错误链可能是: 入口(probe) → 初始化 → 执行操作 → 错误点

## 输出格式
请以JSON格式返回，包含：
```json
{
  "start_entity": "入口函数名",
  "end_entity": "错误点函数名",
  "intermediate_entities": ["中间函数1", "中间函数2", ...],
  "reasoning": "推理过程说明",
  "disambiguation": {
    "line_1": "选择的函数名（如果有多个候选）",
    ...
  }
}
```
"""

    print("\n" + "=" * 70)
    print("LLM分析中...")
    print("=" * 70)

    try:
        # 调用LLM
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一个Linux内核驱动错误分析专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
            timeout=180
        )

        llm_response = response.choices[0].message.content

        if not llm_response:
            return {
                "error": "LLM调用失败",
                "start_entity": None,
                "end_entity": None,
                "intermediate_entities": []
            }

        print(f"\nLLM原始响应:\n{llm_response}\n")

        # 解析JSON（处理markdown代码块）
        json_text = llm_response
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()

        llm_result = json.loads(json_text)

        return llm_result

    except Exception as e:
        logger.error(f"LLM分析失败: {e}")
        return {
            "error": str(e),
            "start_entity": None,
            "end_entity": None,
            "intermediate_entities": []
        }


def display_llm_results(llm_result: dict):
    """显示LLM分析结果"""
    print("\n" + "=" * 70)
    print("LLM分析结果")
    print("=" * 70)

    if llm_result.get('error'):
        print(f"\n❌ 分析失败: {llm_result['error']}")
        return

    print(f"\n🎯 入口点: {llm_result.get('start_entity', 'N/A')}")
    print(f"🔴 错误点: {llm_result.get('end_entity', 'N/A')}")

    intermediate = llm_result.get('intermediate_entities', [])
    if intermediate:
        print(f"\n📍 中间关键点 ({len(intermediate)} 个):")
        for idx, func in enumerate(intermediate, 1):
            print(f"  {idx}. {func}")

    if llm_result.get('disambiguation'):
        print(f"\n🔍 消歧决策:")
        for line, func in llm_result['disambiguation'].items():
            print(f"  {line}: 选择 {func}")

    if llm_result.get('reasoning'):
        print(f"\n💭 推理过程:")
        print(f"  {llm_result['reasoning']}")

    # 显示完整调用链
    if llm_result.get('start_entity') and llm_result.get('end_entity'):
        chain = [llm_result['start_entity']]
        chain.extend(intermediate)
        chain.append(llm_result['end_entity'])
        print(f"\n🔗 推断的完整调用链:")
        print(f"  {' → '.join(chain)}")


def extract_functions_from_log(log_text: str, use_llm: bool = False) -> dict:
    """
    从日志中提取关键函数（起始点、错误点、中间点）

    Args:
        log_text: 错误日志文本
        use_llm: 是否使用LLM进行增强分析

    Returns:
        {
            'start_entity': 起始函数名,
            'end_entity': 错误点函数名,
            'intermediate_entities': [中间函数列表],
            'all_functions': [所有匹配的函数列表],
            'pattern_matching': 模式匹配详细结果,
            'llm_analysis': LLM分析结果（如果启用）
        }
    """
    # 1. 逐行分析日志，进行模式匹配
    pattern_result = analyze_log_by_lines(log_text)

    # 2. 如果启用LLM，进行增强分析
    llm_result = None
    if use_llm:
        llm_result = analyze_log_with_llm(log_text, pattern_result)

    # 3. 提取关键函数
    all_functions = pattern_result.get('all_functions', [])

    # Mock起始点（暂时固定为probe函数）
    start_entity = 'dw_mci_pltfm_probe'

    # 错误点：最底层的函数（日志的第一个匹配函数）
    end_entity = None
    if all_functions:
        end_entity = all_functions[0]

    # 中间点：如果有LLM分析结果，使用LLM的；否则使用模式匹配的
    intermediate_entities = []
    if llm_result and not llm_result.get('error'):
        intermediate_entities = llm_result.get('intermediate_entities', [])
        # 如果LLM推断的错误点更准确，使用它
        if llm_result.get('end_entity'):
            end_entity = llm_result['end_entity']
    else:
        # 使用模式匹配的中间函数（去除第一个作为错误点）
        if len(all_functions) > 1:
            intermediate_entities = all_functions[1:]

    return {
        'start_entity': start_entity,
        'end_entity': end_entity,
        'intermediate_entities': intermediate_entities,
        'all_functions': all_functions,
        'pattern_matching': pattern_result,
        'llm_analysis': llm_result
    }


def main():
    """主测试函数"""
    # 测试日志
    mmc_error_log = """
ALL phases bad!
mmc0: tuning execution failed: -1
mmc0: error -1 whilst initialising MMC card
    """

    print("\n测试日志:")
    print("-" * 70)
    print(mmc_error_log.strip())
    print("-" * 70)

    # 逐行分析
    result = analyze_log_by_lines(mmc_error_log)

    # 显示基于模式匹配的汇总
    display_summary(result)

    # LLM分析
    llm_result = analyze_log_with_llm(mmc_error_log, result)

    # 显示LLM分析结果
    display_llm_results(llm_result)

    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)

    # 返回完整结果
    return {
        'pattern_matching': result,
        'llm_analysis': llm_result
    }


if __name__ == "__main__":
    main()
