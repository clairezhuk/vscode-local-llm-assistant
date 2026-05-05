import ast
import json
import re

class FileProcessor:
    def __init__(self):
        self.storage = {}

    def process_files(self, files: list, engine) -> str:
        summaries = []
        for f in files:
            name = f.get("name", "unknown")
            content = f.get("content", "")
            self.storage[name] = content 
            
            ext = name.split('.')[-1].lower() if '.' in name else ''
            
            if ext == "py":
                summary = self._parse_py(content)
            elif ext == "json":
                summary = self._parse_json(content)
            elif ext in ["js", "ts", "cpp", "c", "java"]:
                summary = self._regex_code_parse(content)
            else:
                summary = self._summarize_text(content, engine)
                
            summaries.append(f"File: {name}\nContent Info:\n{summary}")
        
        return "\n\n".join(summaries)

    def _parse_py(self, content: str) -> str:
        try:
            tree = ast.parse(content)
            res = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef):
                    res.append(f"def {node.name}(...)")
                elif isinstance(node, ast.ClassDef):
                    res.append(f"class {node.name}:")
            return "\n".join(res) if res else "Scripts/Variables only."
        except Exception:
            return "Syntax Error in Python file."

    def _parse_json(self, content: str) -> str:
        try:
            d = json.loads(content)
            if isinstance(d, dict):
                return "Keys: " + ", ".join(d.keys())
            elif isinstance(d, list) and len(d) > 0:
                return f"List of {type(d[0]).__name__}"
            return "Valid JSON."
        except Exception:
            return "Invalid JSON."

    def _regex_code_parse(self, content: str) -> str:
        funcs = re.findall(r'(?:function\s+|const\s+|let\s+|var\s+)?([a-zA-Z0-9_]+)\s*(?:=|:)?\s*(?:function)?\s*\(', content)
        return "Detected signatures: " + ", ".join(set(funcs[:10]))

    def _summarize_text(self, content: str, engine) -> str:
        if len(content) < 500: 
            return content
        prompt = f"<|im_start|>system\nSummarize the core purpose of this text in 1 short sentence.<|im_end|>\n<|im_start|>user\n{content[:2000]}<|im_end|>\n<|im_start|>assistant\n"
        return engine.generate(prompt, max_tokens=32)["text"].strip()