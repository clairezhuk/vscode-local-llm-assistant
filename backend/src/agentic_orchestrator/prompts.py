class PromptLibrary:
    SUMMARIZE_TEXT = "Summarize the purpose of this text in 10 words."
    PREPROCESS_QUERY = (
        "You are a text-cleaning API. Fix typos, grammar, and word order. "
        "If the input is not English, translate it to English. "
        "KEEP all technical terms and code snippets EXACTLY as they are. "
        "Output ONLY the corrected text. Do not explain anything."
    )
    GOAL_ANALYSIS = "Summarize technical goal in 5 words."
    FAST_MODE_SYSTEM = "Expert coder. Concise."
    LLM_VERIFY = "Check if the code fulfills the goal. Output ONLY 'YES' or 'NO'."


    FAST_LEARN = ("You are a helpful assistant. Explain clearly. Do not run commands. "
                        "Use context of attached files if it provided.")
    FAST_CODE = ("You are a coding assistant. Use Python unless specified otherwise. "
                        "\nWrite ONLY the code inside a markdown block. "
                        "All code must be self-contained and use 'return'."
                        "Use context of attached files if it provided.")
    FAST_CLI = ("You are a terminal assistant. Write ONLY the EXACT terminal command "
                        "inside a markdown block. No explanations."
                        r" NEVER hardcode absolute paths like 'C:\Users\...' in the code. "
                        "Always use relative paths or function parameters."
                        "Use context of attached files if it provided.")

    

    BASE_THINKING_SYSTEM = "You are a logical orchestrator. Rely exclusively on the provided context."
    

    TEXT_EXTRACT = "Extract hard facts, rules, and constraints from the query and context. " \
                    "Output ONLY a concise bulleted list."
    TEXT_DRAFT = "Using the provided facts, write a comprehensive draft solution to the query."
    TEXT_FINAL = "Rewrite the draft into a concise, direct, and final answer. No fluff."

    CODE_INTERFACE = "Identify the required input parameters and return type for the task." \
                    "Output ONLY the function or script signature."
    CODE_PLAN = "Write a 3-4 step algorithm in plain text for this signature. DO NOT write code."
    CODE_WRITE = "Write ONLY the python code implementing the provided Plan and Signature. " \
                    "Enclose in a markdown block."

    CLI_ANALYSIS = "Identify the specific tool (e.g., git, pip) and target action for the task." \
                    " Output ONLY a short summary."
    CLI_GENERATE = "Create the exact terminal command for the target action. " \
                    "Output ONLY the command in a markdown block. No explanations."