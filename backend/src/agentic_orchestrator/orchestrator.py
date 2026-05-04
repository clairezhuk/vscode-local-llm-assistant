import re
from src.engine.llm import LLMEngine
from src.context_manager.manager import ContextManager
from src.executor.tools import ToolExecutor

class Orchestrator:
    def __init__(self):
        self.engine = LLMEngine()
        self.context_manager = ContextManager()
        self.executor = ToolExecutor()

    def classify_intent(self, query: str) -> int:
        prompt = f"<|im_start|>system\nYou are a router. Analyze the user query.\nReturn ONLY '1' if they ask a question or want an explanation.\nReturn ONLY '2' if they ask you to write a script or function.\nReturn ONLY '3' if they ask to run a terminal command (like pip, git, npm, conda).\n<|im_end|>\n<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
        res = self.engine.generate(prompt, max_tokens=5).strip()
        if "3" in res: return 3
        if "2" in res: return 2
        return 1

    def _extract_code_block(self, text: str) -> str:
        match = re.search(r'```(?:bash|sh|cmd|powershell|markdown|python)?\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.replace("`", "").strip()

    def process_chat(self, query: str, context: dict) -> str:
        intent = self.classify_intent(query)
        code_ctx = context.get("active_file_content", "")

        if intent == 2:
            sys_prompt = "You are a coding assistant. Write ONLY the requested code inside a markdown block. Do not add any conversational text."
        elif intent == 3:
            sys_prompt = "You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block. Do not explain anything."
        else:
            sys_prompt = "You are a helpful assistant. Explain clearly and provide examples if needed."

        prompt = self.context_manager.format_prompt(sys_prompt, query, code_ctx)
        action = self.engine.generate(prompt, max_tokens=1024)

        if intent == 3:
            clean_cmd = self._extract_code_block(action)
            if len(clean_cmd) < 150 and "\n" not in clean_cmd:
                obs = self.executor.execute_command(clean_cmd)
                action += f"\n\n**Terminal Execution:** `{clean_cmd}`\n**Result:**\n```\n{obs}\n```"
            else:
                 action += f"\n\n*(Command execution blocked due to invalid formatting)*"

        self.context_manager.add_message("user", query)
        self.context_manager.add_message("assistant", action)
        
        return action

    def process_completion(self, prompt_text: str) -> str:
        prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
        return self.engine.generate(prompt, max_tokens=64, stop=["<|file_separator|>", "<|fim_prefix|>", "<|im_end|>", "\n\n"])