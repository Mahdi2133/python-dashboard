"""Reference lists (مدیریت گزینه‌های فرم).

Every choice field in the original HTML — centers, contractors, failure
reasons, motor kW ratings, pump types, cable sizes … — lives here instead of
being hardcoded in JavaScript. Options are never deleted: they are
deactivated, so historical records keep their meaning.

``LookupAlias`` exists because the real workshop spreadsheet spells the same
contractor five different ways ("سعدآبادی", "سعدابادی", "سعد ابادی" …).
Import normalises through the alias table so reports aggregate correctly
without rewriting the source data.
"""
from datetime import datetime

from ..services.jalali import local_now

from sqlalchemy import UniqueConstraint

from ..extensions import db


class LookupCategory(db.Model):
    __tablename__ = "lookup_categories"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False, index=True)
    name_fa = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    allows_multiple = db.Column(db.Boolean, nullable=False, default=False)
    # System categories are wired into report queries; the admin may add and
    # reorder their options but not delete the category itself.
    is_system = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    items = db.relationship(
        "LookupItem", back_populates="category",
        cascade="all, delete-orphan", order_by="LookupItem.sort_order",
    )

    def to_dict(self, include_items=False, active_only=True):
        data = {
            "id": self.id, "code": self.code, "name_fa": self.name_fa,
            "description": self.description, "allows_multiple": self.allows_multiple,
            "is_system": self.is_system, "sort_order": self.sort_order,
        }
        if include_items:
            items = [i for i in self.items if i.is_active or not active_only]
            data["items"] = [i.to_dict() for i in items]
        return data


class LookupItem(db.Model):
    __tablename__ = "lookup_items"
    __table_args__ = (UniqueConstraint("category_id", "value", name="uq_lookup_category_value"),)

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("lookup_categories.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    value = db.Column(db.String(200), nullable=False)   # canonical stored value
    label = db.Column(db.String(200), nullable=False)   # what the button shows
    icon = db.Column(db.String(16))                     # optional emoji prefix
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    # Created automatically by the importer for a value not in the list. Kept
    # visible to the admin so they can merge it into a real option or keep it.
    is_adhoc = db.Column(db.Boolean, nullable=False, default=False)
    # A locked option is part of the process rules rather than a preference:
    # «جمع آوری» must always be offerable as a reason for pulling a well, so
    # the option manager may reorder or relabel it but never remove it.
    is_locked = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)

    category = db.relationship("LookupCategory", back_populates="items")
    aliases = db.relationship("LookupAlias", back_populates="item", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "category_id": self.category_id,
            "category": self.category.code if self.category else None,
            "value": self.value, "label": self.label, "icon": self.icon,
            "sort_order": self.sort_order, "is_active": self.is_active,
            "is_default": self.is_default, "is_adhoc": self.is_adhoc,
            "is_locked": self.is_locked,
            "notes": self.notes,
            "aliases": [a.alias for a in self.aliases],
        }


class LookupAlias(db.Model):
    """A spelling seen in real data that maps onto a canonical option."""
    __tablename__ = "lookup_aliases"
    __table_args__ = (UniqueConstraint("category_id", "alias", name="uq_lookup_alias"),)

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("lookup_categories.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("lookup_items.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    alias = db.Column(db.String(200), nullable=False)

    item = db.relationship("LookupItem", back_populates="aliases")
