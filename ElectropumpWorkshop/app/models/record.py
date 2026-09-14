"""The workshop operation record — one row per pull/install/collection job.

Column-for-column this is the ``1405`` sheet of the workshop spreadsheet and
the 51 fields of the original HTML form, with these structural corrections:

* single-choice fields hold a foreign key into ``lookup_items`` instead of a
  loose string, so a report can group on them reliably;
* multi-choice fields (failure reasons, workshop opinion, description tags)
  became ``record_tags`` rows instead of one comma-joined string;
* dates are stored as Gregorian ISO in ``op_date`` while the Jalali values the
  operator actually typed are kept alongside in ``j_year/j_month/j_day``;
* free-text columns from the sheets that the HTML form omitted are present.
"""
from datetime import datetime

from ..services.jalali import local_now

from ..extensions import db


def _fk():
    return db.Column(db.Integer, db.ForeignKey("lookup_items.id"), index=True)


class Record(db.Model):
    __tablename__ = "records"

    id = db.Column(db.Integer, primary_key=True)

    # ── بخش ۱: اطلاعات پایه ────────────────────────────────────────────────
    j_year = db.Column(db.Integer, index=True)
    j_month = db.Column(db.Integer, index=True)
    j_day = db.Column(db.Integer)
    op_date = db.Column(db.Date, index=True)          # Gregorian ISO (storage standard)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), index=True)
    well_name_raw = db.Column(db.String(200))         # exactly as typed/imported
    center_id = _fk()
    shift_id = _fk()

    # ── بخش ۲: عملیات و خرابی ──────────────────────────────────────────────
    operation_id = _fk()
    pm_id = _fk()
    contractor_id = _fk()
    executor_id = _fk()                               # مجری (امانی / پیمانی)
    failure_other = db.Column(db.Text)

    # ── بخش ۳: موتور ───────────────────────────────────────────────────────
    motor_prev_id = _fk()
    motor_curr_id = _fk()
    motor_plaque = db.Column(db.String(80))
    motor_maker_id = _fk()
    motor_condition_id = _fk()
    motor_rewind_id = _fk()                           # سیم‌پیچی / سرویس

    # ── بخش ۴: پمپ ─────────────────────────────────────────────────────────
    pump_prev_id = _fk()                              # type part of "384/10"
    pump_prev_stages = db.Column(db.Integer)          # stage part of "384/10"
    pump_prev_raw = db.Column(db.String(80))          # the original combined text
    pump_curr_id = _fk()
    pump_stages = db.Column(db.Integer)
    pump_plaque = db.Column(db.String(80))
    pump_maker_id = _fk()
    pump_condition_id = _fk()
    type_change_id = _fk()

    # ── بخش ۵: اطلاعات چاه و نصب ───────────────────────────────────────────
    prev_install_date = db.Column(db.Date)
    prev_install_date_raw = db.Column(db.String(40))  # sheets hold partial dates
    well_depth = db.Column(db.Float)
    prev_install_depth = db.Column(db.Float)
    curr_install_depth = db.Column(db.Float)
    static_level = db.Column(db.Float)
    dynamic_level = db.Column(db.Float)
    path_loss = db.Column(db.Float)
    network_pressure = db.Column(db.Float)
    total_head = db.Column(db.Float)
    design_flow = db.Column(db.Float)
    pipe_diameter_id = _fk()
    cable_type_change_id = _fk()

    # ── بخش ۶: آزمایش پمپاژ ────────────────────────────────────────────────
    test_date = db.Column(db.Date)
    test_date_raw = db.Column(db.String(40))
    test_pressure = db.Column(db.Float)
    test_flow = db.Column(db.Float)
    cable_size_change_id = _fk()

    # ── بخش ۷: کابل و راه‌انداز ────────────────────────────────────────────
    cable_well = db.Column(db.String(200))
    starter_id = _fk()
    cable_size_id = _fk()
    pull_year = db.Column(db.Integer, index=True)
    pull_month = db.Column(db.Integer)
    old_install_year = db.Column(db.Integer)
    old_install_month = db.Column(db.Integer)

    # ── بخش ۸: نتیجه و توضیحات ─────────────────────────────────────────────
    working_months = db.Column(db.Integer)
    young_wells = db.Column(db.Integer)
    workshop_note = db.Column(db.Text)                # شرح خرابی از نظر کارگاه
    description = db.Column(db.Text)

    # ── فیلدهای تکمیلی برگرفته از شیت‌های اکسل (در HTML نبودند) ───────────
    install_supervisor = db.Column(db.String(120))    # ناظر نصب
    flow_after_install = db.Column(db.Float)          # دبی پس از نصب پمپ جدید
    flow_before_pull = db.Column(db.Float)            # دبي قبل از كشيدن (۱۳۹۸)
    flow_before_pull_date = db.Column(db.String(40))
    flow_after_install_date = db.Column(db.String(40))
    casing_length = db.Column(db.Float)               # متراژ لوله جدار کشیده‌شده
    casing_pulled_diameter = db.Column(db.String(40))
    casing_repair_count = db.Column(db.Integer)
    casing_material = db.Column(db.String(80))
    casing_diameter = db.Column(db.String(40))
    documents_ref = db.Column(db.String(200))         # مستندات
    reported_to_finance = db.Column(db.Boolean, default=False)  # اعلام شده به مالی

    # ── provenance & lifecycle ─────────────────────────────────────────────
    source_sheet = db.Column(db.String(60))
    source_row = db.Column(db.Integer)
    import_batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id"), index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"), index=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("app_users.id"), index=True)

    well = db.relationship("Well", backref=db.backref("records", lazy="dynamic"))
    tags = db.relationship("RecordTag", back_populates="record",
                           cascade="all, delete-orphan", lazy="selectin")
    dynamic_values = db.relationship("RecordDynamicValue", back_populates="record",
                                     cascade="all, delete-orphan", lazy="selectin")

    # Every single-choice column, paired with the lookup category it draws from.
    CHOICE_FIELDS = {
        "center_id": "center", "shift_id": "shift", "operation_id": "operation",
        "pm_id": "pm_form", "contractor_id": "contractor", "executor_id": "executor",
        "motor_prev_id": "motor_type", "motor_curr_id": "motor_type",
        "motor_maker_id": "maker", "motor_condition_id": "condition",
        "motor_rewind_id": "motor_rewind",
        "pump_prev_id": "pump_type", "pump_curr_id": "pump_type",
        "pump_maker_id": "maker", "pump_condition_id": "condition",
        "type_change_id": "change_flag", "pipe_diameter_id": "pipe_diameter",
        "cable_type_change_id": "change_flag", "cable_size_change_id": "change_flag",
        "starter_id": "starter", "cable_size_id": "cable_size",
    }
    MULTI_FIELDS = {"failure": "failure_reason", "workshop_opinion": "workshop_opinion",
                    "desc_tags": "desc_tag"}

    NUMERIC_FIELDS = (
        "well_depth", "prev_install_depth", "curr_install_depth", "static_level",
        "dynamic_level", "path_loss", "network_pressure", "total_head", "design_flow",
        "test_pressure", "test_flow", "flow_after_install", "flow_before_pull",
        "casing_length",
    )
    INT_FIELDS = (
        "j_year", "j_month", "j_day", "pump_prev_stages", "pump_stages", "pull_year",
        "pull_month", "old_install_year", "old_install_month", "working_months",
        "young_wells", "casing_repair_count",
    )
    TEXT_FIELDS = (
        "well_name_raw", "failure_other", "motor_plaque", "pump_plaque", "pump_prev_raw",
        "prev_install_date_raw", "test_date_raw", "cable_well", "workshop_note",
        "description", "install_supervisor", "flow_before_pull_date",
        "flow_after_install_date", "casing_pulled_diameter", "casing_material",
        "casing_diameter", "documents_ref",
    )
    DATE_FIELDS = ("op_date", "prev_install_date", "test_date")

    def tag_values(self, category_code):
        return [t.value for t in self.tags if t.category_code == category_code]


class RecordTag(db.Model):
    """One selected option of a multi-choice field.

    Replaces the original ``"a, b, c"`` string so that «کدام علت خرابی چند بار
    رخ داده؟» is a GROUP BY rather than string splitting.
    """
    __tablename__ = "record_tags"

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    category_code = db.Column(db.String(60), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("lookup_items.id"), index=True)
    value = db.Column(db.String(200), nullable=False, index=True)

    record = db.relationship("Record", back_populates="tags")
    item = db.relationship("LookupItem")
