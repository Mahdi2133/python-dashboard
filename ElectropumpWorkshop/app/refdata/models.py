"""The reference databases — each its own SQLite file, never the main one.

flowtest.db    دبی‌سنجی چاه‌ها: one row per test sheet, its pumping points
production.db  روند تولید: the well register of the production report and
               its monthly production, hours, average flow and pressure
videometry.db  ویدئومتری: one row per camera inspection of a well

They are bound through Flask-SQLAlchemy binds (``__bind_key__``), so each
lives in its own file next to wells.db (``refdata/<name>.db``), can be
replaced or re-imported on its own, and the main database never carries a
copy. A row knows the main register's well it belongs to (``main_well_id``)
through the codes the sources share with it — «کد تاسیس» is the register's
PM code, «کلاسه چاه» its well class — and, failing those, the well's name.
"""
from ..extensions import db
from ..services.jalali import local_now


# ── دبی‌سنجی ─────────────────────────────────────────────────────────────────
class FlowSource(db.Model):
    __bind_key__ = "flowtest"
    __tablename__ = "ft_sources"

    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(400), nullable=False)
    folder = db.Column(db.String(400))
    office = db.Column(db.String(80))
    sha1 = db.Column(db.String(40), index=True)
    sheets = db.Column(db.Integer, default=0)
    tests = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="ok")       # ok | skipped | error
    message = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=local_now)


class FlowTest(db.Model):
    __bind_key__ = "flowtest"
    __tablename__ = "ft_tests"
    __table_args__ = (db.UniqueConstraint("well_key", "test_date", name="uq_ft_well_date"),)

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey("ft_sources.id", ondelete="SET NULL"))
    sheet = db.Column(db.String(120))
    office = db.Column(db.String(80), index=True)
    well_name = db.Column(db.String(160), nullable=False)
    well_key = db.Column(db.String(160), nullable=False, index=True)
    well_class = db.Column(db.String(40), index=True)
    main_well_id = db.Column(db.Integer, index=True)
    match_method = db.Column(db.String(20))               # class | name | manual
    test_date = db.Column(db.String(10))                  # 1405/05/23
    test_date_num = db.Column(db.Integer, index=True)
    test_reason = db.Column(db.String(160))
    # the electropump at the time of the test
    pump_label = db.Column(db.String(60))                 # «384/8+62» as written
    pump_type = db.Column(db.String(20))
    pump_stages = db.Column(db.String(20))
    motor_kw = db.Column(db.Float)
    prev_test_date = db.Column(db.String(10))
    prev_pump_label = db.Column(db.String(60))
    last_install_date = db.Column(db.String(10))
    starter = db.Column(db.String(80))
    panel_power = db.Column(db.Float)
    # the well
    drill_year = db.Column(db.Integer)
    well_type = db.Column(db.String(40))                  # سیمانته / غیرسیمانته
    well_depth = db.Column(db.Float)
    install_depth = db.Column(db.Float)
    prev_install_depth = db.Column(db.Float)
    discharge_pipe = db.Column(db.Float)                  # inch
    casing = db.Column(db.Float)                          # inch
    design_flow = db.Column(db.Float)                     # l/s
    impeller_flow = db.Column(db.Float)
    static_level = db.Column(db.Float)                    # measured this test
    static_video = db.Column(db.Float)
    prev_static = db.Column(db.Float)
    zone = db.Column(db.String(40))
    network_type = db.Column(db.String(80))
    last_sholat = db.Column(db.String(80))
    last_rehab_date = db.Column(db.String(40))
    pull_reason = db.Column(db.String(200))
    # electrical
    voltage = db.Column(db.String(40))
    capacitor_kvar = db.Column(db.String(40))
    pf_capacitor = db.Column(db.String(40))
    amps_capacitor = db.Column(db.String(60))
    amps_with_capacitor = db.Column(db.String(60))
    ohm_pp = db.Column(db.String(60))
    ohm_pg = db.Column(db.String(60))
    allowed_current = db.Column(db.Float)
    power_subscription = db.Column(db.String(40))
    efficiency = db.Column(db.Float)                      # % at network pressure
    energy_intensity = db.Column(db.Float)                # kWh/m³
    cos_phi = db.Column(db.Float)
    # network-pressure summary (the newer template prints it separately)
    net_flow = db.Column(db.Float)
    net_pressure = db.Column(db.Float)                    # atm
    water_change = db.Column(db.Float)                    # m per l/s
    line_pressure = db.Column(db.Float)                   # bar
    set_pressure = db.Column(db.String(40))
    meter_status = db.Column(db.String(120))
    meter_brand = db.Column(db.String(120))
    expert_opinion = db.Column(db.Text)
    support_opinion = db.Column(db.Text)
    technician = db.Column(db.String(120))
    design_curve = db.Column(db.Text)                     # JSON [[head, m3h], …]
    raw_json = db.Column(db.Text)                         # every label read, as found
    imported_at = db.Column(db.DateTime, default=local_now)

    points = db.relationship("FlowPoint", back_populates="test",
                             cascade="all, delete-orphan", order_by="FlowPoint.point_no")


