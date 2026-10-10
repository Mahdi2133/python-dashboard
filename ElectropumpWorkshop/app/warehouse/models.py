"""warehouse.db — items, condition classes and the movement ledger."""
from ..extensions import db
from ..services.jalali import local_now

WAREHOUSES = {"equipment": "انبار تجهیزات", "parts": "انبار قطعات"}
KINDS = {"equipment": "تجهیز (الکتروموتور، پمپ، الکتروپمپ)", "part": "قطعه"}
DIRECTIONS = {"in": "ورود", "out": "خروج"}
REASONS = {
    "pull": "کشیدن الکتروپمپ از چاه",
    "disassembly": "دمونتاژ و تفکیک",
    "purchase": "خرید نو",
    "repair": "تعمیر",
    "assembly": "مصرف در مونتاژ (ساخت)",
    "assembled": "الکتروپمپ مونتاژشده",
    "install": "خروج برای نصب",
    "scrap": "اسقاط",
    "manual": "اصلاح موجودی",
    "opening": "موجودی اول دوره (انبارگردانی)",
}
# How many of a part one equipment takes: as many as the pump has stages
# («پروانه»، «بوش»، «طبقه»), a fixed number («شافت»، «سوپاپ» = 1), or typed.
QTY_RULES = {"": "دستی", "stages": "به تعداد طبقات پمپ"}


class WhItem(db.Model):
    __bind_key__ = "warehouse"
    __tablename__ = "wh_items"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="part")     # equipment | part
    category = db.Column(db.String(80))
    unit = db.Column(db.String(20), nullable=False, default="عدد")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    source = db.Column(db.String(40), default="پیشنهادی")             # پیشنهادی | ورود از اکسل
    note = db.Column(db.Text)
    # «تعداد در هر تجهیز»: '' typed by hand, 'stages' = the pump's stage
    # count, or a number («1» for the shaft and the valve)
    qty_rule = db.Column(db.String(20))
    # «موجودی به تفکیک تیپ پمپ»: a part made for one pump type (impeller,
    # bush, stage) is stocked per type — 35 of 374, 65 of 6608
    per_type = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name, "kind": self.kind,
                "category": self.category, "unit": self.unit, "is_active": self.is_active,
                "sort_order": self.sort_order, "source": self.source, "note": self.note,
                "qty_rule": self.qty_rule or "", "per_type": bool(self.per_type)}


class WhCondition(db.Model):
    __bind_key__ = "warehouse"
    __tablename__ = "wh_conditions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    label = db.Column(db.String(80), nullable=False)
    applies_to = db.Column(db.String(40), default="equipment,part")
    color = db.Column(db.String(12))
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"code": self.code, "label": self.label,
                "applies_to": [x for x in (self.applies_to or "").split(",") if x],
                "color": self.color, "is_active": self.is_active}


class WhMovement(db.Model):
    __bind_key__ = "warehouse"
    __tablename__ = "wh_movements"

    id = db.Column(db.Integer, primary_key=True)
    jdate = db.Column(db.String(10), nullable=False)          # 1405/07/17
    date_num = db.Column(db.Integer, index=True)
    warehouse = db.Column(db.String(20), nullable=False, index=True)
    direction = db.Column(db.String(4), nullable=False)       # in | out
    reason = db.Column(db.String(20), nullable=False, default="manual")
    item_id = db.Column(db.Integer, db.ForeignKey("wh_items.id", ondelete="SET NULL"), index=True)
    item_name = db.Column(db.String(160), nullable=False)     # as it was called then
    item_kind = db.Column(db.String(20))
    qty = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(20))
    condition = db.Column(db.String(20), index=True)
    spec = db.Column(db.String(80))                           # «384/10+73.5», «37 kW»
    # the type the stock is counted by: «73.5» (motor kW), «384/10» (pump),
    # «384/10+73.5» (electropump), «384» (a part made for that pump type)
    variant = db.Column(db.String(60), index=True)
    serial = db.Column(db.String(80))                         # plaque / serial
    note = db.Column(db.Text)
    # where it came from
    instance_id = db.Column(db.Integer, index=True)
    workflow_name = db.Column(db.String(120))
    stage_number = db.Column(db.Integer)
    stage_title = db.Column(db.String(160))
    field_name = db.Column(db.String(80))
    well_id = db.Column(db.Integer, index=True)
    well_name = db.Column(db.String(160))
    user_id = db.Column(db.Integer)
    user_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=local_now)

    item = db.relationship("WhItem")

    def to_dict(self):
        return {"id": self.id, "jdate": self.jdate, "warehouse": self.warehouse,
                "warehouse_label": WAREHOUSES.get(self.warehouse, self.warehouse),
                "direction": self.direction, "direction_label": DIRECTIONS.get(self.direction),
                "reason": self.reason, "reason_label": REASONS.get(self.reason, self.reason),
                "item_id": self.item_id, "item_name": self.item_name, "item_kind": self.item_kind,
                "qty": self.qty, "unit": self.unit, "condition": self.condition,
                "spec": self.spec, "variant": self.variant, "serial": self.serial, "note": self.note,
                "instance_id": self.instance_id, "workflow_name": self.workflow_name,
                "stage_number": self.stage_number, "stage_title": self.stage_title,
                "well_id": self.well_id, "well_name": self.well_name,
                "user_name": self.user_name}


