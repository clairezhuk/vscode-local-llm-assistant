import subprocess

class ToolExecutor:
    def execute_command(self, command: str) -> str:
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return str(e)