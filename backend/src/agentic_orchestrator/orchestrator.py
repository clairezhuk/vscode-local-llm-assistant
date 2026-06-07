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
        sys_prompt = "You are a strict translation API. Your ONLY job is to translate the text to English and fix typos. DO NOT output greetings like 'Sure' or 'Here is'. Output ONLY the raw translated string."
        prompt = f"<|im_start|>system\n{sys_prompt}<|im_end|>\n<|im_start|>user\nTranslate:\n[[[{query}]]]<|im_end|>\n<|im_start|>assistant\n"        
        res = self.engine.generate(prompt, max_tokens=128)["text"].strip()
        if "```" in res or "def " in res or len(res) > len(query) * 3 + 50:
            print(" [Orchestrator] Warning: Preprocessor tried to solve the task. Using original query.")
            return query
        
        res = res.replace("[[[", "").replace("]]]", "").strip()
        print(f" [Orchestrator] Translated/Fixed: '{query}' -> '{res}'")
        return res

    def _extract_code(self, text):
        text = text.split('```')[1] if '```' in text else text
        for lang in ['python', 'bash', 'sh', 'javascript', 'typescript']:
            if text.lower().startswith(lang):
                text = text[len(lang):].strip()
        return text.strip().replace('`', '')

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
        if not code: return "No code block found."
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"SyntaxError: {e}"

        defined_funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        called_funcs = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        
        builtins = {"print", "len", "range", "int", "str", "list", "set", "dict", "enumerate", "type", "sum", "max", "min", "open", "abs", "any", "all", "hasattr", "getattr", "setattr"}
        missing = called_funcs - defined_funcs - builtins
        if missing:
            return f"NameError: You called undefined functions: {', '.join(missing)}. Please define them or import them."
            
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                has_return = any(isinstance(child, (ast.Return, ast.Yield)) for child in ast.walk(node))
                if not has_return:
                    return f"LogicError: Function '{node.name}' is missing a 'return' statement."

        return ""
    
    async def _ask_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 512):
        full_prompt = f"<|im_start|>system\n{system_prompt}. BE BRIEF. DO NOT REPEAT INSTRUCTIONS.<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        async with self.lock:
            res = await asyncio.to_thread(self.engine.generate, full_prompt, max_tokens=max_tokens)
        return res["text"].strip()
    
    async def process_chat(self, raw_query: str, context: dict):
        intent = context.get("intent", 1) 
        mode = context.get("mode", "fast") 
        attached_files = context.get("attached_files", [])
        workspace_path = context.get("workspace_path")

        file_ctx = self.file_processor.process_files(attached_files, self.engine) if attached_files else ""
        full_ctx = f"Workspace: {workspace_path}\nFiles Context: {file_ctx}\n"

        prep_query = self.preprocess_query(raw_query)
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
            2: "You are a coding assistant. \nWrite ONLY the code inside a markdown block. All code must be self-contained and use 'return'.",
            3: "You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block. No explanations."
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
        final_result = ""
        self.workspace_path = workspace

        # --- STEP 1: GOAL AND REQUAREMENTS ---
        yield json.dumps({"type": "status", "content": "Analyzing goal..."}) + "\n"
        goal_info = await self._ask_llm("Analyze user request core goal", query, max_tokens=100)
        goal_info = goal_info.split('\n')[0]

        yield json.dumps({"type": "status", "content": f"Goal identified: {goal_info[:50]}..."}) + "\n"

        while attempts < self.max_retries and not success:
            attempts += 1
            yield json.dumps({"type": "status", "content": f"Thinking cycle {attempts}/{self.max_retries}..."}) + "\n"

            if intent == 1: # LEARN/EXPLAIN
                # 1. Plan
                plan = self.planner.generate_plan(f"Goal: {goal_info}", context)
                yield json.dumps({"type": "plan", "content": plan}) + "\n"
                # 2. Creating
                yield json.dumps({"type": "start_content", "clear": True}) + "\n"
                exec_prompt = f"Goal: {goal_info}. {critique}\nProvide a comprehensive answer based on the plan. Do not repeat the plan itself."
                prompt = self.context_manager.format_prompt("Technical Expert", exec_prompt, context)
                full_ans = ""
                for token in self.engine.generate_stream(prompt):
                    full_ans += token
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"
                # 3. Verification
                verify = await self._ask_llm("Does this answer the goal? YES/NO + reason", f"Goal: {goal_info}\nAnswer: {full_ans[:200]}", max_tokens=50)
                if "YES" in verify.upper(): success = True
                else: critique = f"Previous attempt failed verification: {verify}"

            elif intent == 3: # TERMINAL
                # 1. Generation
                cmd_prompt = f"Goal: {goal_info}. Requirements: {context}. {critique} Generate ONLY the terminal command."
                cmd = await self._ask_llm("Terminal expert", cmd_prompt)
                cmd = self._extract_code(cmd)
                # 2. Verification goal and security
                verify = await self._ask_llm("Security specialist", f"Goal: {goal_info}. Command: {cmd}. Will it work and is it safe? Answer YES or NO + reason.")
                if "YES" in verify.upper():
                    self.pending_command = {"cmd": cmd, "cwd": workspace}
                    yield json.dumps({"type": "start_content", "clear": True}) + "\n"
                    yield json.dumps({"type": "chunk", "content": f"Proposed command: `{cmd}`"}) + "\n"
                    yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"
                    success = True
                else:
                    critique = f"Command '{cmd}' rejected: {verify}"

            elif intent == 2: # CODE GENERATION
                # 1. Plan
                plan = self.planner.generate_plan(f"Goal: {goal_info}", context)
                yield json.dumps({"type": "plan", "content": plan}) + "\n"
                # 2. Steps
                fragments = []
                for step in plan:
                    yield json.dumps({"type": "status", "content": f"Working on: {step}"}) + "\n"
                    f_prompt = f"Goal: {goal_info}. Task: {step}. Write ONLY the code fragment."
                    res = await self._ask_llm("Senior Developer", f_prompt, max_tokens=400)
                    fragments.append(self._extract_code(res))
                # 3. Assembly
                yield json.dumps({"type": "status", "content": "Assembling code..."}) + "\n"
                assembly_prompt = f"Assemble these parts into a single valid Python file. Parts: {fragments}. Fix duplicates."
                final_code = await self._ask_llm("Architect", assembly_prompt, max_tokens=1024)
                final_code = self._extract_code(final_code)
                
                yield json.dumps({"type": "start_content", "clear": True}) + "\n"
                yield json.dumps({"type": "chunk", "content": f"```python\n{final_code}\n```"}) + "\n"
                
                # 4. Verification (Goal + Static check)
                err = self._static_code_check(final_code)
                if not err: success = True
                else: critique = f"Fix syntax: {err}"

        if not success:
            yield json.dumps({"type": "chunk", "content": "\n\n> ⚠️ **AI Warning:** Failed to fully verify this result after multiple cycles. Please check carefully."}) + "\n"
        
        yield json.dumps({"type": "end"}) + "\n"


    async def process_completion(self, prompt_text: str) -> dict:
        prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
        async with self.lock:
            result = self.engine.generate(
                prompt, 
                max_tokens=32, 
                stop=["<|file_separator|>", "<|fim_prefix|>", "<|im_end|>", "\n\n", "\r\n\r\n"]
            )
        return result
