import ast
import json
from ..agentic_orchestrator.prompts import PromptLibrary as PrLib

class FileProcessor:
    def process_files(self, files: list, engine) -> str:
        file_blocks = []
        for f in files:
            name = f.get("name", "unknown")
            content = f.get("content", "")
            ext = name.split('.')[-1].lower() if '.' in name else ''

            if ext in ["py", "ts", "js", "cpp"]:
                processed = self._extract_structure(content, ext)
            elif ext == "json":
                processed = self._summarize_json(content)
            else:
                processed = self._summarize_text(content, engine)

            file_blocks.append(f"--- FILE: {name} ---\n{processed}\n--- END ---")
        return "\n\n".join(file_blocks)

    def _extract_structure(self, content: str, ext: str) -> str:
        if len(content) < 1000: return content 
        
        if ext == "py":
            try:
                tree = ast.parse(content)
                defs = []
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        line = content.splitlines()[node.lineno-1].strip()
                        defs.append(line + " ...")
                return "\n".join(defs) if defs else "Content: [Code Logic]"
            except: return content[:800] + "\n[Syntax Error in Summary]"
        
        return content[:800] + "\n[Truncated for context]"

    def _summarize_json(self, content: str) -> str:
        try:
            data = json.loads(content)
            if isinstance(data, dict): return f"Keys: {list(data.keys())}"
            return "Valid JSON structure"
        except: return "Invalid JSON"

    def _summarize_text(self, content: str, engine) -> str:
        if len(content) < 500: return content
        prompt = f"<|im_start|>system\n{PrLib.SUMMARIZE_TEXT}<|im_end|>\n" \
             f"<|im_start|>user\n{content[:1500]}<|im_end|>\n<|im_start|>assistant\n"
        return engine.generate(prompt, max_tokens=20)["text"].strip()