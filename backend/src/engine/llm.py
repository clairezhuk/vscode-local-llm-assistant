import os
from llama_cpp import Llama

MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"))
#MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models/qwen2.5-coder-3b-instruct-q3_k_m.gguf"))

class LLMEngine:
    def __init__(self):
        self.llm = Llama(model_path=MODEL_PATH, n_ctx=4096, n_gpu_layers=-1, n_batch=128, verbose=False) # 1.5 B setap
        # self.llm = Llama( # 3B setap
        #     model_path=MODEL_PATH,
        #     n_ctx=2048,           
        #     n_gpu_layers=-1,     
        #     n_batch=128,          
        #     type_k=2,             
        #     type_v=2,             
        #     flash_attn=True,      
        #     n_threads=4,         
        #     offload_kqv=True,       
        #     verbose=False
        # )

    def generate(self, prompt: str, max_tokens: int = 1024, stop: list = None, temp: float = 0.2) -> dict:
        response = self.llm(prompt, 
                            max_tokens=max_tokens, 
                            stop=stop or ["<|im_end|>"],
                            temperature=temp,    
                            top_p=0.95,            
                            repeat_penalty=1.1,   
                            )
        return {
            "text": response["choices"][0]["text"].strip(),
            "usage": response.get("usage", {})
        }
    
    def generate_stream(self, prompt: str, max_tokens: int = 1024, stop: list = None, temp: float = 0.2):
        stream = self.llm(
            prompt, 
            max_tokens=max_tokens, 
            stop=stop or ["<|im_end|>"], 
            stream=True,
            temperature=temp,      
            top_p=0.95,
            repeat_penalty=1.1
        )
        for chunk in stream:
            token = chunk["choices"][0]["text"]
            if token:
                yield token