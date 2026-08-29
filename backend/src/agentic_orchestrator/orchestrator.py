import asyncio
import json
import re
from .reasoning import ReasoningEngine
from .validator import Validator
from .prompts import PromptLibrary as PrLib
from ..context_manager.manager import ContextManager
from ..context_manager.file_processor import FileProcessor
from src.engine.llm import LLMEngine

class Orchestrator:
    def __init__(self, max_retries: int = 3):
        self.engine = LLMEngine()
        self.context_mgr = ContextManager()
        self.file_proc = FileProcessor()
        self.validator = Validator()
        self.pending_command = None
        self.workspace_path = None
        self.lock = asyncio.Lock()
        self.reasoner = ReasoningEngine(self.engine, self.validator, self.lock)

    def preprocess_query(self, query: str) -> str:
        prompt = f"<|im_start|>system\n{PrLib.PREPROCESS_QUERY}<|im_end|>\n" \
                 f"<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
        
        try:
            res = self.engine.generate(prompt, max_tokens=128)["text"].strip()
            if "```" in res or "def " in res:
                return query
            return res if res else query
        except:
            return query

    async def process_chat(self, raw_query: str, context: dict):
        intent = context.get("intent", 1)
        mode = context.get("mode", "fast")
        attached_files = context.get("attached_files", [])
        self.workspace_path = context.get("workspace_path")

        clean_query = self.preprocess_query(raw_query)

        context_parts = []
        if self.workspace_path:
            context_parts.append(f"Current Workspace: {self.workspace_path}")
        
        file_ctx = self.file_proc.process_files(attached_files, self.engine)
        if file_ctx.strip():
            context_parts.append(f"### ATTACHED_FILES_CONTEXT ###\n{file_ctx}\n##############################")
        
        full_ctx = "\n".join(context_parts)

        # Goal Analysis
        goal_prompt = f"<|im_start|>system\n{PrLib.GOAL_ANALYSIS}<|im_end|>\n" \
                      f"<|im_start|>user\nContext:\n{full_ctx}\nTask: {clean_query}<|im_end|>\n<|im_start|>assistant\n"
        
        goal_res = await asyncio.to_thread(self.engine.generate, goal_prompt, max_tokens=30)
        goal = goal_res["text"].strip()

        #  ReasoningEngine
        async for chunk in self.reasoner.execute(mode, clean_query, full_ctx, goal, intent, self.workspace_path):
            if "command_proposal" in chunk:
                data = json.loads(chunk)
                self.pending_command = {"cmd": data["command"], "cwd": self.workspace_path}
            
            yield chunk

    def execute_confirmed(self):
        if not self.pending_command:
            return "No command to execute."
        from src.executor.tools import ToolExecutor
        executor = ToolExecutor()
        res = executor.execute_command(self.pending_command["cmd"], cwd=self.pending_command["cwd"])
        self.pending_command = None
        return res

    def reject_command(self):
        self.pending_command = None
        return "Command rejected."

    async def process_completion(self, prompt_text: str) -> dict:
            prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
            async with self.lock:
                result = await asyncio.to_thread(self.engine.generate, prompt, max_tokens=32, stop=["<|im_end|>", "\n\n"])
            return result