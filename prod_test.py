import time
from llama_cpp import Llama
from huggingface_hub import hf_hub_download

repo_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
filename = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
model_path = hf_hub_download(repo_id=repo_id, filename=filename)

print("Loading model...")
llm = Llama(model_path=model_path, n_gpu_layers=-1, verbose=True)

prompt = "# python code to sort list\ndef"

print("\nGenerating code...")
start_time = time.time()

output = llm(prompt, max_tokens=150, stop=["```"])

end_time = time.time()

generated_text = output['choices'][0]['text']
tokens = output['usage']['completion_tokens']
elapsed_time = end_time - start_time
speed = tokens / elapsed_time if elapsed_time > 0 else 0

print(f"\nResult:\n{prompt}{generated_text}")
print("\n--- Stats ---")
print(f"Tokens generated: {tokens}")
print(f"Time: {elapsed_time:.2f} seconds")
print(f"Speed: {speed:.2f} tokens/sec")