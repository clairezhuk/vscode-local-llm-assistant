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
        prompt = f"<|im_start|>system\nClassify intent. Reply ONLY with digit: 1 (Chat/Explain), 2 (Write Code), 3 (Terminal Command).<|im_end|>\n<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
        res = self.engine.generate(prompt, max_tokens=2).strip()
        if "2" in res: return 2
        if "3" in res: return 3
        return 1

    def process_chat(self, query: str, context: dict) -> str:
        intent = self.classify_intent(query)
        code_ctx = context.get("active_file_content", "")

        if intent == 2:
            sys_prompt = "You are an expert coder. Write ONLY the code in markdown blocks. No explanations."
        elif intent == 3:
            sys_prompt = "You are a terminal assistant. Write ONLY the exact terminal command. No formatting, no markdown, no explanations."
        else:
            sys_prompt = "You are a helpful assistant. Answer briefly."

        prompt = self.context_manager.format_prompt(sys_prompt, query, code_ctx)
        action = self.engine.generate(prompt, max_tokens=1024)

        if intent == 3:
            clean_cmd = action.replace("`", "").strip()
            obs = self.executor.execute_command(clean_cmd)
            action += f"\n\n**Terminal Output:**\n```\n{obs}\n```"

        self.context_manager.add_message("user", query)
        self.context_manager.add_message("assistant", action)
        
        return action

    def process_completion(self, prompt_text: str) -> str:
        prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
        return self.engine.generate(prompt, max_tokens=64, stop=["<|file_separator|>", "<|fim_prefix|>", "<|im_end|>", "\n\n"])