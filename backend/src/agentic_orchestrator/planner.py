import json
import re

class TaskPlanner:
    def __init__(self, engine):
        self.engine = engine

    def generate_plan(self, query: str, context: str = "") -> list:
        sys_prompt = (
            "You are a technical architect. Break down the coding task into 3-5 logical steps. "
            "Output ONLY a JSON array of strings. Example: [\"Step 1\", \"Step 2\"]. "
            "Do not write code, only logical steps."
        )
        
        prompt = f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
        if context:
            prompt += f"<|im_start|>user\nContext:\n{context}<|im_end|>\n"
        prompt += f"<|im_start|>user\nTask: {query}<|im_end|>\n<|im_start|>assistant\n"

        res = self.engine.generate(prompt, max_tokens=256)["text"].strip()
        
        try:
            match = re.search(r'\[.*\]', res, re.DOTALL)
            if match:
                plan = json.loads(match.group(0))
                if isinstance(plan, list):
                    return plan
            return [res] 
        except:
            return ["Analyze requirements", "Implement solution", "Verify result"]

    def format_plan_for_llm(self, plan: list) -> str:
        return "\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)])