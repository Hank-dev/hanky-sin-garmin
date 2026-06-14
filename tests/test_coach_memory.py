import importlib
import tempfile

import pandas as pd

import analysis
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


# ---------------------------------------------------------------------------
# analysis.build_coach_memory_digest tests
# ---------------------------------------------------------------------------

def _mem_df(rows):
    cols = ["id", "category", "text", "status", "source", "confidence",
            "target_date", "body_part", "created_at", "updated_at"]
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows])


def test_digest_empty_returns_empty_dict():
    assert analysis.build_coach_memory_digest(pd.DataFrame()) == {}
    df = _mem_df([{"category": "note", "text": "x", "status": "archived"}])
    assert analysis.build_coach_memory_digest(df) == {}


def test_digest_groups_and_shapes_active_only():
    df = _mem_df([
        {"category": "goal", "text": "comp", "status": "active",
         "target_date": "2026-08-15"},
        {"category": "injury", "text": "knee", "status": "active",
         "body_part": "knee"},
        {"category": "pattern", "text": "late coffee → low HRV",
         "status": "active", "confidence": "high"},
        {"category": "note", "text": "ignored", "status": "archived"},
    ])
    d = analysis.build_coach_memory_digest(df)
    assert d["goals"] == [{"text": "comp", "target_date": "2026-08-15"}]
    assert d["injuries"] == [{"text": "knee", "body_part": "knee"}]
    assert d["patterns"] == [{"text": "late coffee → low HRV",
                              "confidence": "high"}]
    assert "notes" not in d            # the only note was archived


def test_digest_coaching_recent_first_and_capped():
    rows = [{"category": "coaching", "text": f"advice {i}", "status": "active",
             "created_at": f"2026-06-0{i}T00:00:00"} for i in range(1, 8)]
    d = analysis.build_coach_memory_digest(_mem_df(rows), coaching_cap=3)
    assert [c["text"] for c in d["coaching"]] == ["advice 7", "advice 6", "advice 5"]
    assert d["coaching"][0]["date"] == "2026-06-07"
