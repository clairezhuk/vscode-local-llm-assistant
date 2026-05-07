import re
import ast
from src.engine.llm import LLMEngine
from src.context_manager.manager import ContextManager
from src.executor.tools import ToolExecutor
from src.context_manager.file_processor import FileProcessor

class Orchestrator:
    def __init__(self):
        self.engine = LLMEngine()
        self.context_manager = ContextManager()
        self.executor = ToolExecutor()
        self.file_processor = FileProcessor()

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

    def classify_intent(self, query: str) -> int:
        prompt = f"<|im_start|>system\nYou are a router. Analyze the user query.\nReturn ONLY '3' if it's a CLI/terminal command (pip, npm, git).\nReturn ONLY '2' if they ask to write a programming script, function, or code snippet.\nReturn ONLY '1' if they ask a theory question, explanation, or definition.\n<|im_end|>\n<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
        res = self.engine.generate(prompt, max_tokens=5)["text"].strip()
        
        intent = 1
        if "3" in res: intent = 3
        elif "2" in res: intent = 2
        
        query_lower = query.lower()
        code_triggers = ["write a function", "napisz funkcję", "напиши функцію", "code", "script", "function"]
        if intent != 2 and any(trigger in query_lower for trigger in code_triggers):
            intent = 2
            
        print(f" [Orchestrator] Selected Intent: {intent}")
        return intent

    def _extract_code_block(self, text: str) -> str:
        match = re.search(r'```(?:bash|sh|cmd|powershell|markdown|python)?\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.replace("`", "").strip()
    
    def _is_valid_cli(self, cmd: str) -> bool:
        cmd = cmd.strip().lower()
        allowed_prefixes = ("pip", "python", "git", "npm", "conda", "ls", "cd", "mkdir", "echo", "pytest")
        return cmd.startswith(allowed_prefixes)
    
    def _static_code_check(self, code: str) -> str:
        if not code: return "No code block found."
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"SyntaxError: {e}"

        defined_funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        called_funcs = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        
        # Додано hasattr, getattr, setattr, щоб AST-валідатор не сварився на них
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
    
    def process_chat(self, raw_query: str, context: dict) -> dict:
        query = self.preprocess_query(raw_query)
        intent = self.classify_intent(query)
        
        files = context.get("attached_files", [])
        file_context = self.file_processor.process_files(files, self.engine) if files else ""
        
        ctx_text = context.get("active_file_content", "")
        if file_context:
            ctx_text += f"\n\nAttached Files Info:\n{file_context}"

        if intent == 3:
            check_prompt = f"<|im_start|>system\nExtract only the terminal command from this query. If there is no command, output 'NONE'.<|im_end|>\n<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
            test_cmd = self.engine.generate(check_prompt, max_tokens=20)["text"].strip()
            if not self._is_valid_cli(test_cmd):
                print(f" [Orchestrator] Downgrading Intent 3 -> 1 (Not a valid CLI command: {test_cmd})")
                intent = 1

        sys_prompts = {
            1: "You are a helpful assistant. Explain clearly. Do not run commands.",
            2: "You are a coding assistant. Write ONLY the requested code inside a markdown block. CRITICAL RULES:\n1. The code MUST be self-contained.\n2. Always explicitly 'return' the final result.",
            3: "You are a terminal assistant. Write ONLY the EXACT terminal command inside a markdown block."
        }

        prompt = self.context_manager.format_prompt(sys_prompts[intent], query, ctx_text)
        gen_result = self.engine.generate(prompt, max_tokens=1024)
        action = gen_result["text"]
        usage = gen_result["usage"]

        if intent == 2:
            code_only = self._extract_code_block(action)
            if not code_only or "sorry" in action.lower() or "didn't provide" in action.lower():
                print(" [Orchestrator] Intent 2 Fallback -> Intent 1 (No valid code was generated).")
                intent = 1
                prompt = self.context_manager.format_prompt(sys_prompts[1], query, ctx_text)
                gen_result = self.engine.generate(prompt, max_tokens=1024)
                action = gen_result["text"]
                usage["total_tokens"] += gen_result["usage"].get("total_tokens", 0)

        # CLEAN SLATE CORRECTION LOOP
        if intent == 2:
            code_only = self._extract_code_block(action)
            error = self._static_code_check(code_only)
            
            max_retries = 3 # Для чистого аркуша достатньо 3 спроб
            attempt = 0
            
            while error and attempt < max_retries:
                attempt += 1
                print(f" [Clean Slate Correction] Attempt {attempt}/{max_retries} - Error: {error}")
                clean_slate_query = query + f"\n\nCRITICAL FIX REQUIRED: Write the complete code from scratch. You MUST address this error: {error}. Ensure all modules are imported, all helper functions are defined, and you explicitly return the result. Wrap code in ```python ```."
                
                fix_prompt = self.context_manager.format_prompt(sys_prompts[intent], clean_slate_query, ctx_text)
                
                fix_result = self.engine.generate(fix_prompt, max_tokens=1024)
                action = fix_result["text"]
                usage["total_tokens"] += fix_result["usage"].get("total_tokens", 0)
                
                code_only = self._extract_code_block(action)
                error = self._static_code_check(code_only)
                
            if error:
                print(f" [Clean Slate Correction] Failed to fix after {max_retries} attempts.")
                action += f"\n\n> **⚠️ AI Warning:** I tried to fix this code, but it may still contain errors:\n> `{error}`"
        
        if intent == 3:
            clean_cmd = self._extract_code_block(action)
            if self._is_valid_cli(clean_cmd):
                obs = self.executor.execute_command(clean_cmd)
                action += f"\n\n**Terminal Execution:** `{clean_cmd}`\n**Result:**\n```\n{obs}\n```"
            else:
                 action += f"\n\n*(Command execution blocked: '{clean_cmd}' is not a recognized safe command)*"

        self.context_manager.add_message("user", raw_query)
        self.context_manager.add_message("assistant", action)       
        return {"result": action, "usage": usage, "intent": intent}

    def process_completion(self, prompt_text: str) -> dict:
        prompt = f"<|fim_prefix|>{prompt_text}<|fim_suffix|><|fim_middle|>"
        return self.engine.generate(prompt, max_tokens=32, stop=["<|file_separator|>", "<|fim_prefix|>", "<|im_end|>", "\n\n", "\r\n\r\n"])