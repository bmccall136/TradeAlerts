import json
import os

# services/settings_service.py
from datetime import timedelta

from peewee import IntegerField, Model, SqliteDatabase, TextField

# Common chart/timeframe windows used by the dashboard
TIMEFRAME_DELTAS = {
    "1d": timedelta(days=1),
    "5d": timedelta(days=5),
    "1mo": timedelta(days=30),
    "3mo": timedelta(days=90),
    "6mo": timedelta(days=182),
    "1y": timedelta(days=365),
    "2y": timedelta(days=730),
    "5y": timedelta(days=1825),
    "max": None,  # special-cased by callers
}

# ... rest as before
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "settings.db"))
DB = SqliteDatabase(DB_PATH)


class BaseModel(Model):
    class Meta:
        database = DB


class Settings(BaseModel):
    id = IntegerField(primary_key=True, default=1)
    data = TextField()


def init_settings_db():
    # only connect once
    if DB.is_closed():
        DB.connect()
    DB.create_tables([Settings])
    # seed
    if not Settings.select().where(Settings.id == 1).exists():
        Settings.create(id=1, data=json.dumps({}))


def load_settings(defaults):
    row = Settings.get_by_id(1)
    saved = json.loads(row.data or "{}")
    # overlay defaults *under* saved so you fill in missing keys
    merged = {**defaults, **saved}
    return merged


def save_settings(settings_dict):
    Settings.update(data=json.dumps(settings_dict)).where(Settings.id == 1).execute()
