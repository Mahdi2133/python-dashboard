"""Wells — the 342 names that used to be the hardcoded ``ALL_WELLS`` array."""
from datetime import datetime

from sqlalchemy import UniqueConstraint

from ..extensions import db


class Well(db.Model):
    __tablename__ = "wells"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False, index=True)
    code = db.Column(db.String(60), index=True)
    # From the maintenance workbook «کلاسه و pm code»: the PM system's asset id
    # and the well's class number. Operators search by these as often as by
    # name, so they travel with the well everywhere it is shown or exported.
    pm_code = db.Column(db.String(40), index=True)
    well_class = db.Column(db.String(40), index=True)
    address = db.Column(db.Text)
    center_id = db.Column(db.Integer, db.ForeignKey("lookup_items.id"), index=True)
    depth = db.Column(db.Float)
    status = db.Column(db.String(40), default="active")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    # Set when the importer meets a name that is not in the canonical list; the
    # row is kept (never discarded) but flagged for the admin to confirm.
    is_verified = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    center = db.relationship("LookupItem", foreign_keys=[center_id])
    aliases = db.relationship("WellAlias", back_populates="well", cascade="all, delete-orphan")

    def to_dict(self, with_stats=False):
        data = {
            "id": self.id, "name": self.name, "code": self.code,
            "pm_code": self.pm_code, "well_class": self.well_class,
            "address": self.address,
            "center_id": self.center_id,
            "center": self.center.label if self.center else None,
            # The *stored* value, not the label: the entry form ticks the
            # centre radio by value when a well is chosen.
            "center_value": self.center.value if self.center else None,
            "depth": self.depth, "status": self.status,
            "is_active": self.is_active, "is_verified": self.is_verified,
            "notes": self.notes,
            "display": self.display_label,
        }
        if with_stats:
            data["record_count"] = len([r for r in self.records if r.is_active])
        return data

    @property
    def display_label(self):
        """Name with the PM code and class appended, for pickers and reports."""
        parts = []
        if self.pm_code:
            parts.append(f"PM {self.pm_code}")
        if self.well_class:
            parts.append(f"کلاسه {self.well_class}")
        return f"{self.name} ({' · '.join(parts)})" if parts else self.name


class WellAlias(db.Model):
    __tablename__ = "well_aliases"
    __table_args__ = (UniqueConstraint("alias", name="uq_well_alias"),)

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    alias = db.Column(db.String(200), nullable=False)

    well = db.relationship("Well", back_populates="aliases")


class PumpCurvePoint(db.Model):
    """Head/flow points for a pump curve comparison (sheet «رجائی 2»).

    Deliberately left empty by the seeder: the workshop spreadsheet holds this
    analysis for a single well, which is not enough to invent defaults from.
    """
    __tablename__ = "pump_curve_points"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id", ondelete="CASCADE"), index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("records.id", ondelete="SET NULL"), index=True)
    head = db.Column(db.Float)
    table_flow = db.Column(db.Float)      # دبی جدول (catalogue)
    initial_flow = db.Column(db.Float)    # دبی اولیه
    return_flow = db.Column(db.Float)     # دبی برگشتی
    months_in_service = db.Column(db.Integer)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        drop = None
        if self.initial_flow is not None and self.return_flow is not None:
            drop = round(self.initial_flow - self.return_flow, 3)
        vs_table = None
        if self.table_flow is not None and self.return_flow is not None:
            vs_table = round(self.table_flow - self.return_flow, 3)
        return {
            "id": self.id, "well_id": self.well_id, "record_id": self.record_id,
            "head": self.head, "table_flow": self.table_flow,
            "initial_flow": self.initial_flow, "return_flow": self.return_flow,
            "months_in_service": self.months_in_service, "note": self.note,
            "flow_drop": drop, "flow_vs_table": vs_table,
        }
