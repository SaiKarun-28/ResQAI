import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
RESOURCES_FILE_PATH = BASE_DIR / "data" / "resources.json"

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or ""

# LLM Selection
# Current Google AI Studio model names (as of 2025):
# - gemini-3.8-flash: Latest Flash model
# - gemini-3.5-flash-lite: Lightweight Flash model (recommended for cost/performance)
# - gemini-3.1-flash-lite: Earlier lightweight model
# Note: gemini-1.5 and gemini-2.0 series are deprecated/shut down
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Provider detection
if GEMINI_API_KEY:
    ACTIVE_PROVIDER = "gemini"
elif GROQ_API_KEY:
    ACTIVE_PROVIDER = "groq"
else:
    ACTIVE_PROVIDER = "deterministic_fallback"

# Orchestrator & Server Settings
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "20.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "1"))
PORT = int(os.getenv("PORT", "8000"))

# Allowed CORS origins
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "*",
]