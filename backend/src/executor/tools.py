import subprocess
import os

class ToolExecutor:
    def execute_command(self, command: str, cwd: str = None) -> str:
        try:
            target_cwd = cwd if cwd and os.path.exists(cwd) else os.getcwd()
            
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=15,
                cwd=target_cwd 
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            if result.returncode == 0:
                return output if output else "Success (no output)"
            else:
                return error if error else f"Error (code {result.returncode})"
        except Exception as e:
            return f"Execution Error: {str(e)}"