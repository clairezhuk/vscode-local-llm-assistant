import json
import re
import asyncio
from .prompts import PromptLibrary as PrLib

class ReasoningEngine:
    def __init__(self, engine, validator):
        self.engine = engine
        self.validator = validator
        self.max_retries = 3
        self.strategies = {
            "fast": self._fast_mode,
            "thinking": self._thinking_mode
        }

    def _extract_code(self, text: str) -> str:
        blocks = re.findall(r'```(?:\w+)?\s*(.*?)\s*```', text, re.DOTALL)
        code = blocks[-1] if blocks else text.strip()
        
        noise = [r'^\s*#?\s*Attempt\s*\d+:.*$', r'^\s*---.*$', r'^\s*###.*$']
        lines = code.split('\n')
        clean = [l for l in lines if not any(re.match(p, l, re.IGNORECASE) for p in noise)]
        return '\n'.join(clean).strip()

    async def execute(self, mode: str, query: str, context: str, goal: str, intent: int, workspace: str):
        strategy_func = self.strategies.get(mode, self._fast_mode)
        async for chunk in strategy_func(query, context, goal, intent, workspace):
            yield chunk

    async def _fast_mode(self, query: str, context: str, goal: str, intent: int, workspace: str):
        yield json.dumps({"type": "status", "content": "Fast processing..."}) + "\n"
        
        sys_prompts = {
            1: PrLib.FAST_LEARN,
            2: PrLib.FAST_CODE,
            3: PrLib.FAST_CLI,
        }
        
        prompt = f"<|im_start|>system\n{sys_prompts.get(intent, 'Assistant')}\n{PrLib.FAST_MODE_SYSTEM}<|im_end|>\n" \
                 f"<|im_start|>user\nContext:\n{context}\nTask: {query}<|im_end|>\n<|im_start|>assistant\n"
        
        yield json.dumps({"type": "start_content"}) + "\n"
        full_text = ""
        for token in self.engine.generate_stream(prompt):
            full_text += token
            yield json.dumps({"type": "chunk", "content": token}) + "\n"
        
        if intent == 3:
            cmd = self._extract_code(full_text)
            yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"

    async def _thinking_mode(self, query: str, context: str, goal: str, intent: int, workspace: str):
        attempts = 0
        critique = ""
        success = False

        yield json.dumps({"type": "status", "content": f"Goal: {goal}"}) + "\n"
        yield json.dumps({"type": "start_content"}) + "\n"

        while attempts < self.max_retries and not success:
            attempts += 1
            yield json.dumps({"type": "status", "content": f"Cycle {attempts}/{self.max_retries}..."}) + "\n"
            yield json.dumps({"type": "chunk", "content": f"\n\n---\n### Attempt {attempts}\n"}) + "\n"

            if intent == 1: # LEARN (Textual)
                prompt = f"<|im_start|>system\n{PrLib.THINKING_LEARN}\n{critique}<|im_end|>\n" \
                         f"<|im_start|>user\nContext:\n{context}\nGoal: {goal}<|im_end|>\n<|im_start|>assistant\n"
                
                full_ans = ""
                for token in self.engine.generate_stream(prompt, temp=0.3):
                    full_ans += token
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"
                
                success = True # Для тексту зазвичай 1 спроба, або додати LLM верифікацію

            elif intent == 2: # CODE
                # Вибір внутрішньої стратегії (поки прямий виклик refine)
                final_code = ""
                async for res in self._reflection_refine(query, context, goal, critique):
                    final_code = res
                
                yield json.dumps({"type": "chunk", "content": f"\n```python\n{final_code}\n```\n"}) + "\n"
                
                err = self.validator.static_check(final_code)
                if err != "CLEAR":
                    critique = f"Fix syntax error: {err}"
                else:
                    is_ok = await self.validator.llm_verify(self.engine, goal, final_code)
                    if is_ok: success = True
                    else: critique = "Code logic is incomplete for the goal."

            elif intent == 3: # TERMINAL
                prompt = f"<|im_start|>system\n{PrLib.FAST_MODE_SYSTEM}. Generate ONLY terminal command.\n{critique}<|im_end|>\n" \
                         f"<|im_start|>user\nContext:\n{context}\nTask: {query}<|im_end|>\n<|im_start|>assistant\n"
                
                cmd_raw = await asyncio.to_thread(self.engine.generate, prompt)
                cmd = self._extract_code(cmd_raw["text"])
                
                yield json.dumps({"type": "chunk", "content": f"Proposed: `{cmd}`"}) + "\n"
                yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"
                success = True

        if not success:
            yield json.dumps({"type": "chunk", "content": "\n\n> ⚠️ **Verification failed after max retries.**"}) + "\n"
        yield json.dumps({"type": "end"}) + "\n"

    # Внутрішні стратегії (Refine, Draft, Planning)
    async def _reflection_refine(self, query, context, goal, critique):
        prompt = f"<|im_start|>system\n{PrLib.STRATEGY_REFINE}\n{critique}<|im_end|>\n" \
                 f"<|im_start|>user\nGoal: {goal}\nContext:\n{context}<|im_end|>\n<|im_start|>assistant\n"
        
        res = await asyncio.to_thread(self.engine.generate, prompt, max_tokens=1024)
        yield self._extract_code(res["text"])

    async def _chain_of_draft(self, query, context, goal, critique):
        # Аналогічна реалізація з використанням PrLib.STRATEGY_DRAFT
        pass

    async def _planning_logic(self, query, context, goal, critique):
        # Аналогічна реалізація з використанням PrLib.STRATEGY_PLANNING
        pass