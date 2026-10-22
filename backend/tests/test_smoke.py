"""
Smoke tests for AI Coder Agent backend.

These tests verify the application runs without complex AI logic
and without downloading the model into VRAM. All LLM interactions
are mocked.
"""

import os
import sys
import json
from unittest.mock import patch, MagicMock

# Ensure backend root is on the path so `main` and `src` are importable
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# ---------------------------------------------------------------------------
# Mock LLMEngine BEFORE importing the FastAPI app, because routes.py creates
# Orchestrator() at module import time, which instantiates LLMEngine() and
# would load the ~1GB GGUF model into VRAM.
# ---------------------------------------------------------------------------
mock_engine = MagicMock()
mock_engine.generate.return_value = {"text": "mocked llm response", "usage": {}}
mock_engine.generate_stream.return_value = iter(["mocked ", "streamed ", "response"])
mock_engine.save_state.return_value = b"mock_kv_state"
mock_engine.load_state.return_value = None

with patch("src.engine.llm.LLMEngine", return_value=mock_engine):
    from main import app  # noqa: E402
    from src.api_router.routes import orchestrator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app)

# Model path resolved the same way as backend/src/engine/llm.py:
TEST_DIR = os.path.dirname(os.path.abspath(__file__))  # backend/tests/
ENGINE_DIR = os.path.join(TEST_DIR, "..", "src", "engine")  # backend/src/engine/
MODEL_PATH = os.path.abspath(
    os.path.join(ENGINE_DIR, "../../models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
)


# ---------------------------------------------------------------------------
# 1) Application startup check
# ---------------------------------------------------------------------------
def test_app_starts():
    """The FastAPI application starts without errors (LLM is mocked)."""
    assert app is not None
    assert app.title == "FastAPI"
    routes = [r.path for r in app.routes]
    assert "/chat" in routes
    assert "/completion" in routes
    assert "/command-confirm" in routes

    response = client.post(
        "/chat",
        json={"query": "hello", "context": {"intent": 1, "mode": "fast"}},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2) Model availability check
# ---------------------------------------------------------------------------
def test_model_available():
    """The GGUF model file exists, is a file, and is readable."""
    assert os.path.exists(MODEL_PATH), f"Model not found at {MODEL_PATH}"
    assert os.path.isfile(MODEL_PATH), f"Model path is not a file: {MODEL_PATH}"
    assert os.access(MODEL_PATH, os.R_OK), f"Model file is not readable: {MODEL_PATH}"


# ---------------------------------------------------------------------------
# 3) E2E integration flow check (mocked LLM, no VRAM)
# ---------------------------------------------------------------------------
def _collect_ndjson_chunks(response):
    """Collect all chunks from a streaming NDJSON response."""
    chunks = []
    for line in response.iter_lines():
        if line:
            chunks.append(json.loads(line))
    return chunks


def _make_chat_context(intent: int, mode: str = "fast", attached_files=None):
    return {
        "intent": intent,
        "mode": mode,
        "attached_files": attached_files or [],
        "workspace_path": os.getcwd(),
    }


# --- chat: fast mode ---
def _run_chat_fast(intent: int):
    response = client.post(
        "/chat",
        json={"query": "prompt", "context": _make_chat_context(intent, "fast")},
    )
    assert response.status_code == 200
    chunks = _collect_ndjson_chunks(response)
    assert len(chunks) > 0


def _run_chat_thinking(intent: int):
    response = client.post(
        "/chat",
        json={"query": "prompt", "context": _make_chat_context(intent, "thinking")},
    )
    assert response.status_code == 200
    chunks = _collect_ndjson_chunks(response)
    assert len(chunks) > 0


# --- ghost ---
def _run_ghost():
    response = client.post("/completion", json={"prompt": "def hello(): "})
    assert response.status_code == 200
    data = response.json()
    assert "text" in data


# --- stop button ---
def _run_stop_accept():
    orchestrator.pending_command = {"cmd": "echo hello", "cwd": os.getcwd()}
    response = client.post("/command-confirm", json={"action": "accept"})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data


def _run_stop_reject():
    orchestrator.pending_command = {"cmd": "rm -rf /", "cwd": os.getcwd()}
    response = client.post("/command-confirm", json={"action": "reject"})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert orchestrator.pending_command is None


# ---------------------------------------------------------------------------
# Full E2E suite
# ---------------------------------------------------------------------------
def test_e2e_chat_and_ghost_and_stop():
    """Run all E2E flows: chat fast/thinking x learn/code/terminal, ghost, stop."""
    # Fast mode: learn, code, terminal
    for intent in [1, 2, 3]:
        _run_chat_fast(intent)
    # Thinking mode: learn, code, terminal
    for intent in [1, 2, 3]:
        _run_chat_thinking(intent)
    # Ghost
    _run_ghost()
    # Stop button accept
    _run_stop_accept()
    # Stop button reject
    _run_stop_reject()

test_app_starts()
test_model_available()
test_e2e_chat_and_ghost_and_stop()