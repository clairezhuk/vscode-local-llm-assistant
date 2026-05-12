import ast
import os

files = [
    "backend/main.py",
    "backend/src/agentic_orchestrator/orchestrator.py",
    "backend/src/api_router/routes.py",
    "backend/src/context_manager/file_processor.py",
    "backend/src/context_manager/manager.py",
    "backend/src/engine/llm.py",
    "backend/src/executor/tools.py",
    "backend/tests/run_benchmark.py"
]

output_file = "backend_signatures.txt"

def extract_signatures(file_path):
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found.\n"
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        
        result = [f"File: {file_path}"]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                result.append(f"class {node.name}:")
            elif isinstance(node, ast.FunctionDef):
                indent = "  " if any(isinstance(parent, ast.ClassDef) for parent in ast.walk(tree) if node in getattr(parent, 'body', [])) else ""
                result.append(f"{indent}def {node.name}(...):")
        
        return "\n".join(result) + "\n\n"
    except Exception as e:
        return f"Error processing {file_path}: {e}\n\n"

def main():
    with open(output_file, "w", encoding="utf-8") as out:
        for file_path in files:
            signatures = extract_signatures(file_path)
            out.write(signatures)
    
    print(f"Done! Signatures saved to {output_file}")

if __name__ == "__main__":
    main()