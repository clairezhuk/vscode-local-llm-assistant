import re
import ast
import json
import asyncio
from src.engine.llm import LLMEngine
from src.context_manager.manager import ContextManager
from src.executor.tools import ToolExecutor
from src.context_manager.file_processor import FileProcessor
from src.agentic_orchestrator.planner import TaskPlanner

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
        match = re.search(r'```(?:\w+)?\n(.*?)\n```', text, re.DOTALL)
        if match: return match.group(1).strip()
        return text.replace('`', '').strip()

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
    
    async def _ask_llm(self, system_prompt: str, user_prompt: str):
        full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        res = await asyncio.to_thread(self.engine.generate, full_prompt)
        return res["text"].strip()
    
    async def process_chat(self, raw_query: str, context: dict):
        intent = context.get("intent", 1) 
        mode = context.get("mode", "fast") 
        attached_files = context.get("attached_files", [])
        workspace_path = context.get("workspace_path")

        file_ctx = self.file_processor.process_files(attached_files, self.engine) if attached_files else ""
        full_ctx = f"Workspace: {workspace_path}\nFiles Context: {file_ctx}\n"

        if mode == "fast":
            async for chunk in self._run_fast_mode(raw_query, full_ctx, intent):
                yield chunk
        else:
            async for chunk in self._run_thinking_mode(raw_query, full_ctx, intent, workspace_path):
                yield chunk

        # yield json.dumps({"type": "status", "content": "Preprocessing query..."}) + "\n"
        # query = self.preprocess_query(raw_query)
        
        
        # ctx_text = context.get("active_file_content", "") + f"\n{file_ctx}"

        # plan_text = ""

        # if mode == "thinking":
        #     yield json.dumps({"type": "status", "content": "Creating execution plan..."}) + "\n"
        #     plan = self.planner.generate_plan(query, ctx_text)
        #     plan_text = self.planner.format_plan_for_llm(plan)
        #     yield json.dumps({"type": "plan", "content": plan}) + "\n"

        #     if intent == 2:
        #         for i, step in enumerate(plan):
        #             yield json.dumps({"type": "status", "content": f"Executing: {step}..."}) + "\n"
        #             await asyncio.sleep(0.1) # Емуляція роздумів

        # sys_prompts = {
        #     1: "You are a helpful assistant. Explain clearly. Do not run commands.",
        #     2: "You are a coding assistant. FOLLOW THIS PLAN:\n{plan_text}\n\nWrite ONLY the code inside a markdown block. All code must be self-contained and use 'return'.",
        #     3: "You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block. No explanations."
        # }

        # prompt = self.context_manager.format_prompt(sys_prompts[intent], query, ctx_text)

        # full_response = ""
        # yield json.dumps({"type": "start_content"}) + "\n"
        
        # for token in self.engine.generate_stream(prompt):
        #     full_response += token
        #     yield json.dumps({"type": "chunk", "content": token}) + "\n"

        # if intent == 2 and mode == "thinking":
        #     code = self._extract_code(full_response)
        #     error = self._static_code_check(code)
        #     attempts = 0
            
        #     while error and attempts < 3:
        #         attempts += 1
        #         yield json.dumps({"type": "status", "content": f"Error found: {error}. Retrying ({attempts}/3)..."}) + "\n"
                
        #         fix_query = f"Fix this error: {error}\nOriginal: {query}"
        #         prompt = self.context_manager.format_prompt(sys_prompts[2], fix_query, ctx_text)
                
        #         full_response = ""
        #         yield json.dumps({"type": "start_content", "clear": True}) + "\n"
        #         for token in self.engine.generate_stream(prompt):
        #             full_response += token
        #             yield json.dumps({"type": "chunk", "content": token}) + "\n"
                
        #         code = self._extract_code(full_response)
        #         error = self._static_code_check(code)

        #     if error:
        #         yield json.dumps({"type": "chunk", "content": "\n\n> ⚠️ **AI Warning:** I tried to fix this code, but it may still contain errors."})

        # if intent == 3:
        #     cmd = self._extract_code(full_response)
        #     self.pending_command = {"cmd": cmd, "cwd": workspace_path}
        #     yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"

        # yield json.dumps({"type": "end"}) + "\n"

    async def _run_fast_mode(self, query: str, context: str, intent: int):
        yield json.dumps({"type": "status", "content": "Fast processing..."}) + "\n"
        sys_prompts = {
            1: "You are a helpful assistant. Explain clearly. Do not run commands.",
            2: "You are a coding assistant. \nWrite ONLY the code inside a markdown block. All code must be self-contained and use 'return'.",
            3: "You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block. No explanations."
        }
        prompt = self.context_manager.format_prompt(sys_prompts[intent], query, context)
        
        yield json.dumps({"type": "start_content"}) + "\n"
        for token in self.engine.generate_stream(prompt):
            yield json.dumps({"type": "chunk", "content": token}) + "\n"

    async def _run_thinking_mode(self, query: str, context: str, intent: int, workspace: str):
        attempts = 0
        critique = ""
        success = False
        final_result = ""

        # --- STEP 1: GOAL AND REQUAREMENTS ---
        yield json.dumps({"type": "status", "content": "Defining goal and constraints..."}) + "\n"
        goal_prompt = f"Analyze the user request: '{query}'. What is the core goal and what are the technical constraints/requirements? Output briefly."
        goal_info = await self._ask_llm("You are a technical analyst.", goal_prompt)
        yield json.dumps({"type": "status", "content": f"Goal identified: {goal_info[:50]}..."}) + "\n"

        while attempts < self.max_retries and not success:
            attempts += 1
            yield json.dumps({"type": "status", "content": f"Thinking cycle {attempts}/{self.max_retries}..."}) + "\n"

            if intent == 1: # LEARN/EXPLAIN
                # 1. Plan
                plan = self.planner.generate_plan(f"Goal: {goal_info}. Query: {query}", context)
                yield json.dumps({"type": "plan", "content": plan}) + "\n"
                # 2. Execution
                final_result = ""
                yield json.dumps({"type": "start_content", "clear": True}) + "\n"
                exec_prompt = f"Follow this plan: {plan}. Goal: {goal_info}. {critique}"
                for token in self.engine.generate_stream(exec_prompt):
                    final_result += token
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"
                # 3. Verification
                verify = await self._ask_llm("Reviewer", f"Goal: {goal_info}. Result: {final_result}. Does it satisfy the goal? Answer YES or NO + reason.")
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
                plan = self.planner.generate_plan(f"Goal: {goal_info}. Constraints: {context}", context)
                yield json.dumps({"type": "plan", "content": plan}) + "\n"
                # 2. Steps
                fragments = []
                for step in plan:
                    yield json.dumps({"type": "status", "content": f"Coding: {step}"}) + "\n"
                    frag = await self._ask_llm("Coder", f"Goal: {goal_info}. Step: {step}. Context: {context}. {critique} Write only code.")
                    fragments.append(self._extract_code(frag))
                # 3. Assembly
                yield json.dumps({"type": "status", "content": "Assembling fragments..."}) + "\n"
                assembly_prompt = f"Assemble these code parts into one clean file. Goal: {goal_info}. Parts: {fragments}. Avoid duplicate imports and functions."
                final_result = await self._ask_llm("Architect", assembly_prompt)
                final_result = self._extract_code(final_result)
                
                yield json.dumps({"type": "start_content", "clear": True}) + "\n"
                yield json.dumps({"type": "chunk", "content": f"```python\n{final_result}\n```"}) + "\n"
                
                # 4. Verification (Goal + Static check)
                err = self._static_code_check(final_result)
                if err:
                    critique = f"Code has syntax errors: {err}"
                    continue
                
                verify = await self._ask_llm("Reviewer", f"Goal: {goal_info}. Code: {final_result}. Does it satisfy constraints? Answer YES or NO + reason.")
                if "YES" in verify.upper(): success = True
                else: critique = f"Logic check failed: {verify}"

        if not success:
            yield json.dumps({"type": "chunk", "content": "\n\n> ⚠️ **AI Warning:** Failed to fully verify this result after multiple cycles. Please check carefully."}) + "\n"
        
        yield json.dumps({"type": "end"}) + "\n"


    def process_completion(self, prompt_text: str) -> dict:
        prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
        result = self.engine.generate(
            prompt, 
            max_tokens=32, 
            stop=["<|file_separator|>", "<|fim_prefix|>", "<|im_end|>", "\n\n", "\r\n\r\n"]
        )
        return result
