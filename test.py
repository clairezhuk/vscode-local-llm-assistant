from llama_cpp import Llama

model_path = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"

#print("--- Checking Device ---")
# verbose=True will print backend details (CUDA/BLAS/Metal)
# llm = Llama(model_path=model_path, n_gpu_layers=-1, verbose=True)

try:
    print(f"Loading {model_path}...")
    llm = Llama(model_path=model_path, n_gpu_layers=-1, verbose=False)

    user_prompt = 'Реалізуй bubble-sort на введеній строці'
    prompt = "#python code that relize task '"+user_prompt+"' here: \n def"
    
    print("Generating code...")
    output = llm(prompt, max_tokens=200, stop=["```"])
    
    generated_text = output['choices'][0]['text']
    print(f"\nResult:\n{prompt}{generated_text}")
    print("\nStatus: Model is working!")

except Exception as e:
    print(f"Error: {e}")