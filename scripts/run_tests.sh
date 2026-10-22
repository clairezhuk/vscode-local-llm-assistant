#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Smoke test runner for AI Coder Agent backend
#
# Runs backend/tests/test_smoke.py which verifies the application starts,
# the model file is available, and the E2E integration flow works with a
# mocked LLM (no VRAM, no real generation).
#
# Designed to be run locally or in CI (GitHub Actions).
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "=============================================="
echo "  AI Coder Agent — Smoke Tests"
echo "=============================================="
echo "Project root: $PROJECT_ROOT"
echo "Backend dir:  $BACKEND_DIR"
echo

# --- Pre-flight checks -------------------------------------------------------

if ! command -v python &> /dev/null; then
    echo "ERROR: python not found in PATH"
    exit 1
fi

if ! python -m pytest --version &> /dev/null; then
    echo "ERROR: pytest not found. Install with: pip install pytest"
    exit 1
fi

if ! python -c "from fastapi.testclient import TestClient" &> /dev/null; then
    echo "ERROR: fastapi not installed."
    echo "       Install backend dependencies: pip install -r backend/requirements.txt"
    exit 1
fi

# --- Run smoke tests ---------------------------------------------------------

cd "$BACKEND_DIR"

echo "Running smoke tests from $BACKEND_DIR..."
echo "----------------------------------------------"

python -m pytest tests/test_smoke.py -v --tb=short "$@"

echo
echo "=============================================="
echo "  Smoke tests complete"
echo "=============================================="
