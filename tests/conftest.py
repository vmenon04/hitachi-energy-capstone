"""
Root conftest: runs before any test collection.

Sets the minimum environment variables required by src/main.py and
src/agents/agents.py at import time (they use os.environ[...] at module level),
then adds src/ to sys.path so that main.py's non-prefixed imports
(e.g. ``from utils.logging_utils import ...``) resolve correctly.

To prevent the "dual-module" problem, where the same .py file gets loaded
twice under two different names (``src.utils.logging_utils`` AND
``utils.logging_utils``) causing isinstance() checks to fail, we eagerly
import the key src.* modules and then alias them in sys.modules under their
non-prefixed names.  main.py's top-level imports then find the aliases in
sys.modules and skip re-loading, so both name variants always reference the
same module and class objects.
"""

import importlib
import os
import sys
from pathlib import Path

# ── environment variables ─────────────────────────────────────────────────────
# Use setdefault so real values from .env or the shell take precedence.
os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "DefaultEndpointsProtocol=https;AccountName=testaccount;AccountKey=dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXRlc3RrZXk=;EndpointSuffix=core.windows.net")
os.environ.setdefault("AZURE_STORAGE_CONTAINER_NAME", "test-container")
os.environ.setdefault("AZURE_AI_PROJECT_ENDPOINT", "https://test.openai.azure.com/")
os.environ.setdefault("AZURE_AI_PROJECT_API_KEY", "test-api-key-for-tests")

# ── sys.path ──────────────────────────────────────────────────────────────────
# src/main.py uses bare (non-src.-prefixed) imports such as
#   from utils.logging_utils import ...
#   from agents.agents import ...
# Adding src/ to sys.path makes those resolve to the correct packages
# without affecting the existing ``from src.xxx import ...`` style used by
# the unit tests.
_src_dir = str(Path(__file__).parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# ── sys.modules aliasing ──────────────────────────────────────────────────────
# Import src.utils sub-modules eagerly so they are registered under their
# canonical ``src.*`` names first.  Then mirror them under their bare names so
# that when main.py executes ``from utils.logging_utils import setup_logger``,
# Python finds the SAME module object in sys.modules instead of loading a
# second copy.  This is only needed for modules whose classes are checked with
# isinstance() across test files.
importlib.import_module("src.utils.logging_utils")
importlib.import_module("src.utils.data_utils")

sys.modules.setdefault("utils", sys.modules.get("src.utils"))
sys.modules.setdefault("utils.logging_utils", sys.modules["src.utils.logging_utils"])
sys.modules.setdefault("utils.data_utils", sys.modules["src.utils.data_utils"])
