import json
import re

class TaskPlanner:
    def __init__(self, engine):
        self.engine = engine

    def generate_plan(self, query: str, context: str = "") -> list:
        sys_prompt = (
            "You are a technical architect. Your job is to extract the core technical task from the user's input, "
            "even if the input contains irrelevant stories, noise, or typos. "
            "Break down the technical task into logical steps. "
            "IMPORTANT: If the task is simple (e.g., a single function or a simple question), "
            "provide ONLY ONE step. Use more steps (max 4) ONLY for complex multi-stage tasks. "
            "Output ONLY a JSON array. DO NOT include function names or code in the steps. "
            "Example: [\"Initialize DP table\", \"Fill values\", \"Return max\"]."
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