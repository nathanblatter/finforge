import os
import sys

# The cron container has no package.json-style install step for itself — each
# module is imported flat (see other cron/*.py files: `from db import ...`).
# Add the cron/ directory to sys.path so `import charge_guardian` works the
# same way it does at runtime, without needing sqlalchemy/psycopg2 installed
# (charge_guardian's pure detector functions have no DB import at module load
# time — only run_charge_guardian() imports db, lazily, inside the function).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
