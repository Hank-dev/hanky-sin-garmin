import importlib
import tempfile

import config
import db


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    importlib.reload(db)
    db.config.DB_PATH = tmp.name
    db.init_db()
    return tmp.name


def test_memory_add_load_roundtrip():
    _fresh_db()
    mid = db.add_memory({"category": "goal", "text": "BJJ comp in August",
                         "source": "user", "target_date": "2026-08-15"})
    assert isinstance(mid, int) and mid > 0
    df = db.load_memory_df()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["category"] == "goal"
    assert row["text"] == "BJJ comp in August"
    assert row["status"] == "active"
    assert row["source"] == "user"
    assert row["target_date"] == "2026-08-15"
    assert row["created_at"] and row["updated_at"]


def test_memory_update_bumps_updated_at():
    _fresh_db()
    mid = db.add_memory({"category": "note", "text": "old", "source": "user"})
    before = db.load_memory_df().iloc[0]["updated_at"]
    db.update_memory(mid, {"text": "new"})
    row = db.load_memory_df().iloc[0]
    assert row["text"] == "new"
    assert row["updated_at"] >= before


def test_memory_archive_hides_from_active_load():
    _fresh_db()
    mid = db.add_memory({"category": "injury", "text": "left knee",
                         "source": "user", "body_part": "knee"})
    db.archive_memory(mid)
    assert len(db.load_memory_df()) == 0                 # default: active only
    assert len(db.load_memory_df(status=None)) == 1      # all
    assert db.load_memory_df(status="archived").iloc[0]["body_part"] == "knee"


def test_memory_delete_removes_row():
    _fresh_db()
    mid = db.add_memory({"category": "note", "text": "x", "source": "user"})
    db.delete_memory(mid)
    assert len(db.load_memory_df(status=None)) == 0
