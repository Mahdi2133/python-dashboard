"""A tiny key/value table for facts about the database file itself.

Used by one-time data repairs that must run exactly once against a live
wells.db and must not run at all against a database the current code created.
"""
from ..extensions import db


class AppMeta(db.Model):
    __tablename__ = "app_meta"

    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(200))

    @staticmethod
    def get(key, default=None):
        row = db.session.get(AppMeta, key)
        return row.value if row is not None else default

    @staticmethod
    def set(key, value):
        row = db.session.get(AppMeta, key)
        if row is None:
            db.session.add(AppMeta(key=key, value=str(value)))
        else:
            row.value = str(value)
