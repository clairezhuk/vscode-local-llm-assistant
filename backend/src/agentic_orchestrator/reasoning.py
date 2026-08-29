import json
import re
import asyncio
from .prompts import PromptLibrary as PrLib
from ..context_manager.kv_cache import KVCacheManager

class ReasoningEngine:
    def __init__(self, engine, validator):
        self.engine = engine
        self.validator = validator
        self.strategies = {
            "fast": self._fast_mode,
            "thinking": self._thinking_mode
        }
        self.kv_cache = KVCacheManager(self.engine)

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
        yield json.dumps({"type": "status", "content": "Initializing thinking context..."}) + "\n"
        
        base_prefix = f"<|im_start|>system\n{PrLib.BASE_THINKING_SYSTEM}\nContext:\n{context}<|im_end|>\n"
        state_id = self.kv_cache.create_state(base_prefix)

        try:
            if intent == 1:
                yield json.dumps({"type": "status", "content": "Extracting facts..."}) + "\n"
                self.kv_cache.load_state(state_id)
                ext_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.TEXT_EXTRACT}\nQuery: {query}<|im_end|>\n<|im_start|>assistant\n"
                facts = self.engine.generate(ext_prompt, max_tokens=150)["text"].strip()

                yield json.dumps({"type": "status", "content": "Drafting response..."}) + "\n"
                self.kv_cache.load_state(state_id)
                draft_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.TEXT_DRAFT}\nFacts:\n{facts}\nQuery: {query}<|im_end|>\n<|im_start|>assistant\n"
                draft = self.engine.generate(draft_prompt, max_tokens=500)["text"].strip()

                yield json.dumps({"type": "status", "content": "Finalizing..."}) + "\n"
                self.kv_cache.load_state(state_id)
                final_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.TEXT_FINAL}\nDraft:\n{draft}<|im_end|>\n<|im_start|>assistant\n"
                
                yield json.dumps({"type": "start_content"}) + "\n"
                for token in self.engine.generate_stream(final_prompt):
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"

            elif intent == 2:
                yield json.dumps({"type": "status", "content": "Analyzing signature..."}) + "\n"
                self.kv_cache.load_state(state_id)
                sig_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.CODE_INTERFACE}\nTask: {query}<|im_end|>\n<|im_start|>assistant\n"
                signature = self.engine.generate(sig_prompt, max_tokens=50)["text"].strip()

                yield json.dumps({"type": "status", "content": "Planning algorithm..."}) + "\n"
                self.kv_cache.load_state(state_id)
                plan_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.CODE_PLAN}\nSignature: {signature}\nTask: {query}<|im_end|>\n<|im_start|>assistant\n"
                plan = self.engine.generate(plan_prompt, max_tokens=150)["text"].strip()

                yield json.dumps({"type": "status", "content": "Writing code..."}) + "\n"
                self.kv_cache.load_state(state_id)
                code_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.CODE_WRITE}\nSignature:\n{signature}\nPlan:\n{plan}<|im_end|>\n<|im_start|>assistant\n"
                
                yield json.dumps({"type": "start_content"}) + "\n"
                full_text = ""
                for token in self.engine.generate_stream(code_prompt):
                    full_text += token
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"

            elif intent == 3:
                yield json.dumps({"type": "status", "content": "Analyzing environment..."}) + "\n"
                self.kv_cache.load_state(state_id)
                env_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.CLI_ANALYSIS}\nTask: {query}<|im_end|>\n<|im_start|>assistant\n"
                analysis = self.engine.generate(env_prompt, max_tokens=50)["text"].strip()

                yield json.dumps({"type": "status", "content": "Generating command..."}) + "\n"
                self.kv_cache.load_state(state_id)
                cmd_prompt = f"{base_prefix}<|im_start|>user\n{PrLib.CLI_GENERATE}\nTarget: {analysis}<|im_end|>\n<|im_start|>assistant\n"
                
                yield json.dumps({"type": "start_content"}) + "\n"
                full_text = ""
                for token in self.engine.generate_stream(cmd_prompt):
                    full_text += token
                    yield json.dumps({"type": "chunk", "content": token}) + "\n"

                cmd = self._extract_code(full_text)
                yield json.dumps({"type": "command_proposal", "command": cmd}) + "\n"

        finally:
            self.kv_cache.clear_state(state_id)