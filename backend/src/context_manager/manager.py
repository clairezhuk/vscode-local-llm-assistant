class ContextManager:
    def __init__(self):
        self.history = []

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        if len(self.history) > 6:
            self.history = self.history[-6:]

    def format_prompt(self, system_prompt: str, new_query: str, code_context: str = "") -> str:
        prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        
        if code_context:
            prompt += f"<|im_start|>user\nContext:\n{code_context}<|im_end|>\n"
            
        for msg in self.history:
            prompt += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
            
        prompt += f"<|im_start|>user\n{new_query}<|im_end|>\n<|im_start|>assistant\n"
        return prompt