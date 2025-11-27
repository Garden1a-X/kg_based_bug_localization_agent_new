"""
统一的 LLM 客户端
支持多种后端（OpenAI API、本地服务器等）
"""
import json
from typing import Optional, Dict, Any, List
from loguru import logger
from .backends import OpenAIBackend, LocalServerBackend, OllamaBackend, BaseLLMBackend


class LLMClient:
    """
    统一的 LLM 客户端

    使用策略模式支持多种后端，提供统一的接口

    示例用法：
        # OpenAI API / 兼容服务
        client = LLMClient(backend='openai', model='gpt-4o-mini',
                          base_url='http://10.12.208.86:8502')

        # Ollama 本地部署
        client = LLMClient(backend='ollama', host='http://10.78.108.45:11434',
                          model='qwen3:4b-instruct-2507-fp16')

        # 本地服务器（未来）
        client = LLMClient(backend='local', server_url='http://localhost:8000')

        # 调用
        result = client.extract_async_parameter(caller_name, callee_name, source_code)
    """

    def __init__(
        self,
        backend: str = 'openai',
        **backend_config
    ):
        """
        初始化 LLM 客户端

        Args:
            backend: 后端类型 ('openai', 'local', 'ollama', 等)
            **backend_config: 后端特定的配置参数
                - OpenAI: api_key, base_url, model
                - Local: server_url, model
                - Ollama: host, model
        """
        self.backend_type = backend
        self.backend: Optional[BaseLLMBackend] = None

        # 创建后端实例
        if backend == 'openai':
            self.backend = OpenAIBackend(**backend_config)
        elif backend == 'local':
            self.backend = LocalServerBackend(**backend_config)
        elif backend == 'ollama':
            self.backend = OllamaBackend(**backend_config)
        else:
            raise ValueError(f"不支持的后端类型: {backend}")

        if not self.backend.is_available():
            logger.warning(f"LLM 后端 '{backend}' 初始化失败或不可用")

    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        return self.backend is not None and self.backend.is_available()

    def get_backend_info(self) -> str:
        """获取后端信息"""
        if self.backend:
            return self.backend.get_backend_name()
        return "未初始化"

    # ========== 通用接口 ==========

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 180,
        **kwargs
    ) -> Optional[str]:
        """
        通用的对话补全接口

        Args:
            messages: 消息列表 [{"role": "system/user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间
            **kwargs: 其他参数

        Returns:
            生成的文本
        """
        if not self.is_available():
            logger.error("LLM 不可用")
            return None

        return self.backend.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs
        )

    def complete(
        self,
        prompt: str,
        system_prompt: str = "你是一个Linux内核代码分析专家，擅长理解C代码的调用关系。",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 180
    ) -> Optional[str]:
        """
        简化的文本补全接口（兼容旧接口）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大token数
            timeout: 超时时间

        Returns:
            生成的文本
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        return self.chat_completion(messages, temperature, max_tokens, timeout)

    # ========== 专用方法 ==========

    def extract_async_parameter(
        self,
        caller_name: str,
        callee_name: str,
        caller_source: str
    ) -> Optional[str]:
        """
        提取异步调用的参数字段名

        用于分析 delayed work 模式：caller 调用 schedule_work/queue_work 等函数时，
        传入的 work_struct 字段名（如 &host->detect 中的 "detect"）

        Args:
            caller_name: 调用者函数名
            callee_name: 被调用的异步函数名（如 mmc_schedule_delayed_work）
            caller_source: 调用者源代码

        Returns:
            字段名（如 'detect'），失败返回 None
        """
        if not self.is_available():
            return None

        prompt = f"""分析以下C函数，找到它调用 {callee_name} 时传入的work参数。

函数名: {caller_name}
源代码:
```c
{caller_source}
```

任务：
找到调用 {callee_name}(...) 的代码行，提取第一个参数（通常是&var形式）。
如果参数是 &host->detect，则字段名是 detect。
如果参数是 &work，则字段名是 work。

