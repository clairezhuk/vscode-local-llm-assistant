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
    # Improved extraction logic to handle multiple blocks and Architect assembly
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
                print(f"Error reading file {rel_path}: {e}")
    return assets

def run_isolated_code(ai_code: str, asserts: list, context_data: list = None) -> tuple[bool, str]:
    if not ai_code: 
        return False, "No code block found"
    
    indented_asserts = "".join([f"        {line}\n" for line in asserts]) if isinstance(asserts, list) else f"        {asserts}\n"

    full_code = (
        f"{ai_code}\n\n"
        f"def __run_benchmark_test():\n"
        f"    try:\n"
        f"{indented_asserts}"
        f"        print('TESTS_PASSED')\n"
        f"    except AssertionError as e:\n"
        f"        print(f'ASSERT_FAIL: {{e or \"Logic error\"}}')\n"
        f"    except Exception as e:\n"
        f"        print(f'RUNTIME_ERROR: {{type(e).__name__}}: {{e}}')\n"
        f"if __name__ == '__main__':\n"
        f"    __run_benchmark_test()"
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        if context_data:
            for file_info in context_data:
                file_path = os.path.join(tmpdir, file_info['name'])
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(file_info['content'])

        script_path = os.path.join(tmpdir, "test_executor.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)
            
        try:
            result = subprocess.run(["python", script_path], cwd=tmpdir, capture_output=True, text=True, timeout=15)
            output = result.stdout + result.stderr
            if "TESTS_PASSED" in output: return True, "Passed"
            if "ASSERT_FAIL:" in output: 
                match = re.search(r'ASSERT_FAIL: (.*)', output)
                return False, match.group(1).strip() if match else "Logic error"
            if "RUNTIME_ERROR:" in output: 
                match = re.search(r'RUNTIME_ERROR: (.*)', output)
                return False, match.group(1).strip() if match else "Runtime error"
            return False, f"Python Error: {result.stderr.strip().splitlines()[-1]}" if result.stderr else "Execution Failure"
        except subprocess.TimeoutExpired:
            return False, "Timeout"

def run_benchmarks(target_suites: list = None, limit: int = None, mode_filter: str = None):
    test_files = [Path(f"{SUITES_DIR}/{name}.json") for name in target_suites] if target_suites else list(Path(SUITES_DIR).glob("*.json"))
    
    # MODIFIED: Define which modes to iterate over
    selected_modes = [mode_filter] if mode_filter else ["fast", "thinking"]
    
    for file_path in test_files:
        suite_name = file_path.stem
        results = []
        if not file_path.exists():
            print(f"File not found: {file_path}")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            suite = json.load(f)
            
        print(f"\n>>> Suite: {suite_name}")
        for test in (suite[:limit] if limit else suite):
            for mode in selected_modes:
                print(f"[{test['id']}] Mode: {mode} | {test.get('description', '')}")
                context_data = load_context_assets(test.get("context_files", []))
                
                with tempfile.TemporaryDirectory() as simulated_workspace:
                    payload = {
                        "query": test['query'],
                        "context": {
                            "attached_files": context_data,
                            "intent": test['expected_intent'],
                            "mode": mode,
                            "workspace_path": simulated_workspace
                        }
                    }

                    ai_text = ""
                    tokens = 0
                    start_time = time.time()
                    try:
                        # Streaming support for JSON chunks
                        with requests.post(API_URL, json=payload, timeout=150, stream=True) as r:
                            for line in r.iter_lines():
                                if line:
                                    data = json.loads(line)
                                    if data.get("type") == "chunk":
                                        ai_text += data.get("content", "")
                                    if data.get("usage"):
                                        tokens = data["usage"].get("total_tokens", 0)
                        elapsed = time.time() - start_time
                    except Exception as e:
                        print(f"  ⚠️ Request Failed: {e}")
                        continue

                    metrics = test.get("metrics", {})
                    must_contain = metrics.get("must_contain", [])
                    must_not_contain = metrics.get("must_not_contain", [])
                    format_ok = all(w.lower() in ai_text.lower() for w in must_contain) and \
                                all(w.lower() not in ai_text.lower() for w in must_not_contain)
                                
                    exec_ok, exec_msg = (None, "N/A")
                    if test['type'] == "code" and "execution" in metrics:
                        code = extract_code(ai_text)
                        exec_ok, exec_msg = run_isolated_code(code, metrics["execution"].get("run_tests", []), context_data)
                    
                    result_row = {
                        "id": test['id'],
                        "processing_type": mode,
                        "time_s": round(elapsed, 2),
                        "intent": test['expected_intent'],
                        "format_ok": format_ok,
                        "exec_ok": exec_ok,
                        "exec_msg": exec_msg,
                        "tokens": tokens
                    }
                    results.append(result_row)
                    
                    status_icon = "✅" if (format_ok and (exec_ok is not False)) else "❌"
                    print(f"  {status_icon} {mode.upper()} done in {round(elapsed, 1)}s. Result: {exec_msg}")

                    if status_icon == "❌":
                        log_name = f"fail_{test['id']}_{mode}.log"
                        with open(os.path.join(LOGS_DIR, log_name), "w", encoding="utf-8") as lf:
                            lf.write(f"QUERY: {test['query']}\nERROR: {exec_msg}\n\nAI RESPONSE:\n{ai_text}")

        if results:
            csv_path = os.path.join(RESULTS_DIR, f"{suite_name}.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)

if __name__ == "__main__":
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("suites", nargs="*")
    parser.add_argument("-n", "--limit", type=int, default=None)
    # MODIFIED: Added mode filter argument
    parser.add_argument("-t", "--type", choices=["fast", "thinking"], default=None, 
                        help="Select mode to run: fast or thinking. Leave empty for both.")
    
    args = parser.parse_args()
    
    run_benchmarks(
        target_suites=args.suites if args.suites else None, 
        limit=args.limit,
        mode_filter=args.type
    )