class FlowPoint(db.Model):
    __bind_key__ = "flowtest"
    __tablename__ = "ft_points"

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey("ft_tests.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    point_no = db.Column(db.Integer, nullable=False)      # «کارکرد N»
    at_network = db.Column(db.Boolean, default=False)     # «(فشار شبکه)»
    label = db.Column(db.String(60))
    amps = db.Column(db.String(60))
    head = db.Column(db.Float)
    pipe_loss = db.Column(db.Float)
    flow = db.Column(db.Float)                            # l/s
    water_change = db.Column(db.Float)
    water_column = db.Column(db.Float)
    dynamic_level = db.Column(db.Float)
    pressure = db.Column(db.Float)                        # atm
    mech_power = db.Column(db.Float)
    specific_energy = db.Column(db.Float)
    apparent_power = db.Column(db.Float)
    active_power = db.Column(db.Float)

    test = db.relationship("FlowTest", back_populates="points")


# ── روند تولید ───────────────────────────────────────────────────────────────
class ProdSource(db.Model):
    __bind_key__ = "production"
    __tablename__ = "pr_sources"

    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(400), nullable=False)
    year = db.Column(db.Integer)
    sha1 = db.Column(db.String(40), index=True)
    wells = db.Column(db.Integer, default=0)
    months = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="ok")
    message = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=local_now)


class ProdWell(db.Model):
    __bind_key__ = "production"
    __tablename__ = "pr_wells"

    id = db.Column(db.Integer, primary_key=True)
    facility_code = db.Column(db.String(40), unique=True, nullable=False)   # 10/21/4
    name = db.Column(db.String(160), nullable=False)
    name_key = db.Column(db.String(160), index=True)
    center_code = db.Column(db.String(20))
    urban_rural = db.Column(db.String(20))
    zone = db.Column(db.String(40))
    low_run_reason = db.Column(db.String(200))
    pump_install_date = db.Column(db.String(10))
    pump_label = db.Column(db.String(40))                 # «293 (9)» as written
    pump_type = db.Column(db.String(20))
    pump_stages = db.Column(db.String(20))
    motor_label = db.Column(db.String(40))                # «9A (30)»
    motor_model = db.Column(db.String(20))
    motor_kw = db.Column(db.Float)
    last_rehab_failure = db.Column(db.Text)
    last_rehab_date = db.Column(db.String(10))
    meter_status = db.Column(db.String(80))
    location_status = db.Column(db.String(80))
    relocations = db.Column(db.Integer)
    snapshot_year = db.Column(db.Integer)                 # the file the above came from
    main_well_id = db.Column(db.Integer, index=True)
    match_method = db.Column(db.String(20))

    months = db.relationship("ProdMonth", back_populates="well",
                             cascade="all, delete-orphan")


class ProdMonth(db.Model):
    __bind_key__ = "production"
    __tablename__ = "pr_months"
    __table_args__ = (db.UniqueConstraint("well_id", "year", "month", name="uq_pr_month"),)

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("pr_wells.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)          # 1..12
    production = db.Column(db.Float)                       # m³
    hours = db.Column(db.Float)
    avg_flow = db.Column(db.Float)                         # l/s
    pressure = db.Column(db.Float)
    pressure_type = db.Column(db.String(40))

    well = db.relationship("ProdWell", back_populates="months")


# ── ویدئومتری ────────────────────────────────────────────────────────────────
class VideoSource(db.Model):
    __bind_key__ = "videometry"
    __tablename__ = "vm_sources"

    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(400), nullable=False)
    sha1 = db.Column(db.String(40), index=True)
    rows = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="ok")
    message = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=local_now)


class VideoInspection(db.Model):
    __bind_key__ = "videometry"
    __tablename__ = "vm_inspections"
    __table_args__ = (db.UniqueConstraint("facility_code", "insp_date", name="uq_vm_code_date"),)

    id = db.Column(db.Integer, primary_key=True)
    facility_code = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(160))
    name_key = db.Column(db.String(160), index=True)
    center = db.Column(db.String(80))
    address = db.Column(db.Text)
    insp_date = db.Column(db.String(10))
    insp_date_num = db.Column(db.Integer, index=True)
    depth = db.Column(db.Float)                            # عمق چاه
    static_level = db.Column(db.Float)                     # سطح ایستابی
    screen_start = db.Column(db.Float)                     # عمق شروع مشبک
    no_screen = db.Column(db.Text)                         # JSON [{from, to}]
    repair = db.Column(db.Text)                            # JSON
    tear = db.Column(db.Text)
    change = db.Column(db.Text)
    clog = db.Column(db.Text)                              # JSON [{from, to, sev}]
    notes = db.Column(db.Text)
    defect_count = db.Column(db.Integer, default=0)
    main_well_id = db.Column(db.Integer, index=True)
    match_method = db.Column(db.String(20))
    source_id = db.Column(db.Integer)
