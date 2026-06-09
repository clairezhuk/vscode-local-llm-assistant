import re
import ast
import json
import asyncio
from src.engine.llm import LLMEngine
from src.context_manager.manager import ContextManager
from src.executor.tools import ToolExecutor
from src.context_manager.file_processor import FileProcessor
from src.agentic_orchestrator.planner import TaskPlanner
import asyncio

class Orchestrator:
    def __init__(self, max_retries: int = 3):
        self.engine = LLMEngine()
        self.context_manager = ContextManager()
        self.executor = ToolExecutor()
        self.file_processor = FileProcessor()
        self.planner = TaskPlanner(self.engine)
        self.pending_command = None
        self.workspace_path = None
        self.max_retries = max_retries
        self.lock = asyncio.Lock()

    def preprocess_query(self, query: str) -> str:
        sys_prompt = (
            "You are a strict translation and text-normalization API. "
            "Your ONLY job is to translate the text to English and fix clear spelling typos. "
            "CRITICAL: Preserve all technical terms, algorithm names (e.g., 'Linear Search', 'Bubble Sort'), "
            "and code-like identifiers (e.g., function names, variables) exactly as they are. "
            "DO NOT attempt to improve the logic or rewrite the query. "
            "If the text is already correct English, return it unchanged. "
            "Output ONLY the raw processed string."
        )
        prompt = f"<|im_start|>system\n{sys_prompt}<|im_end|>\n<|im_start|>user\nTranslate:\n[[[{query}]]]<|im_end|>\n<|im_start|>assistant\n"        
        res = self.engine.generate(prompt, max_tokens=128)["text"].strip()
        if "```" in res or "def " in res or len(res) > len(query) * 3 + 50:
            print(" [Orchestrator] Warning: Preprocessor tried to solve the task. Using original query.")
            return query
        
        res = res.replace("[[[", "").replace("]]]", "").strip()
        print(f" [Orchestrator] Translated/Fixed: '{query}' -> '{res}'")
        return res

    def _extract_code(self, text):
        blocks = re.findall(r'```(?:\w+)?\s*(.*?)\s*```', text, re.DOTALL)      
        if blocks:
            code = blocks[-1]
        else:
            code = text.strip()
        noise_patterns = [
            r'^\s*#?\s*Step\s*\d+:.*$',      
            r'^\s*#?\s*Attempt\s*\d+:.*$',   
            r'^\s*---.*$',                   
            r'^\s*###.*$',                   
            r'^.*Code only.*$',              
            r'^.*Assembling.*$'             
        ]       
        lines = code.split('\n')
        clean_lines = []
        for line in lines:
            if any(re.match(pattern, line, re.IGNORECASE) for pattern in noise_patterns):
                continue
            clean_lines.append(line)          
        return '\n'.join(clean_lines).strip()

    def execute_confirmed(self):
        if not self.pending_command:
            return "No command to execute."
        cmd_data = self.pending_command
        res = self.executor.execute_command(cmd_data["cmd"], cwd=cmd_data["cwd"])
        self.pending_command = None
        return res
    
    def reject_command(self):
        self.pending_command = None
        return "Command rejected by user."
    
    def _static_code_check(self, code: str) -> str:
        if not code: return "Empty code."
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"SyntaxError: {e}"
        called_funcs = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        defined = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names: imported.add(n.name)
            elif isinstance(node, ast.ImportFrom):
                for n in node.names: imported.add(n.name)

        builtins = set(__builtins__.keys()) | {"print", "len", "range", "int", "str", "list", "dict", "sum", "max", "min"}
        common_libs = {"math", "os", "sys", "json", "re", "datetime", "requests", "np", "pd", "plt", "torch"}
        
        for func in called_funcs:
            if func not in defined and func not in builtins and func not in imported:
                if func in ["gcd", "sqrt", "sin", "cos", "floor"]:
                    return f"Missing 'import math' for {func}."
                return f"NameError: '{func}' is not defined or imported."

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('__'): continue
                has_ret = any(isinstance(child, (ast.Return, ast.Yield)) for child in ast.walk(node))
                if not has_ret:
                    return f"Function '{node.name}' might need a 'return' statement."

        return ""
    
    async def _ask_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 512, temp=0.2):
        full_prompt = f"<|im_start|>system\n{system_prompt}. BE BRIEF. DO NOT REPEAT INSTRUCTIONS. IMPORTANT: Focus ONLY on the user's query. Ignore workspace files unless they are explicitly mentioned in the query.<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        async with self.lock:
            res = await asyncio.to_thread(self.engine.generate, full_prompt, max_tokens=max_tokens, temp=temp)
        return res["text"].strip()
    
    async def process_chat(self, raw_query: str, context: dict):
        intent = context.get("intent", 1) 
        mode = context.get("mode", "fast") 
        attached_files = context.get("attached_files", [])
        workspace_path = context.get("workspace_path")
        context_parts = []
        if workspace_path:
            context_parts.append(f"Current Workspace: {workspace_path}")
        if attached_files:
            # --- START OF FILE [filename] ---
            # [content]
            # --- END OF FILE ---
            file_ctx = self.file_processor.process_files(attached_files, self.engine)
            if file_ctx.strip():
                context_parts.append("### ATTACHED_FILES_CONTEXT ###")
                context_parts.append(file_ctx)
                context_parts.append("##############################")

        full_ctx = "\n".join(context_parts) if context_parts else ""
        prep_query = self.preprocess_query(raw_query)
        if attached_files:
            print(f" [Orchestrator] Processing with {len(attached_files)} files in context.")
        else:
            print(" [Orchestrator] Processing without file context.")

        if mode == "fast":
            async for chunk in self._run_fast_mode(prep_query, full_ctx, intent):
                yield chunk
        else:
            async for chunk in self._run_thinking_mode(prep_query, full_ctx, intent, workspace_path):
                yield chunk


    async def _run_fast_mode(self, query: str, context: str, intent: int):
        yield json.dumps({"type": "status", "content": "Fast processing..."}) + "\n"
        sys_prompts = {
            1: "You are a helpful assistant. Explain clearly. Do not run commands.",
            2: "You are a coding assistant. Use Python unless specified otherwise. \nWrite ONLY the code inside a markdown block. All code must be self-contained and use 'return'.",
            3: r"You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block. No explanations. NEVER hardcode absolute paths like 'C:\Users\...' in the code. Always use relative paths or function parameters."
            }
        prompt = self.context_manager.format_prompt(sys_prompts[intent], query, context)
        
        yield json.dumps({"type": "start_content"}) + "\n"
        full_text = ""
        for token in self.engine.generate_stream(prompt):
            full_text += token
            yield json.dumps({"type": "chunk", "content": token}) + "\n"
        if intent == 3:
            cmd = self._extract_code(full_text)
            self.pending_command = {"cmd": cmd, "cwd": getattr(self, 'workspace_path', None)}
            yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"

    async def _run_thinking_mode(self, query: str, context: str, intent: int, workspace: str):
        attempts = 0
        critique = ""
        success = False
        self.workspace_path = workspace

        yield json.dumps({"type": "status", "content": "Analyzing goal..."}) + "\n"
        goal_info = await self._ask_llm("Core goal in 5 words", query, max_tokens=50)
        yield json.dumps({"type": "status", "content": f"Goal: {goal_info}"}) + "\n"
        yield json.dumps({"type": "start_content"}) + "\n"

        while attempts < self.max_retries and not success:
            attempts += 1
            yield json.dumps({"type": "status", "content": f"Cycle {attempts}/{self.max_retries}..."}) + "\n"

            separator = f"\n\n---\n### Attempt {attempts}\n"
            yield json.dumps({"type": "chunk", "content": separator}) + "\n"

            if intent == 1: # LEARN
                exec_prompt = f"Goal: {goal_info}. {critique}\nProvide a concise, expert answer. Focus on facts."
                prompt = self.context_manager.format_prompt("Technical Expert", exec_prompt, context)
                
                full_ans = ""
                async with self.lock:
                    for token in self.engine.generate_stream(prompt, temp=0.3):
                        full_ans += token
                        yield json.dumps({"type": "chunk", "content": token}) + "\n"
                
                verify_prompt = f"Check for: 1. Hallucinations 2. Logic errors. If OK, output 'CLEAR'. Else, describe error.\nAns: {full_ans[:300]}"
                verify = await self._ask_llm("Reviewer", verify_prompt, max_tokens=50)
                if "CLEAR" in verify.upper(): success = True
                else: critique = f"Improve response: {verify}"

            elif intent == 3: # TERMINAL
                cmd_prompt = f"Goal: {goal_info}. {critique} Generate ONLY terminal command."\
                    r"NEVER hardcode absolute paths like 'C:\Users\...' in the code. Always use relative " \
                    "paths or function parameters. IMPORTANT: Use relative paths for file operations. " \
                    r"The environment is Linux-based Docker."
                cmd_raw = await self._ask_llm("Terminal expert", cmd_prompt)
                cmd = self._extract_code(cmd_raw)
                
                verify = await self._ask_llm("Safe? YES/NO", f"Cmd: {cmd}", max_tokens=50, temp=0.0)
                if "YES" in verify.upper():
                    self.pending_command = {"cmd": cmd, "cwd": workspace}
                    yield json.dumps({"type": "chunk", "content": f"Proposed command: `{cmd}`"}) + "\n"
                    yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"
                    success = True
                else: critique = f"Rejected: {verify}"

            elif intent == 2: # CODE
                plan = self.planner.generate_plan(f"Goal: {goal_info}", context)
                final_code = ""
                target_func = re.search(r'([a-zA-Z0-9_]+)\(', query)
                func_hint = f"Use exactly the name '{target_func.group(1)}' and argument order from the Task." if target_func else ""
                if len(plan) <= 1:
                    yield json.dumps({"type": "status", "content": "Generating solution..."}) + "\n"
                    res = await self._ask_llm("Senior Python Developer", 
                        f"Task: {query}. {func_hint}\nWrite ONLY the implementation. {critique}", 
                        temp=0.1)
                    final_code = self._extract_code(res)
                else:
                    yield json.dumps({"type": "plan", "content": plan}) + "\n"
                    fragments = []
                    for step in plan:
                        res = await self._ask_llm("Coder", f"Goal: {goal_info}. Step: {step}. Code only." \
                            "Your output must be PURE code. DO NOT include comments like 'Step 1' or 'Final implementation'. " \
                            "If I see the word 'Step' inside the code, it's a failure.",
                            max_tokens=400, temp=0.1)
                        fragments.append(self._extract_code(res))
                    yield json.dumps({"type": "status", "content": "Assembling..."}) + "\n"
                    assembly_prompt = (
                        f"Task: {query}. Below is a rough draft consisting of code fragments. "
                        f"Your job is to refine these fragments into a single, clean, and fully functional Python file. "
                        f"Fix any missing imports, logical inconsistencies, or syntax errors. "
                        f"When using libraries, always use standard aliases: import numpy as np, import pandas as pd, "
                        f"import torch.nn as nn, import matplotlib.pyplot as plt. "
                        f"Your function MUST be named exactly as requested. Check the task description again before finalizing. "
                        f"{func_hint}\n\n"
                        "IMPORTANT: Use relative paths for file operations. The environment is Linux-based Docker."
                        f"Draft fragments:\n{fragments}\n\n"
                        f"Final code only (no explanations):"
                    )
                    final_code_raw = await self._ask_llm("Python Architect", assembly_prompt, max_tokens=1024, temp=0.1)
                    final_code = self._extract_code(final_code_raw)
                
                yield json.dumps({"type": "chunk", "content": f"\n```python\n{final_code}\n```\n"}) + "\n"
                err = self._static_code_check(final_code)
                if err:
                    critique = f"Fix this: {err}"
                else:
                    logic_check = await self._ask_llm("Reviewer", f"Is this code missing imports (like math or sys) or logic for: {goal_info}? If perfect, output 'CLEAR'.", max_tokens=100)
                    if "CLEAR" in logic_check.upper(): success = True
                    else: critique = f"Logic fix: {logic_check}"

        if not success:
            yield json.dumps({"type": "chunk", "content": "\n\n> ⚠️ **AI Warning:** Verification failed after max retries."}) + "\n"
        yield json.dumps({"type": "end"}) + "\n"


    async def process_completion(self, prompt_text: str) -> dict:
        prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
        async with self.lock:
            result = await asyncio.to_thread(self.engine.generate, prompt, max_tokens=32, stop=["<|im_end|>", "\n\n"])
        return result
