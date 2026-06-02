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
    def __init__(self):
        self.engine = LLMEngine()
        self.context_manager = ContextManager()
        self.executor = ToolExecutor()
        self.file_processor = FileProcessor()
        self.planner = TaskPlanner(self.engine)
        self.pending_command = None

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
        print(f"Extracted command: {match.group(1).strip()}")
        return match.group(1).strip() if match else text

    def execute_confirmed(self):
        if not self.pending_command:
            return "No command to execute."
        res = self.executor.execute_command(self.pending_command)
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
    
    async def process_chat(self, raw_query: str, context: dict):
        intent = context.get("intent", 1) 
        mode = context.get("mode", "fast") # "fast" or "thinking"
        attached_files = context.get("attached_files", [])

        yield json.dumps({"type": "status", "content": "Preprocessing query..."}) + "\n"
        query = self.preprocess_query(raw_query)
        
        file_ctx = self.file_processor.process_files(attached_files, self.engine) if attached_files else ""
        ctx_text = context.get("active_file_content", "") + f"\n{file_ctx}"

        plan_text = ""

        if mode == "thinking":
            yield json.dumps({"type": "status", "content": "Creating execution plan..."}) + "\n"
            plan = self.planner.generate_plan(query, ctx_text)
            plan_text = self.planner.format_plan_for_llm(plan)
            yield json.dumps({"type": "plan", "content": plan}) + "\n"

            if intent == 2:
                for i, step in enumerate(plan):
                    yield json.dumps({"type": "status", "content": f"Executing: {step}..."}) + "\n"
                    await asyncio.sleep(0.1) # Емуляція роздумів

        sys_prompts = {
            1: "You are a helpful assistant. Explain clearly. Do not run commands.",
            2: "You are a coding assistant. FOLLOW THIS PLAN:\n{plan_text}\n\nWrite ONLY the code inside a markdown block. All code must be self-contained and use 'return'.",
            3: "You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block. No explanations."
        }

        prompt = self.context_manager.format_prompt(sys_prompts[intent], query, ctx_text)

        full_response = ""
        yield json.dumps({"type": "start_content"}) + "\n"
        
        for token in self.engine.generate_stream(prompt):
            full_response += token
            yield json.dumps({"type": "chunk", "content": token}) + "\n"

        if intent == 2 and mode == "thinking":
            code = self._extract_code(full_response)
            error = self._static_code_check(code)
            attempts = 0
            
            while error and attempts < 3:
                attempts += 1
                yield json.dumps({"type": "status", "content": f"Error found: {error}. Retrying ({attempts}/3)..."}) + "\n"
                
                fix_query = f"Fix this error: {error}\nOriginal: {query}"
                prompt = self.context_manager.format_prompt(sys_prompts[2], fix_query, ctx_text)
                
                full_response = ""
                yield json.dumps({"type": "start_content", "clear": True}) + "\n"
                for token in self.engine.generate_stream(prompt):
                    full_response += token
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"
                
                code = self._extract_code(full_response)
                error = self._static_code_check(code)

            if error:
                yield json.dumps({"type": "chunk", "content": "\n\n> ⚠️ **AI Warning:** I tried to fix this code, but it may still contain errors."})

        if intent == 3:
            cmd = self._extract_code(full_response)
            self.pending_command = cmd
            yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"

        yield json.dumps({"type": "end"}) + "\n"
