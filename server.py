import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llama_cpp import Llama
import re

# 1. Configuration
MODEL_PATH = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
N_CTX = 2048
N_GPU_LAYERS = -1 # Use -1 for all layers on GPU

app = FastAPI()
llm = None

class GenerateRequest(BaseModel):
    command: str
    context: str = ""  # Code snippet or imports

@app.on_event("startup")
def startup_event():
    global llm
    print(f"Loading model from {MODEL_PATH}...")
    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=N_GPU_LAYERS,
        n_ctx=N_CTX,
        verbose=True
    )
    print("Model loaded successfully.")

def build_prompt(command, context):
    # Constructing ChatML format
    system_msg = "You are a helpful Python coding assistant. Output only valid Python code."
    user_msg = f"Context:\n{context}\n\nTask:\n{command}"
    
    return f"""<|im_start|>system
{system_msg}<|im_end|>
<|im_start|>user
{user_msg}<|im_end|>
<|im_start|>assistant
"""

@app.post("/generate")
async def generate_code(request: GenerateRequest):
    if not llm:
        raise HTTPException(status_code=500, detail="Model not loaded")

    prompt = build_prompt(request.command, request.context)
    
    print("Generating...") # Лог для контролю
    output = llm(
        prompt,
        max_tokens=512, # Трохи збільшимо ліміт
        stop=["<|im_end|>"], # ПРИБРАЛИ "```"
        echo=False
    )
    
    raw_text = output['choices'][0]['text']
    print(f"Raw Output: {raw_text}") # Щоб ти бачила, що видає модель
    
    # Очистка від ```python та ```
    clean_text = re.sub(r"^```python\s*", "", raw_text.strip())
    clean_text = re.sub(r"^```\s*", "", clean_text)
    clean_text = re.sub(r"```$", "", clean_text)
    
    return {"response": clean_text.strip()}

if __name__ == "__main__":
    # Runs on localhost:8000
    uvicorn.run(app, host="127.0.0.1", port=8000)