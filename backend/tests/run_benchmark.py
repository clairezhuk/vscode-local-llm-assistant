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
SUITES_DIR = "suites"
RESULTS_DIR = "results"
LOGS_DIR = os.path.join(RESULTS_DIR, "logs")

def extract_code(text: str) -> str:
    """Витягує код з markdown блоку"""
    match = re.search(r'```(?:python)?\s*\n(.*?)\n```', text, re.DOTALL)
    return match.group(1).strip() if match else ""

def extract_cli(text: str) -> str:
    """Витягує CLI команду"""
    match = re.search(r'```(?:bash|sh|cmd)?\s*\n(.*?)\n```', text, re.DOTALL)
    return match.group(1).strip() if match else text.replace("`", "").strip()

def run_isolated_code(ai_code: str, asserts: str) -> tuple[bool, str]:
    """Запускає згенерований код + тести у тимчасовій папці"""
    if not ai_code: return False, "No code generated"
    
    full_code = f"{ai_code}\n\n# --- Tests ---\n{asserts}"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "test_script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)
            
        try:
            result = subprocess.run(
                ["python", script_path], 
                cwd=tmpdir, 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                return True, "Passed"
            return False, result.stderr.split('\n')[-2] if result.stderr else "Runtime Error"
        except subprocess.TimeoutExpired:
            return False, "Timeout"

def run_isolated_cli(ai_cmd: str, verify_cmd: str) -> tuple[bool, str]:
    """Виконує команду терміналу і перевіряє результат"""
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
        test_files = [Path(SUITES_DIR) / f"{name}.json" for name in target_suites]
        test_files = [f for f in test_files if f.exists()]
    else:
        test_files = list(Path(SUITES_DIR).glob("*.json"))
    
    print(f"Found {len(test_files)} test suites to run.")
    
    for file_path in test_files:
        suite_name = file_path.stem
        results = []
        
        with open(file_path, "r", encoding="utf-8") as f:
            suite = json.load(f)
            
        if limit is not None and limit > 0:
            suite = suite[:limit]
            print(f"\n=== Starting Suite: {suite_name} (Limited to first {limit} tests) ===")
        else:
            print(f"\n=== Starting Suite: {suite_name} (All {len(suite)} tests) ===")
            
        for test in suite:
            print(f"Running [{test['id']}]...")
            start_time = time.time()
            
            try:
                response = requests.post(API_URL, json={
                    "query": test['query'], 
                    "context": {"attached_files": test.get("context_files", [])}
                }).json()
                
                ai_text = response.get("result", "")
                actual_intent = response.get("intent", 0)
            except Exception as e:
                print(f"API Error on {test['id']}: {e}")
                continue
                
            elapsed = time.time() - start_time
            metrics = test.get("metrics", {})
            
            # 1. Базові метрики (Text/Syntax)
            intent_match = (actual_intent == test['expected_intent'])
            must_contain = metrics.get("must_contain", [])
            contains_req = any(word.lower() in ai_text.lower() for word in must_contain) if must_contain else True
            no_forbidden = all(word.lower() not in ai_text.lower() for word in metrics.get("must_not_contain", []))            
            
            # 2. Метрики виконання (Execution)
            exec_success = None
            exec_msg = "N/A"
            
            if test['type'] == "code" and "execution" in metrics:
                code = extract_code(ai_text)
                exec_success, exec_msg = run_isolated_code(code, metrics["execution"]["run_tests"])
            elif test['type'] == "cli" and "execution" in metrics:
                cmd = extract_cli(ai_text)
                exec_success, exec_msg = run_isolated_cli(cmd, metrics["execution"]["verify_cmd"])
                
            result_row = {
                "id": test['id'],
                "type": test['type'],
                "time_s": round(elapsed, 2),
                "intent_ok": intent_match,
                "format_ok": contains_req and no_forbidden,
                "exec_ok": exec_success,
                "exec_msg": exec_msg,
                "tokens": response.get("usage", {}).get("total_tokens", 0)
            }
            results.append(result_row)
            
            # Логування невдач
            if not (intent_match and contains_req and no_forbidden and (exec_success is not False)):
                print(f"  ❌ Failed: {exec_msg if exec_success is False else 'Format/Intent mismatch'}")
                log_path = os.path.join(LOGS_DIR, f"log_{suite_name}_{test['id']}.txt")
                with open(log_path, "w", encoding="utf-8") as lf:
                    lf.write(f"Query: {test['query']}\n\nAI Output:\n{ai_text}")
            else:
                print("  ✅ Passed")

        # Запис у CSV після завершення сюїти
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