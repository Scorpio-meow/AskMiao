import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Document as DbDocument, RagChunk
from app.models.database import Base
from app.tasks.uploads_watcher import check_missing_uploads


def test_missing_upload_is_warned_once_and_nothing_is_deleted(tmp_path, caplog):
    engine = create_engine(f"sqlite:///{tmp_path / 'watcher.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "kept.txt").write_text("加班需主管核准", encoding="utf-8")
    with session_factory() as session:
        session.add_all([
            DbDocument(id=1, filename="gone.txt", content="特休依年資計算", file_type="text/plain"),
            DbDocument(id=2, filename="kept.txt", content="加班需主管核准", file_type="text/plain"),
            RagChunk(document_id=1, chunk_index=0, content="特休依年資計算", chunk_metadata="{}"),
        ])
        session.commit()
    warned_ids = set()

    with caplog.at_level(logging.WARNING, logger="app.tasks.uploads_watcher"):
        check_missing_uploads(session_factory, str(upload_dir), warned_ids)
        check_missing_uploads(session_factory, str(upload_dir), warned_ids)

    assert len([record for record in caplog.records if "gone.txt" in record.getMessage()]) == 1
    assert not [record for record in caplog.records if "kept.txt" in record.getMessage()]
    with session_factory() as session:
        assert session.query(DbDocument).count() == 2
        assert session.query(RagChunk).count() == 1
    engine.dispose()


def test_restored_upload_warns_again_if_it_goes_missing_later(tmp_path, caplog):
    engine = create_engine(f"sqlite:///{tmp_path / 'watcher.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    with session_factory() as session:
        session.add(DbDocument(id=1, filename="handbook.txt", content="特休依年資計算", file_type="text/plain"))
        session.commit()
    warned_ids = set()

    with caplog.at_level(logging.WARNING, logger="app.tasks.uploads_watcher"):
        check_missing_uploads(session_factory, str(upload_dir), warned_ids)
        (upload_dir / "handbook.txt").write_text("特休依年資計算", encoding="utf-8")
        check_missing_uploads(session_factory, str(upload_dir), warned_ids)
        (upload_dir / "handbook.txt").unlink()
        check_missing_uploads(session_factory, str(upload_dir), warned_ids)

    assert len([record for record in caplog.records if "handbook.txt" in record.getMessage()]) == 2
    engine.dispose()
