import ast
from .prompts import PromptLibrary as PrLib

class Validator:
    def static_check(self, code: str) -> str:
        if not code.strip(): return "Empty response."
        try:
            ast.parse(code)
            return "CLEAR"
        except SyntaxError as e:
            return f"Syntax Error: {e.msg} at line {e.lineno}"

    async def llm_verify(self, engine, goal: str, result: str) -> bool:
        prompt = f"<|im_start|>system\n{PrLib.LLM_VERIFY}<|im_end|>\n" \
             f"<|im_start|>user\nGoal: {goal}\nResult: {result[:500]}<|im_end|>\n<|im_start|>assistant\n"
        res = engine.generate(prompt, max_tokens=5)["text"].strip().upper()
        return "YES" in res