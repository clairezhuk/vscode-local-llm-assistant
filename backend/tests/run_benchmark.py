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
REPEATS = 3

def extract_code(text: str) -> str:
    blocks = re.findall(r'```(?:\w+)?\s*\n?(.*?)\n?```', text, re.DOTALL | re.IGNORECASE)
    clean_blocks = [b.strip() for b in blocks if b.strip() and "### Attempt" not in b]
    if clean_blocks:
        return clean_blocks[-1] 
    if blocks:
        return blocks[-1].strip()
    inline_match = re.search(r'`(.*?)`', text, re.DOTALL)
    return inline_match.group(1).strip() if inline_match else ""

def load_context_assets(file_paths: list) -> list:
    assets = []
    for rel_path in file_paths:
        if ".." in rel_path or rel_path.startswith("/") or ":" in rel_path:
             print(f"Illegal path ignored: {rel_path}")
             continue
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists() and full_path.is_relative_to(PROJECT_ROOT):
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
                with open(p, "w", encoding="utf-8") as f: f.write(file_info['content'])
        
        script_p = os.path.join(tmpdir, "exec.py")
        with open(script_p, "w", encoding="utf-8") as f: f.write(full_code)
        try:
            res = subprocess.run([
                "docker", "run", "--rm", 
                "-v", f"{Path(tmpdir).absolute()}:/app", 
                "-w", "/app",                           
                "--network", "none",                    
                "--memory", "128m",                     
                "ai-benchmark-runner",                     
                "python", "exec.py"                     
            ], capture_output=True, text=True, timeout=20)
            out = res.stdout + res.stderr
            if "PASSED" in out: return True, "Passed"
            if "ERROR:" in out: return False, out.split("ERROR:")[1].strip()
            return False, out.strip() or "Exec failed"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, f"Docker Error: {e}"
        
def run_isolated_shell(ai_cmd: str, verify_script: str, context_data: list = None) -> tuple[bool, str]:
    if not ai_cmd: return False, "No command found"
    ai_cmd = ai_cmd.strip().replace('$', '') 
    full_script = verify_script.replace("{COMMAND}", ai_cmd)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        if context_data:
            for file_info in context_data:
                p = os.path.join(tmpdir, file_info['name'])
                with open(p, "w", encoding="utf-8") as f: f.write(file_info['content'])
        
        script_p = os.path.join(tmpdir, "test.sh")
        with open(script_p, "w", encoding="utf-8") as f: f.write(full_script)
        
        try:
            res = subprocess.run([
                "docker", "run", "--rm", 
                "-v", f"{Path(tmpdir).absolute()}:/app", 
                "-w", "/app",                           
                "--network", "none",                    
                "ai-benchmark-runner",                     
                "sh", "test.sh"                     
            ], capture_output=True, text=True, timeout=15)
            
            if res.returncode == 0:
                return True, "Passed"
            else:
                return False, res.stderr or res.stdout or f"Exit code {res.returncode}"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, f"Docker Error: {e}"

def run_benchmarks(target_suites: list = None, limit: int = None, mode_filter: str = None):
    test_files = [Path(f"{SUITES_DIR}/{n}.json") for n in target_suites] if target_suites else list(Path(SUITES_DIR).glob("*.json"))
    selected_modes = [mode_filter] if mode_filter else ["fast", "thinking"]
    
    for file_path in test_files:
        suite_name = file_path.stem
        csv_path = os.path.join(RESULTS_DIR, f"{suite_name}.csv")
        
        # Check existing file status
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
                print(f"[{test['id']}] {mode.upper()} mode:", end=" ", flush=True)

                log_path = os.path.join(LOGS_DIR, f"fail_{test['id']}_{mode}.log")
                if os.path.exists(log_path):
                    os.remove(log_path)

                agg_format_ok = 0
                agg_exec_ok = 0 if "execution" in test.get("metrics", {}) else None
                agg_warnings = 0
                agg_wrong_warnings = 0
                total_elapsed = 0 
                agg_success_attempts = 0
                ctx_data = load_context_assets(test.get("context_files", []))

                for r_idx in range(REPEATS):
                    print(f"{r_idx+1}/{REPEATS}...", end="", flush=True)
                
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
                                        # Enhanced token & content capture
                                        if data.get("type") == "chunk":
                                            ai_text += data.get("content", "")
                            elapsed = time.time() - start_time
                            total_elapsed += elapsed
                        except Exception as e:
                            print(f"Failed: {e}")
                            continue

                        # Detect AI Warnings
                        has_warning = any(marker in ai_text for marker in ["⚠️", "AI Warning", "Warning:"])
                        metrics = test.get("metrics", {})
                        format_ok = all(w.lower() in ai_text.lower() for w in metrics.get("must_contain", []))
                        
                        current_exec_ok = None
                        if "execution" in metrics:
                            code = extract_code(ai_text)
                            if test['type'] == "code":
                                current_exec_ok, _ = run_isolated_code(code, metrics["execution"].get("run_tests", []), ctx_data)
                            elif test['type'] == "cli":
                                current_exec_ok, _ = run_isolated_shell(code, metrics["execution"].get("verify_cmd", ""), ctx_data)
                        if format_ok: agg_format_ok += 1
                        if current_exec_ok: agg_exec_ok += 1
                        if has_warning: agg_warnings += 1

                        is_actually_correct = format_ok and (current_exec_ok is not False)
                        if is_actually_correct:
                            agg_success_attempts += 1
                            if has_warning:
                                agg_wrong_warnings += 1

                        if not is_actually_correct:
                            with open(log_path, "a", encoding="utf-8") as lf:
                                lf.write(f"\n--- ATTEMPT {r_idx+1}/{REPEATS} FAILED ---\n")
                                lf.write(f"REASON: Format={format_ok}, Exec={current_exec_ok}\n")
                                lf.write(f"AI RESPONSE:\n{ai_text}\n" + "-"*30)    

                        status = "✅" if (is_actually_correct) else "❌"
                        warn_str = " (with ⚠️)" if has_warning else ""
                        print(f"{status}{warn_str} {round(elapsed, 1)}s.")               
                    
                result_row = {
                    "id": test['id'],
                    "processing_type": mode,
                    "time_s": round(total_elapsed, 2),
                    "intent": test['expected_intent'],
                    "format_ok": agg_format_ok,
                    "exec_ok": agg_exec_ok if agg_exec_ok is not None else "",
                    "warning": agg_warnings,
                    "wrong_warnings": agg_wrong_warnings,
                    "repeats": REPEATS
                }
                    
                # Write to CSV in real-time
                file_is_empty = not os.path.exists(csv_path) or os.stat(csv_path).st_size == 0
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=result_row.keys())
                    if file_is_empty:
                        writer.writeheader()
                    writer.writerow(result_row)
                    
                    


if __name__ == "__main__":
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("suites", nargs="*")
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("-t", "--type", choices=["fast", "thinking"], default=None)
    args = parser.parse_args()
    run_benchmarks(args.suites if args.suites else None, args.limit, args.type)