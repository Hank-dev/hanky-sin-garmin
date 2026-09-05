import importlib
import io
import tempfile
from datetime import date
from urllib.error import URLError

import pytest

import config
import db
import import_hevy
import telegram_bot


HEVY_UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
HEVY_URL = f"https://hevy.com/workout/{HEVY_UUID}"


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    importlib.reload(db)
    db.config.DB_PATH = tmp.name
    db.init_db()
    return tmp.name


def _hevy_html(name="Push", iso_date="2026-06-10", extra_sets=""):
    return (
        f"**{name}\\n\\nDuration\\n\\n45m\\n\\nVolume\\n\\n1000 kg\n"
        f'"startTime": "{iso_date}T18:00:00"\n'
        "##### Deadlift\n"
        "100kg x 5 reps\n"
        "##### Deadlift\n"
        "80kg x 8 reps\n"
        f"{extra_sets}"
    )


def test_validate_hevy_url_rejects_ssrf_and_noncanonical():
    with pytest.raises(ValueError):
        import_hevy.validate_hevy_url("http://127.0.0.1:9999/not-a-hevy-workout")
    with pytest.raises(ValueError):
        import_hevy.validate_hevy_url("https://evil.example/workout/" + HEVY_UUID)
    with pytest.raises(ValueError):
        import_hevy.validate_hevy_url("https://hevy.com/workout/not-a-uuid")
    with pytest.raises(ValueError):
        import_hevy.validate_hevy_url(
            f"https://user:pass@hevy.com/workout/{HEVY_UUID}"
        )
    canonical, uuid = import_hevy.validate_hevy_url(
        f"https://www.hevy.com/workout/{HEVY_UUID.upper()}"
    )
    assert canonical == HEVY_URL
    assert uuid == HEVY_UUID


def test_import_requires_workout_date_when_page_has_none(monkeypatch):
    _fresh_db()
    monkeypatch.setattr(
        import_hevy,
        "fetch_hevy_page",
        lambda url: "**Workout\\n\\nDuration\\n\\n10m\n##### Deadlift\n100kg x 5 reps\n",
    )
    with pytest.raises(ValueError, match="Workout date"):
        import_hevy.import_workout(HEVY_URL)


def test_import_uses_page_date_and_keeps_duplicate_exercise_blocks(monkeypatch):
    _fresh_db()
    monkeypatch.setattr(import_hevy, "fetch_hevy_page", lambda url: _hevy_html())
    session_id, n_sets, volume, name = import_hevy.import_workout(HEVY_URL)
    assert name == "Push"
    assert session_id == f"hevy:{HEVY_UUID}"
    assert n_sets == 2
    assert volume == 100 * 5 + 80 * 8
    with db.connect() as conn:
        sess = conn.execute(
            "SELECT date FROM strength_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT set_id, position, set_index, weight_kg, reps "
            "FROM strength_sets WHERE session_id=? ORDER BY position, set_index",
            (session_id,),
        ).fetchall()
    assert sess["date"] == "2026-06-10"
    assert [r["set_id"] for r in rows] == [
        f"hevy:{HEVY_UUID}:deadlift:0:1",
        f"hevy:{HEVY_UUID}:deadlift:1:1",
    ]
    assert [(r["weight_kg"], r["reps"]) for r in rows] == [(100.0, 5), (80.0, 8)]


def test_dry_run_does_not_write(monkeypatch):
    _fresh_db()
    monkeypatch.setattr(import_hevy, "fetch_hevy_page", lambda url: _hevy_html())
    import_hevy.import_workout(HEVY_URL, dry_run=True, workout_date="2026-06-10")
    with db.connect() as conn:
        n_sess = conn.execute("SELECT COUNT(*) FROM strength_sessions").fetchone()[0]
        n_ex = conn.execute(
            "SELECT COUNT(*) FROM exercises WHERE is_custom=1"
        ).fetchone()[0]
    assert n_sess == 0
    assert n_ex == 0


def test_import_is_atomic_on_set_write_failure(monkeypatch):
    _fresh_db()
    monkeypatch.setattr(import_hevy, "fetch_hevy_page", lambda url: _hevy_html())
    original = db.upsert_strength_set

    def boom(record, conn=None):
        if record["set_index"] == 1 and record["position"] == 1:
            raise RuntimeError("injected second-set failure")
        return original(record, conn=conn)

    monkeypatch.setattr(db, "upsert_strength_set", boom)
    with pytest.raises(RuntimeError, match="injected"):
        import_hevy.import_workout(HEVY_URL)
    with db.connect() as conn:
        n_sess = conn.execute("SELECT COUNT(*) FROM strength_sessions").fetchone()[0]
        n_sets = conn.execute("SELECT COUNT(*) FROM strength_sets").fetchone()[0]
    assert n_sess == 0
    assert n_sets == 0


def test_link_garmin_requires_same_calendar_day(monkeypatch):
    _fresh_db()
    db.upsert_strength_session(
        {
            "session_id": f"hevy:{HEVY_UUID}",
            "date": "2026-06-10",
            "name": "Push (Hevy)",
            "source": "hevy",
        }
    )

    class FakeClient:
        def get_activities_by_date(self, start, end):
            return [
                {
                    "activityId": 991,
                    "activityType": {"typeKey": "strength_training"},
                    "startTimeLocal": "2026-06-09T23:50:00",
                },
                {
                    "activityId": 992,
                    "activityType": {"typeKey": "strength_training"},
                    "startTimeLocal": "2026-06-10T18:00:00",
                },
            ]

    monkeypatch.setattr("garmin_client.get_client", lambda interactive=False: FakeClient())
    monkeypatch.setattr("ingest.ingest_activities", lambda *args, **kwargs: 2)
    aid = import_hevy.link_garmin_activity(f"hevy:{HEVY_UUID}")
    assert aid == "992"
    with db.connect() as conn:
        row = conn.execute(
            "SELECT garmin_activity_id FROM strength_sessions WHERE session_id=?",
            (f"hevy:{HEVY_UUID}",),
        ).fetchone()
    assert row["garmin_activity_id"] == "992"


def test_fetch_hevy_page_never_opens_rejected_url(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("urlopen must not be reached")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", boom)
    with pytest.raises(ValueError):
        import_hevy.fetch_hevy_page("http://127.0.0.1:9999/not-a-hevy-workout")


def test_sync_command_does_not_emit_unknown_and_rolls_back_flag(monkeypatch):
    telegram_bot._sync_in_progress = False
    sent = []

    def fail_send(chat_id, text):
        sent.append(text)
        raise telegram_bot.TelegramApiError("nope")

    monkeypatch.setattr(telegram_bot, "send_message", fail_send)
    with pytest.raises(telegram_bot.TelegramApiError):
        telegram_bot.handle_authorized_command("/sync", "7", 1)
    assert telegram_bot._sync_in_progress is False
    assert sent and "Sync started" in sent[0]

    sent.clear()
    started = []

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            started.append(self.args)

    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text: sent.append(text))
    monkeypatch.setattr(telegram_bot.threading, "Thread", FakeThread)
    reply = telegram_bot.handle_authorized_command("/sync", "", 42)
    assert reply == ""
    assert telegram_bot._sync_in_progress is True
    assert started == [(42, 7)]

    replies = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text: replies.append(text))
    telegram_bot.handle_update(
        {"message": {"text": "/sync", "chat": {"id": 42}, "from": {"id": 99}}},
        allowed_ids={99},
    )
    assert replies == ["⏳ Sync already running — I'll notify you when it finishes."]
    telegram_bot._sync_in_progress = False
