import sys
import os
import subprocess
from llama_cpp import llama_print_system_info

print("--- Python Info ---")
print(f"Version: {sys.version.split()[0]}")
print(f"Architecture: {sys.maxsize > 2**32 and '64-bit' or '32-bit'}")

print("\n--- Llama.cpp Info ---")
info = llama_print_system_info().decode('utf-8')
print(info)

print("\n--- CUDA Info ---")
print(f"CUDA_PATH: {os.environ.get('CUDA_PATH', 'Not Set')}")

try:
    nvcc = subprocess.check_output(["nvcc", "--version"]).decode('utf-8')
    print(f"NVCC: {nvcc.splitlines()[-1]}")
except Exception:
    print("NVCC: Not found in PATH")