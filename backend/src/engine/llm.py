import os
from llama_cpp import Llama

MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"))

class LLMEngine:
    def __init__(self):
        self.llm = Llama(model_path=MODEL_PATH, n_ctx=4096, n_gpu_layers=-1, verbose=False)

    def generate(self, prompt: str, max_tokens: int = 1024, stop: list = None) -> dict:
        response = self.llm(prompt, max_tokens=max_tokens, stop=stop or ["<|im_end|>"])
        return {
            "text": response["choices"][0]["text"].strip(),
            "usage": response.get("usage", {})
        }