import os
import sys

# The api container imports flat (`from config import settings`, `from routers...`).
# Add api/ to sys.path so tests import the same way runtime does, and set the
# required env vars up front so `config.Settings()` (which has no defaults for
# database_url/api_key/jwt_secret) can be constructed at import time.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