class WhEquipment(db.Model):
    """The register of motors and pumps by equipment code (EM/…, MP/…)."""
    __bind_key__ = "warehouse"
    __tablename__ = "wh_equipment"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(160))
    kind = db.Column(db.String(60))                    # الکتروموتور شناور | پمپ شناور
    last_date = db.Column(db.String(10))
    last_facility = db.Column(db.String(160))
    last_facility_code = db.Column(db.String(40))
    property_no = db.Column(db.String(60))             # شماره اموال
    maker = db.Column(db.String(80))
    type_label = db.Column(db.String(40))              # «37» kW / «6608/15»
    status = db.Column(db.String(60))                  # در انبار، در کارگاه، در چاه …
    is_sample = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name, "kind": self.kind,
                "last_date": self.last_date, "last_facility": self.last_facility,
                "property_no": self.property_no, "maker": self.maker,
                "type_label": self.type_label, "status": self.status}


PART_ACTIONS = {"installed": "نصب شد", "collected": "جمع آوری شد"}


class WhPartAction(db.Model):
    """One part installed in or collected from one equipment — the history of
    the parts workbook (98–05) and every parts form sent since."""
    __bind_key__ = "warehouse"
    __tablename__ = "wh_part_actions"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(20), nullable=False, default="history", index=True)
    jdate = db.Column(db.String(10))
    date_num = db.Column(db.Integer, index=True)
    year = db.Column(db.Integer, index=True)
    month = db.Column(db.Integer)
    facility_code = db.Column(db.String(40))
    facility_name = db.Column(db.String(160))
    center = db.Column(db.String(80))
    equipment_code = db.Column(db.String(60), index=True)
    equipment_kind = db.Column(db.String(60), index=True)
    equipment_name = db.Column(db.String(160))
    related_action = db.Column(db.String(60))          # نصب / جمع آوری / تعمیر تجهیز
    activity = db.Column(db.String(60))                # الکتریکال، مکانیکال، …
    failure = db.Column(db.String(160))                # خرابی مشاهده شده
    cause = db.Column(db.String(160))                  # علت خرابی
    action_done = db.Column(db.String(160))            # اقدام انجام شده
    note = db.Column(db.Text)
    part_action = db.Column(db.String(20), index=True)  # installed | collected
    state = db.Column(db.String(10))                   # نو | کهنه
    reusable = db.Column(db.Boolean)                   # True = قابل استفاده مجدد, False = اسقاط
    part_code = db.Column(db.String(40), index=True)
    part_name = db.Column(db.String(160))
    part_type = db.Column(db.String(120))
    qty = db.Column(db.Float, nullable=False, default=1)
    instance_id = db.Column(db.Integer, index=True)
    stage_number = db.Column(db.Integer)
    field_name = db.Column(db.String(80))
    well_id = db.Column(db.Integer)
    well_name = db.Column(db.String(160))
    user_name = db.Column(db.String(120))
