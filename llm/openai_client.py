"""
OpenAI LLM 客户端封装
"""
import os
from typing import Optional, Dict, Any
from loguru import logger


class OpenAIClient:
    """OpenAI API 客户端"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini", base_url: Optional[str] = None):
        """
        初始化 OpenAI 客户端

        Args:
            api_key: OpenAI API Key，如果为None则使用空字符串
            model: 模型名称，默认 gpt-4o-mini
            base_url: API服务地址，默认使用 http://10.12.208.86:8502
        """
        self.api_key = api_key if api_key is not None else ""
        self.model = model
        self.base_url = base_url if base_url is not None else "http://10.12.208.86:8502"
        self.client = None

        try:
            # 延迟导入，避免没有安装 openai 包时报错
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(f"OpenAI 客户端初始化成功，模型: {self.model}, 服务地址: {self.base_url}")
        except ImportError:
            logger.error("未安装 openai 包，请运行: pip install openai")
        except Exception as e:
            logger.error(f"OpenAI 客户端初始化失败: {e}")

    def is_available(self) -> bool:
        """检查LLM是否可用"""
        return self.client is not None

    def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2000, timeout: int = 180) -> Optional[str]:
        """
        调用 LLM 完成文本生成

        Args:
            prompt: 提示词
            temperature: 温度参数，越高越随机
            max_tokens: 最大生成token数
            timeout: 超时时间（秒）

        Returns:
            生成的文本，失败返回None
        """
        if not self.is_available():
            logger.error("LLM不可用，无法执行推理")
            return None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个Linux内核代码分析专家，擅长理解C代码的调用关系。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )

            result = response.choices[0].message.content
            logger.debug(f"LLM推理成功，生成 {len(result)} 字符")
            return result

        except Exception as e:
            logger.error(f"LLM推理失败: {e}")
            return None

    def analyze_code_relationship(
        self,
        func_a: str,
        func_b: str,
        code_a: str,
        code_b: str,
        context: Dict[str, Any]
    ) -> Optional[Dict]:
        """
        使用 LLM 分析两个函数之间的调用关系

        Args:
            func_a: 函数A名称
            func_b: 函数B名称
            code_a: 函数A代码
            code_b: 函数B代码
            context: 其他上下文信息

        Returns:
            分析结果字典，包含 bridge_type, confidence, explanation 等字段
        """
        if not self.is_available():
            return None

        prompt = self._build_relationship_analysis_prompt(
            func_a, func_b, code_a, code_b, context
        )

        response_text = self.complete(prompt, temperature=0.3)
        if not response_text:
            return None

        # 解析 JSON 响应
        try:
            import json
            # 去除可能的 markdown 代码块标记
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]

            result = json.loads(response_text.strip())
            return result

        except Exception as e:
            logger.error(f"解析LLM响应失败: {e}")
            logger.debug(f"原始响应: {response_text}")
            return None

    def _build_relationship_analysis_prompt(
        self,
        func_a: str,
        func_b: str,
        code_a: str,
        code_b: str,
        context: Dict[str, Any]
    ) -> str:
        """构建关系分析提示词"""
        prompt = f"""# 任务：分析Linux内核函数调用关系

## 背景
在追踪调用链时，我们发现函数A和函数B之间缺少直接的CALLS关系。
需要分析它们之间可能存在的间接调用机制。

## 函数A: {func_a}
```c
{code_a[:800] if code_a else "代码未找到"}
```

## 函数B: {func_b}
```c
{code_b[:800] if code_b else "代码未找到"}
```

## 上下文信息
- 函数A调用的函数: {', '.join(context.get('callees_a', [])[:10])}
- 调用函数B的函数: {', '.join(context.get('callers_b', [])[:10])}
- 函数A相关的结构体: {', '.join(context.get('related_structs_a', [])[:5])}
- 函数B相关的结构体: {', '.join(context.get('related_structs_b', [])[:5])}

## 分析目标
请分析函数A和函数B之间可能存在的间接调用机制，包括：

1. **异步调用**
   - 工作队列 (work_struct, delayed_work)
   - 定时器 (timer_list)
   - 延迟执行 (deferred work)

2. **函数指针/回调**
   - 操作表 (ops table)
   - 回调函数注册
   - 虚函数表

3. **事件驱动**
   - 中断处理
   - 事件通知
   - 信号/消息

4. **其他机制**
   - 内核线程
   - 任务队列
   - 其他间接调用方式

## 输出要求
请返回JSON格式的分析结果（不要包含其他文字说明）：

```json
{{
    "bridge_type": "async|function_pointer|callback|event|unknown",
    "bridge_entity": "具体的桥接实体名称",
    "confidence": 0.0-1.0,
    "explanation": "推理依据和关键代码线索",
    "key_code_patterns": ["关键的代码模式或标识符"]
}}
```

注意：
- bridge_type 必须是上述类型之一
- confidence 范围 0.0-1.0，表示推理的置信度
- explanation 要具体说明从代码中看到的证据
- 如果确实无法找到关联，confidence 应该很低（<0.3）
"""
        return prompt
