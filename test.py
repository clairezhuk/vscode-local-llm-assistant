from llama_cpp import Llama
from huggingface_hub import hf_hub_download

repo_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
filename = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"

try:
    print("Downloading or locating model...")
    model_path = hf_hub_download(repo_id=repo_id, filename=filename)

    print(f"Loading {model_path}...")
    llm = Llama(model_path=model_path, n_gpu_layers=-1, verbose=False)

    user_prompt = "Implement bubble-sort for an input string"
    prompt = "# python code that realize task '" + user_prompt + "' here:\ndef"
    
    print("Generating code...")
    output = llm(prompt, max_tokens=200, stop=["```"])
    
    generated_text = output['choices'][0]['text']
    print(f"\nResult:\n{prompt}{generated_text}")
    print("\nStatus: Model is working!")

except Exception as e:
    print(f"Error: {e}")