返回JSON格式：
{{
  "found": true/false,
  "call_expression": "完整的调用表达式",
  "first_parameter": "第一个参数的完整形式（如 &host->detect）",
  "field_name": "提取的字段名（如 detect）"
}}

如果没找到调用，返回：
{{
  "found": false
}}

只返回JSON，不要其他说明。"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="You are a C code analyzer.",
                temperature=0.3,
                max_tokens=800,
                timeout=180
            )

            if not response:
                return None

            # 解析 JSON
            content = response.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            result = json.loads(content)

            if not result.get('found', False):
                return None

            field_name = result.get('field_name')
            return field_name

        except Exception as e:
            logger.error(f"LLM提取参数失败: {e}")
            return None

    def analyze_log(
        self,
        log_text: str,
        candidate_entries: list = None,
        user_context: dict = None
    ) -> Optional[Dict[str, Any]]:
        """
        分析错误日志，提取结构化信息

        Args:
            log_text: 错误日志文本
            candidate_entries: 候选入口函数列表（可选）
            user_context: 用户提供的上下文信息（可选），如 {'platform': 'rk3288', 'driver': 'dw_mci'}

        Returns:
            结构化的分析结果，包含置信度
        """
        if not self.is_available():
            return None

        # 构建候选入口部分
        candidates_section = ""
        if candidate_entries:
            candidates_section = f"""
## 候选入口函数
以下是可能的驱动入口函数（probe/init函数）：
{json.dumps(candidate_entries, indent=2, ensure_ascii=False)}

请从候选列表中选择最合适的入口函数。如果日志信息不足以确定具体是哪个驱动，请：
- 设置 start_confidence < 0.6
- 在 suggestions 中列出需要的额外信息
"""
        else:
            candidates_section = """
## 入口函数推断
没有提供候选入口列表，请根据日志内容推断最可能的驱动入口函数（通常是 *_probe, *_init 等）。
如果无法确定，设置 start_confidence < 0.6 并说明原因。
"""

        # 用户上下文
        context_section = ""
        if user_context:
            context_section = f"""
## 用户提供的额外信息
{json.dumps(user_context, indent=2, ensure_ascii=False)}
请结合这些信息进行分析。
"""
            logger.debug(f"用户上下文已添加到 prompt: {user_context}")
        else:
            logger.debug("未提供用户上下文")

        prompt = f"""你是一个Linux内核驱动错误分析专家。请分析以下错误日志并选择最合适的入口函数。

**重要原则：保守评估，宁可置信度低也不要过度自信。只有在有明确证据时才给出高置信度。**

{candidates_section}
{context_section}

## 错误日志
{log_text}

## 分析任务
1. 识别错误类型和错误码
2. 判断这是初始化错误还是运行时错误
3. **仔细检查日志中是否有明确的驱动类型线索**（如驱动名、特定函数名等）
4. 找出错误点函数（实际报错的位置）
5. 列出可能涉及的中间函数

## 入口选择和置信度评估（非常重要！）

**只有满足以下条件之一时，才能给出 confidence >= 0.6：**
1. ✅ 日志中明确提到了驱动名称（如 "dwmmc", "sdhci", "dw_mci" 等）
2. ✅ 用户提供了明确的平台或驱动信息（在用户上下文中）
3. ✅ 日志中包含该驱动的特有函数名（如 "dw_mci_execute_tuning" 明确指向 dw_mci 驱动）

**以下情况必须给出 confidence < 0.6：**
1. ❌ 日志仅提到通用的子系统名（如 "mmc", "usb"），没有具体驱动信息
2. ❌ 候选列表中有多个驱动都可能匹配
3. ❌ 只是基于猜测或经验，没有硬证据
4. ❌ 日志信息过于简单，无法确定具体驱动

**置信度标准（严格执行）：**
- **0.8-1.0**: 有**明确的硬证据**（日志中的驱动名、用户明确指定、特有函数名）
- **0.6-0.8**: 有**一定证据**（如日志中的特有函数可以推断出驱动类型）
- **0.4-0.6**: 有**弱证据**（如基于子系统名猜测，但不确定）
- **0.0-0.4**: **无法确定**（日志信息太少，无法判断）

**示例：**
- 日志："mmc0: tuning failed" + 候选:[dw_mci_probe, sdhci_probe] → confidence=0.3（无法确定是哪个驱动）
- 日志："dw_mci: tuning failed" → confidence=0.9（明确提到 dw_mci）
- 日志："mmc0: tuning failed" + 用户提供 platform="RK3288" → confidence=0.8（RK3288 用 dw_mci）
- 日志中有函数 "dw_mci_execute_tuning" → confidence=0.8（特有函数名）

## 输出格式
返回JSON格式（不要其他说明）：
{{
  "error_type": "错误类型描述",
  "error_code": 错误码（数字）,
  "start_entity": "起点函数名或null",
  "start_confidence": 0.3,
  "end_entity": "错误点函数名",
  "intermediate_entities": ["中间函数1", "中间函数2"],
  "reasoning": [
    "推理步骤1：检查日志是否明确提到驱动名 - 未提到",
    "推理步骤2：检查是否有特有函数 - 没有",
    "推理步骤3：结论 - 无法确定具体驱动，confidence=0.3"
  ],
  "need_more_info": true,
  "suggestions": ["硬件平台信息（如 RK3288）", "驱动类型（如 dw_mci, sdhci）"]
}}

**注意：如果无法确定入口，start_entity 可以设为候选列表中的某个作为建议，但 start_confidence 必须 < 0.6，need_more_info 必须为 true。**
"""

        # DEBUG: 保存 prompt 用于调试
        import os
        if os.environ.get('LLM_DEBUG_PROMPT'):
            with open('/tmp/llm_prompt_debug.txt', 'w', encoding='utf-8') as f:
                f.write(prompt)
            logger.info("已将 prompt 保存到 /tmp/llm_prompt_debug.txt")

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="你是一个Linux内核驱动错误分析专家。",
                temperature=0.3,
                max_tokens=1000,
                timeout=180
            )

            if not response:
                return None

            # 解析 JSON
            content = response.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            result = json.loads(content)
            return result

        except Exception as e:
            logger.error(f"LLM分析日志失败: {e}")
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
        分析两个函数之间的调用关系

        用于找出断裂调用链中的间接连接（函数指针、异步调用等）

        Args:
            func_a: 函数A名称
            func_b: 函数B名称
            code_a: 函数A代码
            code_b: 函数B代码
            context: 上下文信息

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

    def extract_function_pointer_fields(
        self,
        func_name: str,
        source_code: str
    ) -> List[str]:
        """
        提取函数中的函数指针调用字段

        用于分析类似 host->ops->execute_tuning() 这样的调用

        Args:
            func_name: 函数名
            source_code: 函数源代码

        Returns:
            字段名列表（如 ["execute_tuning", "init"]）
        """
        if not self.is_available():
            return []

        prompt = f"""分析以下C函数，找出所有函数指针调用的字段名。

函数名: {func_name}
源代码:
```c
{source_code}
```

任务：
找到所有形如 var->field() 或 var->ops->field() 的函数指针调用。
只提取最后的字段名（即实际被调用的函数指针名）。

示例：
- host->ops->execute_tuning() → 提取 "execute_tuning"
- card->init() → 提取 "init"
- device->driver->probe() → 提取 "probe"

返回JSON格式：
{{
  "fields": ["field1", "field2", ...]
}}

只返回JSON，不要其他说明。"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="You are an expert in C code analysis.",
                temperature=0.3,
                max_tokens=800,
                timeout=180
            )

            if not response:
                return []

            # 解析 JSON
            content = response.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            result = json.loads(content)
            return result.get('fields', [])

        except Exception as e:
            logger.error(f"LLM提取函数指针字段失败: {e}")
            return []

    # ========== 内部辅助方法 ==========

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
