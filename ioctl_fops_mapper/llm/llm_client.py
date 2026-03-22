"""
统一的 LLM 客户端（通用接口）
支持多种后端（OpenAI API、Ollama 等）
"""
import json
from typing import Optional, Dict, Any, List
from loguru import logger
from .backends import OpenAIBackend, LocalServerBackend, OllamaBackend, BaseLLMBackend


class LLMClient:
    """
    统一的 LLM 客户端

    示例用法：
        # OpenAI API / 兼容服务
        client = LLMClient(backend='openai', model='gpt-4o-mini',
                          base_url='http://...')

        # Ollama 本地部署
        client = LLMClient(backend='ollama', host='http://localhost:11434',
                          model='qwen3:4b')

        # 调用
        result = client.complete("分析这段C代码...")
    """

    def __init__(self, backend: str = 'openai', **backend_config):
        self.backend_type = backend
        self.backend: Optional[BaseLLMBackend] = None

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
        return self.backend is not None and self.backend.is_available()

    def get_backend_info(self) -> str:
        if self.backend:
            return self.backend.get_backend_name()
        return "未初始化"

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 180,
        **kwargs
    ) -> Optional[str]:
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
        system_prompt: str = "你是一个Linux内核代码分析专家，擅长理解C代码结构和驱动模型。",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 180
    ) -> Optional[str]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        return self.chat_completion(messages, temperature, max_tokens, timeout)

    def _parse_json_response(self, response: str) -> Optional[dict]:
        """从 LLM 返回中解析 JSON（处理 markdown 代码块、尾随逗号、多余文本等）"""
        import re
        if not response:
            return None
        content = response.strip()

        # 去除 markdown 代码块
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()

        # 1. 直接解析
        try:
            return json.loads(content)
        except Exception:
            pass

        # 2. 提取第一个 {...} 块再解析
        m = re.search(r'\{[\s\S]*\}', content)
        if not m:
            logger.error("JSON 解析失败: 未找到 JSON 对象")
            return None
        chunk = m.group()
        try:
            return json.loads(chunk)
        except Exception:
            pass

        # 3. 清理常见问题后重试：尾随逗号、单引号键值
        cleaned = re.sub(r',\s*([}\]])', r'\1', chunk)   # 去尾随逗号
        cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned) # 单引号→双引号（简单情形）
        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"JSON 解析失败: {e}\n原始片段: {chunk[:200]}")
            return None

    def resolve_ioctl_handler(
        self,
        caller_source: str,
        call_line: Optional[int],
        caller_file: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        单轮 LLM 调用：给定 ioctl() 调用点源码 + 候选 file_operations 列表，
        判断该 ioctl() 调用会走到哪个驱动的 file_operations。

        核心逻辑：
        - ioctl() 的路由是由 fd 对应的 file_operations.unlocked_ioctl 决定的
        - LLM 需要先判断 fd 是从哪个设备/驱动 open() 来的
        - 再从候选 file_operations 列表中找到对应那个驱动的 fops
        - handler 是该 fops 的 unlocked_ioctl 字段

        Args:
            caller_source:  ioctl() 调用点周围的源码上下文
            call_line:      ioctl() 所在行号
            caller_file:    调用文件路径
            candidates:     候选列表，每项含 {handler_func, fops_var, source_file, driver_dir}

        Returns:
            {
                "selected_index": 0~N-1（candidates 下标），无匹配为 -1,
                "confidence":     0~10,
                "reasoning":      "选择理由"
            }
            失败返回 None
        """
        if not self.is_available() or not candidates:
            return None

        # 候选以 fops 为主体展示，handler_func 作为补充信息
        candidates_str = json.dumps(
            [{"index":      i,
              "fops_var":   c.get("fops_var"),
              "driver_dir": c.get("driver_dir"),
              "source_file": c.get("source_file"),
              "unlocked_ioctl_handler": c.get("handler_func")}
             for i, c in enumerate(candidates)],
            ensure_ascii=False, indent=2
        )
        call_hint = f"（第 {call_line} 行是 ioctl() 调用）" if call_line else ""

        prompt = f"""你是 Linux 内核专家。以下是一段包含 ioctl() 调用的 C 代码{call_hint}。

ioctl() 的执行路径由 fd 背后的 file_operations 结构体决定：
  fd = open("/dev/xxx", ...) → 内核根据设备类型找到对应驱动的 file_operations
  → 调用 file_operations.unlocked_ioctl

判断步骤（优先级从高到低）：
1. **ioctl 命令宏前缀**（最强信号）：命令宏如 FOO_IOC_BAR 中的 FOO_IOC 前缀
   直接指向定义这些宏的驱动/子系统，应在候选 fops 的 driver_dir 或 fops_var 中寻找对应
2. **fd 来源**：open() 打开的设备路径（如 /dev/gb-fw-mgmt-0 → greybus fw-mgmt 驱动）
3. **调用文件目录**：调用文件所在目录暗示其操作的子系统

调用文件路径：{caller_file}

代码上下文：
```c
{caller_source[:3000]}
```

候选 file_operations 列表（每项来自内核源码中 .unlocked_ioctl 的注册）：
{candidates_str}

注意：若候选列表中确实不存在匹配的 fops（相关驱动不在候选中），请直接填 -1，
不要强行选一个不相关的。

以 JSON 格式回答（不要其他说明）：
{{
  "selected_index": 0到{len(candidates)-1}的整数，无合适匹配填 -1,
  "confidence": 0到10的整数,
  "reasoning": "先说命令宏前缀指向哪个子系统，再说 fd 来源，最后说为何选或不选某个 fops"
}}"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="你是一个 Linux 内核代码分析专家，擅长 ioctl 调用路径分析。",
                temperature=0.1,
                max_tokens=400,
                timeout=120,
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"resolve_ioctl_handler 失败: {e}")
            return None

    def analyze_ioctl_context(
        self,
        code_context: str,
        file_path: str = "",
        line_no: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        分析 ioctl() 调用点的代码上下文，识别所属设备/驱动/子系统

        Args:
            code_context: ioctl() 调用点周围的代码（约 60 行）
            file_path: 调用点所在文件路径（提供给 LLM 作参考）
            line_no: ioctl() 所在行号

        Returns:
            {
                "device_path": "/dev/xxx 或设备描述",
                "driver_module": "模块名，如 mmc、alsa、usb",
                "fd_source": "fd 来自哪里（如 open() 返回值）",
                "confidence": 0-10,
                "reasoning": "推理说明"
            }
            失败返回 None
        """
        if not self.is_available():
            return None

        file_hint = f"文件路径: {file_path}\n行号: {line_no}\n\n" if file_path else ""

        prompt = f"""{file_hint}以下是包含 ioctl() 调用的 C 代码片段。请分析这个 ioctl() 调用属于哪个设备或内核子系统。

代码上下文：
```c
{code_context}
```

请回答以下问题：
1. 这个 ioctl() 操作的是什么设备或内核子系统？（查找 /dev/ 路径、设备类型等线索）
2. `fd`（或对应的文件描述符变量）是从哪里获得的？（查找 open() 调用或函数参数）
3. 这属于哪个 Linux 内核驱动模块？（如 mmc、alsa、usb、drm、v4l2、i2c 等）

以 JSON 格式回答（不要其他说明）：
{{
  "device_path": "设备路径或描述，如 /dev/mmc0，若不确定写 null",
  "driver_module": "驱动模块名，如 mmc，若不确定写 null",
  "fd_source": "fd 的来源描述，如 open('/dev/xxx')",
  "confidence": 0到10的整数,
  "reasoning": "简短推理说明"
}}"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="你是一个 Linux 内核代码分析专家。",
                temperature=0.2,
                max_tokens=600,
                timeout=120
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"analyze_ioctl_context 失败: {e}")
            return None

    def match_fops_candidate(
        self,
        ioctl_analysis: Dict[str, Any],
        fops_candidates: List[Dict[str, Any]],
        code_context: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        从候选 file_operations 列表中，选出与当前 ioctl 调用最匹配的那个

        Args:
            ioctl_analysis: analyze_ioctl_context() 的返回值
            fops_candidates: fops_indexer 建立的候选列表，每项包含
                {handler_func, fops_var, source_file, driver_hint}
            code_context: ioctl 调用点的代码上下文（可选，提供更多线索）

        Returns:
            最匹配的候选项（从 fops_candidates 中选一个），附加 match_confidence 字段
            若无合适匹配返回 None
        """
        if not self.is_available() or not fops_candidates:
            return None

        candidates_json = json.dumps(fops_candidates, ensure_ascii=False, indent=2)
        analysis_json = json.dumps(ioctl_analysis, ensure_ascii=False, indent=2)

        code_section = ""
        if code_context:
            code_section = f"\n\nioctl 调用点代码上下文（供参考）：\n```c\n{code_context[:800]}\n```"

        prompt = f"""根据对 ioctl() 调用的分析结果，从候选的 file_operations 列表中选出最匹配的一个。

ioctl 调用分析：
{analysis_json}
{code_section}

候选 file_operations 列表（已从源码/图谱中找到的 .unlocked_ioctl 注册项）：
{candidates_json}

请选出最匹配的候选，依据：驱动模块名、源文件路径、handler 函数名等。

以 JSON 格式返回（不要其他说明）：
{{
  "selected_index": 0到{len(fops_candidates)-1}的整数（候选列表中的下标），若无合适匹配填 -1,
  "match_confidence": 0到10的整数,
  "reasoning": "选择理由"
}}"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="你是一个 Linux 内核代码分析专家。",
                temperature=0.2,
                max_tokens=400,
                timeout=120
            )
            result = self._parse_json_response(response)
            if not result:
                return None

            idx = result.get("selected_index", -1)
            if idx < 0 or idx >= len(fops_candidates):
                return None

            matched = dict(fops_candidates[idx])
            matched["match_confidence"] = result.get("match_confidence", 0)
            matched["match_reasoning"] = result.get("reasoning", "")
            return matched

        except Exception as e:
            logger.error(f"match_fops_candidate 失败: {e}")
            return None

    def analyze_ioctl_for_retrieval(
        self,
        caller_source: str,
        call_line: Optional[int],
        caller_file: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Phase 1：不提供候选，让 LLM 从代码上下文推断子系统/驱动方向，
        返回的结果用于后续智能候选召回（关键词过滤 + 名字猜测）。

        Returns:
            {
                "subsystem":        "nitro_enclaves",
                "driver_dir_hints": ["nitro_enclaves", "virt"],
                "fops_name_guess":  "ne_fops",   # 或 null
                "confidence":       0~10,
                "reasoning":        "..."
            }
            失败返回 None
        """
        if not self.is_available():
            return None

        call_hint = f"（第 {call_line} 行是 ioctl() 调用）" if call_line else ""

        prompt = f"""你是 Linux 内核专家。以下是一段包含 ioctl() 调用的 C 代码{call_hint}。

调用文件路径：{caller_file}

代码上下文：
```c
{caller_source[:3000]}
```

请分析该 ioctl() 调用属于哪个 Linux 内核子系统/驱动，以便在内核源码中定位对应的 file_operations 结构体。

分析步骤（优先级从高到低）：
1. **ioctl 命令宏前缀**：命令宏（如 NE_CREATE_VM、KVM_RUN、VHOST_SET_MEM_TABLE）的前缀直接指向所属子系统
2. **fd 来源**：open() 打开的设备路径（如 /dev/nitro_enclaves → nitro_enclaves 驱动）
3. **调用文件目录**：caller 文件所在目录（如 samples/nitro_enclaves/ → nitro_enclaves）

以 JSON 格式回答（不要其他说明）：
{{
  "subsystem": "最可能的子系统名（单个），如 nitro_enclaves、kvm、drm、vhost",
  "driver_dir_hints": ["用于过滤 fops 源文件路径的关键词，3个以内，如 nitro_enclaves、virt、kvm"],
  "fops_name_guess": "猜测的 fops 变量名，如 ne_fops、kvm_fops，不确定填 null",
  "confidence": 0到10的整数,
  "reasoning": "简短推理"
}}"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="你是一个 Linux 内核代码分析专家，擅长 ioctl 调用路径分析。",
                temperature=0.1,
                max_tokens=300,
                timeout=60,
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"analyze_ioctl_for_retrieval 失败: {e}")
            return None

    def select_fops_var(
        self,
        caller_source: str,
        call_line: Optional[int],
        caller_file: str,
        fops_candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        从候选 fops 变量列表中选出与当前 ioctl() 调用最匹配的那个。

        与 resolve_ioctl_handler 的区别：候选不包含 handler_func（因为 KG 可能
        没有提取到 ASSIGNED_TO 关系），只有 fops_var / source_file / driver_dir。
        选中后调用方再从源码提取 .unlocked_ioctl 字段。

        Args:
            caller_source:    ioctl() 调用点周围的源码上下文
            call_line:        ioctl() 所在行号
            caller_file:      调用文件路径
            fops_candidates:  候选列表，每项含 {fops_var, source_file, driver_dir}

        Returns:
            {
                "selected_index": 0~N-1，无匹配为 -1,
                "confidence":     0~10,
                "reasoning":      "选择理由"
            }
            失败返回 None
        """
        if not self.is_available() or not fops_candidates:
            return None

        candidates_str = json.dumps(
            [{"index":      i,
              "fops_var":   c.get("fops_var"),
              "driver_dir": c.get("driver_dir"),
              "source_file": c.get("source_file")}
             for i, c in enumerate(fops_candidates)],
            ensure_ascii=False, indent=2
        )
        call_hint = f"（第 {call_line} 行是 ioctl() 调用）" if call_line else ""

        prompt = f"""你是 Linux 内核专家。以下是一段包含 ioctl() 调用的 C 代码{call_hint}。

ioctl() 的执行路径由 fd 背后的 file_operations 结构体决定：
  fd = open("/dev/xxx", ...) → 内核根据设备类型找到对应驱动的 file_operations
  → 调用 file_operations.unlocked_ioctl

判断步骤（优先级从高到低）：
1. **ioctl 命令宏前缀**（最强信号）：命令宏如 FOO_IOC_BAR 中的 FOO_IOC 前缀
   直接指向定义这些宏的驱动/子系统，应在候选 fops 的 driver_dir 或 fops_var 中寻找对应
2. **fd 来源**：open() 打开的设备路径（如 /dev/gb-fw-mgmt-0 → greybus fw-mgmt 驱动）
3. **调用文件目录**：调用文件所在目录暗示其操作的子系统

调用文件路径：{caller_file}

代码上下文：
```c
{caller_source[:3000]}
```

候选 file_operations 变量列表（来自内核源码）：
{candidates_str}

注意：若候选列表中确实不存在匹配的 fops，请直接填 -1，不要强行选一个不相关的。

以 JSON 格式回答（不要其他说明）：
{{
  "selected_index": 0到{len(fops_candidates)-1}的整数，无合适匹配填 -1,
  "confidence": 0到10的整数,
  "reasoning": "先说命令宏前缀指向哪个子系统，再说 fd 来源，最后说为何选或不选某个 fops"
}}"""

        try:
            response = self.complete(
                prompt=prompt,
                system_prompt="你是一个 Linux 内核代码分析专家，擅长 ioctl 调用路径分析。",
                temperature=0.1,
                max_tokens=400,
                timeout=120,
            )
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"select_fops_var 失败: {e}")
            return None
