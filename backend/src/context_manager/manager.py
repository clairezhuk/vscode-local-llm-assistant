class ContextManager:
    def __init__(self, char_limit: int = 8192):
        self.history = []
        self.char_limit = char_limit

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def format_prompt(self, system_prompt: str, user_query: str, file_context: str) -> str:
        # Systrm + current prompt
        fixed_parts = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        current_query = f"<|im_start|>user\nContext:\n{file_context}\n\nQuery: {user_query}<|im_end|>\n<|im_start|>assistant\n"
        
        available_chars = self.char_limit - len(fixed_parts) - len(current_query)
        
        # Sliding Window
        selected_history = []
        for msg in reversed(self.history):
            msg_text = f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
            if len(msg_text) < available_chars:
                selected_history.insert(0, msg_text)
                available_chars -= len(msg_text)
            else:
                break 
                
        return fixed_parts + "".join(selected_history) + current_query