import argparse
import json
import requests
import time
import csv
import os
import re
import subprocess
import tempfile
from pathlib import Path

API_URL = "http://127.0.0.1:8000/chat"
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
SUITES_DIR = "suites"
RESULTS_DIR = "results"
LOGS_DIR = os.path.join(RESULTS_DIR, "logs")

def extract_code(text: str) -> str:
    blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
    if blocks:
        return blocks[-1].strip() 
    inline_match = re.search(r'`(.*?)`', text, re.DOTALL)
    return inline_match.group(1).strip() if inline_match else ""

def load_context_assets(file_paths: list) -> list:
    assets = []
    for rel_path in file_paths:
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            try:
                content = full_path.read_text(encoding='utf-8')
                assets.append({"name": full_path.name, "content": content})
            except Exception as e:
                print(f"Error reading asset {rel_path}: {e}")
    return assets

def run_isolated_code(ai_code: str, asserts: list, context_data: list = None) -> tuple[bool, str]:
    if not ai_code: return False, "No code block"
    indented_asserts = "".join([f"        {line}\n" for line in asserts]) if isinstance(asserts, list) else f"        {asserts}\n"
    full_code = f"{ai_code}\n\ndef __run_test():\n    try:\n{indented_asserts}        print('PASSED')\n    except AssertionError as e:\n        print(f'FAIL: {{e}}')\n    except Exception as e:\n        print(f'ERROR: {{type(e).__name__}}: {{e}}')\nif __name__ == '__main__': __run_test()"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        if context_data:
            for file_info in context_data:
                p = os.path.join(tmpdir, file_info['name'])
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f: f.write(file_info['content'])
        
        script_p = os.path.join(tmpdir, "exec.py")
        with open(script_p, "w", encoding="utf-8") as f: f.write(full_code)
        try:
            res = subprocess.run(["python", script_p], cwd=tmpdir, capture_output=True, text=True, timeout=15)
            out = res.stdout + res.stderr
            if "PASSED" in out: return True, "Passed"
            if "FAIL:" in out: return False, re.search(r'FAIL: (.*)', out).group(1).strip()
            if "ERROR:" in out: return False, re.search(r'ERROR: (.*)', out).group(1).strip()
            return False, "Exec failed"
        except subprocess.TimeoutExpired: return False, "Timeout"

def run_benchmarks(target_suites: list = None, limit: int = None, mode_filter: str = None):
    test_files = [Path(f"{SUITES_DIR}/{n}.json") for n in target_suites] if target_suites else list(Path(SUITES_DIR).glob("*.json"))
    selected_modes = [mode_filter] if mode_filter else ["fast", "thinking"]
    
    for file_path in test_files:
        suite_name = file_path.stem
        csv_path = os.path.join(RESULTS_DIR, f"{suite_name}.csv")
        
        # CHANGED: Check existing file status
        file_existed = os.path.isfile(csv_path)
        if file_existed:
            with open(csv_path, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
            print(f"⚠️ Warning: {csv_path} already exists with {line_count} lines. Appending results.")

        with open(file_path, "r", encoding="utf-8") as f:
            suite = json.load(f)
            
        print(f"\n>>> Running Suite: {suite_name}")
        for test in (suite[:limit] if limit else suite):
            for mode in selected_modes:
                print(f"[{test['id']}] {mode.upper()} mode...", end=" ", flush=True)
                ctx_data = load_context_assets(test.get("context_files", []))
                
                with tempfile.TemporaryDirectory() as workspace:
                    payload = {
                        "query": test['query'],
                        "context": {
                            "attached_files": ctx_data,
                            "intent": test['expected_intent'],
                            "mode": mode,
                            "workspace_path": workspace
                        }
                    }

                    ai_text, start_time = "", time.time()
                    try:
                        with requests.post(API_URL, json=payload, timeout=180, stream=True) as r:
                            for line in r.iter_lines():
                                if line:
                                    data = json.loads(line)
                                    # CHANGED: Enhanced token & content capture
                                    if data.get("type") == "chunk":
                                        ai_text += data.get("content", "")
                        elapsed = time.time() - start_time
                    except Exception as e:
                        print(f"Failed: {e}")
                        continue

                    # CHANGED: Detect AI Warnings
                    has_warning = any(marker in ai_text for marker in ["⚠️", "AI Warning", "Warning:"])
                    
                    metrics = test.get("metrics", {})
                    format_ok = all(w.lower() in ai_text.lower() for w in metrics.get("must_contain", []))
                    
                    exec_ok, exec_msg = (None, "N/A")
                    if test['type'] == "code" and "execution" in metrics:
                        code = extract_code(ai_text)
                        exec_ok, exec_msg = run_isolated_code(code, metrics["execution"].get("run_tests", []), ctx_data)
                    
                    result_row = {
                        "id": test['id'],
                        "processing_type": mode,
                        "time_s": round(elapsed, 2),
                        "intent": test['expected_intent'],
                        "format_ok": format_ok,
                        "exec_ok": exec_ok,
                        "exec_msg": exec_msg,
                        "warning": has_warning
                    }
                    
                    # CHANGED: Write to CSV in real-time
                    file_is_empty = not os.path.exists(csv_path) or os.stat(csv_path).st_size == 0
                    with open(csv_path, "a", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=result_row.keys())
                        if file_is_empty:
                            writer.writeheader()
                        writer.writerow(result_row)
                    
                    status = "✅" if (format_ok and (exec_ok is not False)) else "❌"
                    warn_str = " (with ⚠️)" if has_warning else ""
                    print(f"{status}{warn_str} {round(elapsed, 1)}s. {exec_msg}")

                    if status == "❌":
                        with open(os.path.join(LOGS_DIR, f"fail_{test['id']}_{mode}.log"), "w", encoding="utf-8") as lf:
                            lf.write(f"ERROR: {exec_msg}\nRESPONSE:\n{ai_text}")

if __name__ == "__main__":
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("suites", nargs="*")
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("-t", "--type", choices=["fast", "thinking"], default=None)
    args = parser.parse_args()
    run_benchmarks(args.suites if args.suites else None, args.limit, args.type)