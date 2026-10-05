from __future__ import annotations

import logging
import shutil
from pathlib import Path

from open_paxel.config import Settings
from open_paxel.db.models import (
    ProcessingJobRow,
    ProfileRow,
    SessionReportRow,
    UploadRow,
    init_db,
    make_engine,
)

logger = logging.getLogger(__name__)


def cleanup_incoming(incoming_dir: Path) -> None:
    if not incoming_dir.exists():
        return
    for path in incoming_dir.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def wipe_database_tables(db_path: Path) -> None:
    engine = make_engine(str(db_path))
    Session = init_db(engine)
    with Session() as session:
        session.query(ProcessingJobRow).delete()
        session.query(SessionReportRow).delete()
        session.query(UploadRow).delete()
        session.query(ProfileRow).delete()
        session.commit()


def reset_app_data(settings: Settings) -> None:
    """Delete analyzed data, jobs, uploads, profile cache, and temp incoming files."""
    incoming = settings.home / "incoming"
    cleanup_incoming(incoming)

    db_path = settings.db_path
    settings.home.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        init_db(make_engine(str(db_path)))
        return

    try:
        db_path.unlink()
        logger.info("Removed database %s", db_path)
        init_db(make_engine(str(db_path)))
    except OSError as exc:
        logger.warning("Could not remove %s (%s); wiping tables in place", db_path, exc)
        wipe_database_tables(db_path)

