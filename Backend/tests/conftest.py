"""Default tests are offline and never load developer credentials."""
import os
from unittest.mock import patch

import pytest

for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
    os.environ[key] = ""
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

# Also prevent file reads with dotenv versions predating PYTHON_DOTENV_DISABLED.
with patch("dotenv.load_dotenv", return_value=False):
    from app import config


@pytest.fixture(autouse=True)
def offline_isolated_backend(monkeypatch):
    from app.api import routes
    from app.orchestrator import workflow
    from app.tools import llm_client, resource_search
    from app.database import wipe_database

    wipe_database()
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.setenv(key, "")
    for module in (config, llm_client):
        monkeypatch.setattr(module, "GEMINI_API_KEY", "")
        monkeypatch.setattr(module, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "ACTIVE_PROVIDER", "deterministic_fallback")
    monkeypatch.setattr(routes, "ACTIVE_PROVIDER", "deterministic_fallback")
    # Tests may explicitly replace these with failure stubs, never live providers.
    monkeypatch.setattr(llm_client, "call_gemini_api", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_client, "call_groq_api", lambda *args, **kwargs: None)
    store = workflow.IncidentStore()
    monkeypatch.setattr(workflow, "incident_store", store)
    monkeypatch.setattr(routes, "incident_store", store)
    monkeypatch.setattr(resource_search, "_RESOURCES_CACHE", None)
    return store
