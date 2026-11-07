import uuid
from pathlib import Path
from app.core.config import Settings, settings
from app.core.security_logging import log_security_event, security_file_handlers
def test_security_handler_points_to_session_log_dir(isolated_log_dir):
    assert Path(settings.LOG_DIR) == isolated_log_dir
    assert [Path(h.baseFilename) for h in security_file_handlers()] == [isolated_log_dir / "security.log"]
def test_security_events_are_written_to_session_log_dir(isolated_log_dir):
    configured_log = Path(Settings().LOG_DIR) / "security.log"
    assert configured_log.parent != isolated_log_dir
    marker = f"log-isolation-{uuid.uuid4().hex}"
    log_security_event("LOG_DIR_ISOLATION_CHECK", details={"marker": marker})
    assert marker in (isolated_log_dir / "security.log").read_text(encoding="utf-8")
    assert not configured_log.exists() or marker not in configured_log.read_text(encoding="utf-8")