### Project Evolution Roadmap

#### Phase 1: UI/UX & Transparency (Frontend Focus)
*   **Manual Intent Control:** Add a dropdown/toggle in the Chat Webview: `[Auto | Theory | Code | Terminal]`.
*   **Mode Selector:** Add a toggle for `[Fast | Thinking]`.
    *   *Fast:* Direct prompt -> response.
    *   *Thinking:* Preprocessor -> Planner -> Generation -> Runtime Fix.
*   **Step Visualization:** 
    *   If "Thinking" is active, show an accordion/collapsible UI element: *"Planning..."* -> *"Verifying..."* -> *"Correcting (Attempt 1)..."*.
*   **Interrupt Mechanism:** Implement an `AbortController` in the backend and a "Stop" button in the VS Code UI to kill the `llama.cpp` process.

#### Phase 2: Advanced Logic & Reliability (Backend Focus)
*   **Runtime Self-Correction:**
    *   Create an isolated `sandbox_executor.py`. 
    *   It should run the generated code (using `subprocess` or `exec()`), catch `RuntimeError`, `TypeError`, etc.
    *   Feed the **Traceback** back into the Orchestrator for a "Correction Cycle."
*   **Optimized Fill-In-The-Middle (FIM):**
    *   Update `ghost_text.ts` to use `<|fim_prefix|>`, `<|fim_suffix|>`, and `<|fim_middle|>` tokens properly.
    *   Implement **Debouncing** (wait 300ms of no typing before calling the API) to save resources.

#### Phase 3: Context Awareness (RAG & Search)
*   **TF-IDF Search Engine:** 
    *   Index local files. When a query is asked, find the top 3 most relevant code snippets.
    *   Inject these snippets into the "Context" section of the prompt.
*   **Project Graph:** Briefly map project structure so the AI knows that `main.py` depends on `utils.py`.

#### Phase 4: Quality Assurance (Testing Suite)
*   **Component Unit Testing:** 
    *   Test `FileProcessor` with broken files.
    *   Test `Orchestrator.classify_intent` with a set of "Tricky" prompts.
*   **Integration Benchmarks:** 
    *   "Quality over Quantity": 20 high-quality tasks that cover logic, CLI, and multi-step refactoring.
*   **LLM-as-a-Judge:** 
    *   Use a larger model (e.g., GPT-4o or Claude 3.5 via API) to automatically grade the responses of your local 1.5B model.
*   **Session Simulation:** 
    *   Automated scripts that simulate a conversation: "Write a function" -> "Now add a docstring" -> "Now write a test for it."

---

### Revised Architecture Diagram (Logical Flow)

1.  **Input:** User Query + Mode (Fast/Thinking) + Intent (Auto/Manual).
2.  **Context:** RAG (TF-IDF) + Active File + Attached Files.
3.  **Thinking Pipeline (If enabled):**
    *   `Planner` -> Generate JSON steps.
    *   `Generator` -> Draft code.
    *   `Static Check` -> Check AST/Syntax.
    *   `Runtime Check` -> Execute in sandbox, catch Traceback.
    *   `Final Polishing` -> Format Markdown.
4.  **Output:** Result + Plan + Error Logs (visible in UI).

### Key Technical Goal for you:
**Keep the "Thinking" mode modular.** If the user is just asking "What is a decorator?", the system should be smart enough (or the user can toggle it) to bypass the Planner and Sandbox to save time and battery.