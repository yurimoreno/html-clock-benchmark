import os
import sys

# Make the repo root importable so tests can `import benchmark_system.runner`
# and `import add_model` regardless of where pytest is invoked from.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
