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
        """从 LLM 返回中解析 JSON（处理 markdown 代码块）"""
        if not response:
            return None
        content = response.strip()
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()
        try:
            return json.loads(content)
        except Exception as e:
            logger.error(f"JSON 解析失败: {e}")
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
