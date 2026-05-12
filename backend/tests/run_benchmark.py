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
    match = re.search(r'```(?:python)?\s*\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    inline_match = re.search(r'`(.*?)`', text, re.DOTALL)
    if inline_match:
        return inline_match.group(1).strip()
        
    return ""

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
        else:
            print(f"File not found: {full_path}")
    return assets

def extract_cli(text: str) -> str:
    match = re.search(r'```(?:bash|sh|cmd)?\s*\n(.*?)\n```', text, re.DOTALL)
    return match.group(1).strip() if match else text.replace("`", "").strip()

def run_isolated_code(ai_code: str, asserts: list) -> tuple[bool, str]:
    if not ai_code: 
        return False, "No code block found (ensure AI outputs code in ```python blocks)"
    indented_asserts = ""
    if isinstance(asserts, list):
        for line in asserts:
            indented_asserts += f"        {line}\n"
    else:
        indented_asserts = f"        {asserts}\n"

    full_code = (
        f"{ai_code}\n\n"
        f"# --- AUTOMATED TESTS ---\n"
        f"def __run_benchmark_test():\n"
        f"    try:\n"
        f"{indented_asserts}"
        f"        print('TESTS_PASSED')\n"
        f"    except AssertionError as e:\n"
        f"        msg = str(e) if str(e) else 'Assertion failed'\n"
        f"        print(f'ASSERT_FAIL: {{msg}}')\n"
        f"    except Exception as e:\n"
        f"        print(f'RUNTIME_ERROR: {{type(e).__name__}}: {{e}}')\n"
        f"\n"
        f"if __name__ == '__main__':\n"
        f"    __run_benchmark_test()"
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "test_executor.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)
            
        try:
            result = subprocess.run(
                ["python", script_path], 
                cwd=tmpdir, 
                capture_output=True, 
                text=True, 
                timeout=12
            )
            output = result.stdout + result.stderr
            
            if "TESTS_PASSED" in output:
                return True, "Passed"
            
            if "ASSERT_FAIL:" in output:
                error_msg = re.search(r'ASSERT_FAIL: (.*)', output)
                return False, error_msg.group(1).strip() if error_msg else "Logic error"
                
            if "RUNTIME_ERROR:" in output:
                error_msg = re.search(r'RUNTIME_ERROR: (.*)', output)
                return False, error_msg.group(1).strip() if error_msg else "Runtime error"

            if result.returncode != 0:
                lines = result.stderr.strip().split('\n')
                return False, f"Python Error: {lines[-1]}"
                
            return False, "Process exited without result"
            
        except subprocess.TimeoutExpired:
            return False, "Execution Timeout (Infinite loop?)"
        
def run_isolated_cli(ai_cmd: str, verify_cmd: str) -> tuple[bool, str]:
    if not ai_cmd: return False, "No command generated"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(ai_cmd, shell=True, cwd=tmpdir, capture_output=True, timeout=10)
            verify = subprocess.run(verify_cmd, shell=True, cwd=tmpdir, capture_output=True, timeout=5)
            
            if verify.returncode == 0:
                return True, "Passed"
            return False, "Verification failed"
        except Exception as e:
            return False, str(e)

def run_benchmarks(target_suites: list = None, limit: int = None):
    if target_suites:
        test_files = [Path(f"suites/{name}.json") for name in target_suites] if target_suites else list(Path("suites").glob("*.json"))
    else:
        test_files = list(Path(SUITES_DIR).glob("*.json"))
    
    print(f"Found {len(test_files)} test suites to run.")
    
    for file_path in test_files:
        suite_name = file_path.stem
        results = []
        with open(file_path, "r", encoding="utf-8") as f:
            suite = json.load(f)
            
        print(f"\n>>> Running Suite: {suite_name}")
        for test in (suite[:limit] if limit else suite):
            print(f"[{test['id']}] {test.get('description', '')}")
            context_data = load_context_assets(test.get("context_files", []))
            try:
                start_time = time.time()
                resp = requests.post(API_URL, json={
                    "query": test['query'],
                    "context": {"attached_files": context_data}
                }, timeout=120).json()
                elapsed = time.time() - start_time
            except Exception as e:
                print(f"API Connection Error: {e}")
                continue

            ai_text = resp.get("result", "")
            actual_intent = resp.get("intent", 0)
            
            expected_intent = test['expected_intent']
            intent_match = (actual_intent == expected_intent)
            
            metrics = test.get("metrics", {})
            must_contain = metrics.get("must_contain", [])
            must_not_contain = metrics.get("must_not_contain", [])
            contains_req = all(word.lower() in ai_text.lower() for word in must_contain)
            forbidden_req = all(word.lower() not in ai_text.lower() for word in must_not_contain)
            format_ok = contains_req and forbidden_req
                        
            exec_ok, exec_msg = (None, "N/A")
            if test['type'] == "code" and "execution" in metrics:
                code = extract_code(ai_text)
                exec_ok, exec_msg = run_isolated_code(code, metrics["execution"].get("run_tests", []))
            
            result_row = {
                "id": test['id'],
                "type": test['type'],
                "time_s": round(elapsed, 2),
                "true_intent": expected_intent,
                "rec_intent": actual_intent,
                "intent_ok": intent_match,
                "format_ok": format_ok,
                "exec_ok": exec_ok,
                "exec_msg": exec_msg,
                "tokens": resp.get("usage", {}).get("total_tokens", 0)
            }
            results.append(result_row)
            
            if not (intent_match and format_ok and (exec_ok is not False)):
                print(f"  ❌ Failed: Intent:{intent_match}, Format:{format_ok}, Exec:{exec_msg}")
                with open(os.path.join(LOGS_DIR, f"fail_{test['id']}.log"), "w", encoding="utf-8") as lf:
                    lf.write(f"QUERY: {test['query']}\nERROR: {exec_msg}\n\nAI RESPONSE:\n{ai_text}")
            else:
                print(f"  ✅ Passed ({round(elapsed, 1)}s)")

        # CSV
        if results:
            keys = results[0].keys()
            csv_path = os.path.join(RESULTS_DIR, f"{suite_name}.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(results)
            print(f"Saved suite results to {csv_path}")

if __name__ == "__main__":
    os.makedirs(SUITES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    parser = argparse.ArgumentParser(description="Run AI Coder benchmarks.")
    parser.add_argument("suites", nargs="*", help="List of suite names to run (e.g. basic_algorithms). Leave empty for all.")
    parser.add_argument("-n", "--limit", type=int, default=None, help="Run only the first N tests from each suite.")
    
    args = parser.parse_args()
    
    target_suites = args.suites if args.suites else None
    
    run_benchmarks(target_suites=target_suites, limit=args.limit)