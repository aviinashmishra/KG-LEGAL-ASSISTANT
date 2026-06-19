import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force tests onto local fallbacks so they never hit paid/live providers from .env.
# (env vars take precedence over the .env file in pydantic-settings)
for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "NEO4J_URI", "NEO4J_PASSWORD",
           "QDRANT_URL", "QDRANT_API_KEY", "COHERE_API_KEY", "REDIS_URL", "LANGSMITH_API_KEY"):
    os.environ[_k] = ""

# Use an isolated test database + deterministic secrets BEFORE the app imports settings.
_TEST_DB = ROOT / "data" / "test_app.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["RATE_LIMIT_PER_MIN"] = "100000"  # don't throttle tests

# fresh DB each test session
if _TEST_DB.exists():
    _TEST_DB.unlink()
