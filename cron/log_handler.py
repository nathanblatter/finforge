"""Custom logging handler that persists cron log records to the database."""

import logging
import uuid
from datetime import datetime, timezone

from db import CronLogRow, SessionLocal


class DBLogHandler(logging.Handler):
    """Write log records to the cron_logs table.

    Maps the logger name to a job_name by stripping common prefixes.
    Only captures logs at INFO level and above to avoid flooding the DB.
    """

    # Logger names we care about → friendly job names
    JOB_NAME_MAP = {
        "finforge.cron": "scheduler",
        "integrations.plaid_sync": "plaid_sync",
        "integrations.schwab_sync": "schwab_sync",
        "integrations.schwab_auth": "schwab_auth",
        "integrations.market_data_sync": "market_data_sync",
        "finforge.cron.goal_engine": "goal_engine",
        "finforge.cron.claude_engine": "claude_engine",
    }

    def _resolve_job_name(self, name: str) -> str:
        # Exact match first
        if name in self.JOB_NAME_MAP:
            return self.JOB_NAME_MAP[name]
        # Prefix match
        for prefix, job in self.JOB_NAME_MAP.items():
            if name.startswith(prefix):
                return job
        # Fallback: last segment
        return name.rsplit(".", 1)[-1]

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.INFO:
            return

        job_name = self._resolve_job_name(record.name)
        message = self.format(record)

        try:
            session = SessionLocal()
            try:
                row = CronLogRow(
                    id=uuid.uuid4(),
                    job_name=job_name,
                    level=record.levelname,
                    message=message,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(row)
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()
        except Exception:
            # Never let logging errors crash the cron process
            pass
