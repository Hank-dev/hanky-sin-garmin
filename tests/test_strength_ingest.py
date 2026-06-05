import importlib
import tempfile

import config
import db
import ingest


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    importlib.reload(db)
    db.config.DB_PATH = tmp.name
    db.init_db()


class FakeClient:
    def get_body_composition(self, start, end):
        return {"dateWeightList": [
            {"calendarDate": "2026-06-05", "weight": 80500.0, "bodyFat": 16.2},
            {"calendarDate": "2026-06-04", "weight": 80700.0},
        ]}

    def get_user_profile(self):
        return {"userData": {"gender": "MALE", "birthDate": "1995-03-10",
                             "height": 182.0}}


def test_ingest_body_metrics_maps_grams_to_kg():
    _fresh_db()
    n = ingest.ingest_body_metrics(FakeClient(), "2026-06-04", "2026-06-05")
    assert n == 2
    bm = db.load_body_metrics_df()
    row = bm[bm["date"].astype(str).str.startswith("2026-06-05")].iloc[0]
    assert abs(row["weight_kg"] - 80.5) < 1e-6
    assert row["source"] == "garmin"


def test_ingest_profile_extracts_sex_and_birth_year():
    _fresh_db()
    ingest.ingest_profile(FakeClient())
    prof = db.load_profile()
    assert prof["sex"] == "male"
    assert prof["birth_year"] == 1995
    assert abs(prof["height_cm"] - 182.0) < 1e-6


class PartialProfileClient:
    def get_user_profile(self):
        return {"userData": {"gender": "MALE", "birthDate": "1995-03-10",
                             "height": 182.0}}


class NoBirthDateClient:
    def get_user_profile(self):
        return {"userData": {"gender": "MALE", "height": 182.0}}  # no birthDate


def test_partial_profile_sync_does_not_null_existing_birth_year():
    _fresh_db()
    ingest.ingest_profile(PartialProfileClient())
    assert db.load_profile()["birth_year"] == 1995
    # a later sync without birthDate must NOT wipe the stored year
    ingest.ingest_profile(NoBirthDateClient())
    prof = db.load_profile()
    assert prof["birth_year"] == 1995
    assert prof["sex"] == "male"
