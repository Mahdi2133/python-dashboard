"""The pump catalogue: each model's head/flow curve, motor and current.

Forms read it through the CAT_* formula functions and the «کاتالوگ» chart
series, so the expert's choice, the workshop's build and its test can be laid
over the manufacturer's curve. Seeded from the Gazar catalogue; the catalogue
page edits rows and re-imports the whole table from Excel.
"""
from ..extensions import db
from ..services.jalali import local_now


def norm_type(value) -> str:
    """«384»، 384.0 and « 384 » are one type; letters (345P) are kept."""
    text = str(value if value is not None else "").strip().replace("٫", ".")
    try:
        f = float(text)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return text.upper()


def norm_stages(value) -> str:
    """«10»، 10.0 and «10 » are one stage count; «3a» stays «3a»."""
    text = "".join(c.lower() if "A" <= c <= "Z" else c
                   for c in str(value if value is not None else "").strip().replace(" ", ""))
    try:
        f = float(text)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return text


class PumpCatalogModel(db.Model):
    __tablename__ = "pump_catalog_models"

    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(60), nullable=False, default="گازار")
    pump_type = db.Column(db.String(20), nullable=False, index=True)
    stages = db.Column(db.String(10), nullable=False)
    trim = db.Column(db.String(40))                # «(Ø131/127)» for an «a» model
    motor_kw = db.Column(db.Float)
    motor_hp = db.Column(db.Float)
    current_a = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    pump_length_mm = db.Column(db.Float)
    total_length_mm = db.Column(db.Float)
    motor_eff = db.Column(db.Float)                # % — the workbook's 90 when unknown
    source = db.Column(db.String(120))
    note = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    points = db.relationship("PumpCatalogPoint", back_populates="model",
                             cascade="all, delete-orphan",
                             order_by="PumpCatalogPoint.q_m3h")

    __table_args__ = (db.UniqueConstraint("brand", "pump_type", "stages",
                                          name="uq_pump_catalog_model"),)

    @property
    def title(self) -> str:
        return f"{self.pump_type}/{self.stages}"

    @property
    def full_title(self) -> str:
        # «384/10+73.5» — the one electropump format (services.epump)
        kw = f"+{self.motor_kw:g}" if self.motor_kw is not None else ""
        trim = self.trim if self.trim and self.trim.replace(" ", "") not in self.stages else ""
        return f"{self.title}{trim.replace(' ', '') if trim else ''}{kw}"

    def to_dict(self, points=True):
        data = {
            "id": self.id, "brand": self.brand, "pump_type": self.pump_type,
            "stages": self.stages, "trim": self.trim, "title": self.title,
            "full_title": self.full_title, "motor_kw": self.motor_kw,
            "motor_hp": self.motor_hp, "current_a": self.current_a,
            "weight_kg": self.weight_kg, "pump_length_mm": self.pump_length_mm,
            "total_length_mm": self.total_length_mm, "motor_eff": self.motor_eff,
            "source": self.source, "note": self.note, "is_active": self.is_active,
            "point_count": len(self.points),
        }
        if points:
            data["points"] = [p.to_dict() for p in self.points]
        return data


class PumpCatalogPoint(db.Model):
    __tablename__ = "pump_catalog_points"

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey("pump_catalog_models.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    q_m3h = db.Column(db.Float, nullable=False)
    head = db.Column(db.Float, nullable=False)
    pump_eff = db.Column(db.Float)                 # %

    model = db.relationship("PumpCatalogModel", back_populates="points")

    @property
    def q_ls(self):
        return round(self.q_m3h / 3.6, 3)

    def to_dict(self):
        return {"id": self.id, "q_m3h": self.q_m3h, "q_ls": self.q_ls,
                "head": self.head, "pump_eff": self.pump_eff}
