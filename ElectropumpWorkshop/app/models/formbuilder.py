"""Form builder — the data-entry form is described by rows, not by markup.

``FormSection`` / ``FormField`` / ``FormFieldOption`` reproduce the eight
sections and 51 inputs of the original HTML exactly, and let an admin add,
reorder, retitle or deactivate fields afterwards without touching code.

A field is either **mapped** — ``model_attr`` names a real column on
``Record`` — or **dynamic**, in which case its answers land in
``record_dynamic_values``. Built-in fields are mapped, so reports keep working;
anything the admin invents later is dynamic and still exportable.
"""
from datetime import datetime

from ..services.jalali import local_now

from ..extensions import db

FIELD_TYPES = (
    "text", "number", "textarea", "date", "jalali_date", "select", "radio",
    "checkbox", "multiselect", "autocomplete",
    # A checklist is a checkbox group that reads as a list of things to do:
    # one item per line, ticked off. It is its own type because a stage often
    # wants to *show* the list somebody else ticked, and «چندانتخابی» laid out
    # as a row of buttons is unreadable once there are a dozen of them.
    "checklist",
    # «مستند»: a slot where a named document is uploaded — «عکس پلاک موتور»,
    # «فرم دبی‌سنجی» — optional or required like any other field.
    "file",
    # «محاسباتی»: filled by a formula over other fields of the form, e.g.
    # Sp.Cap = دبی × 0.001 ÷ سطح دینامیک; shown, never typed.
    "formula",
    # «فیلد مشترک»: the same answer shown in a second form. It stores nothing
    # of its own — it draws and writes the field it points at, so «تیپ پمپ
    # قبلی» in «فرم انتخاب پمپ» and in «مشخصات پمپ» is one value, not two.
    "mirror",
    # «چند مقدار عددی»: one answer made of several numbers, e.g. the three
    # phases of «عدم تعادل جریان» — فاز ۱ / فاز ۲ / فاز ۳. The parts are named by
    # the field's own options (default: three phases).
    "numbers",
    # «نمودار»: a chart drawn from other fields of the form as they are filled
    # (series of x/y fields, an axis on either side, optional trend line). It
    # stores nothing.
    "chart",
    # «اقلام انبار»: a small table — item, specification, plaque, condition,
    # quantity — whose rows are posted to the warehouse ledger when the stage
    # is sent (which warehouse, in or out, and why: ``wh_config``).
    "wh_lines",
)

DEFAULT_PART_LABELS = ["فاز ۱", "فاز ۲", "فاز ۳"]


class FormSection(db.Model):
    __tablename__ = "form_sections"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    icon = db.Column(db.String(16))
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    full_width = db.Column(db.Boolean, nullable=False, default=False)
    columns = db.Column(db.Integer, nullable=False, default=3)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    description = db.Column(db.Text)
    # «این بخش را فقط وقتی نشان بده که …», in the same «field=value» shape a
    # field's own rule uses. A whole section is the unit here because the
    # parameters of one علت خرابی belong together: tick «سوختن الکتروپمپ» and
    # its dozen readings appear as one block, not one field at a time.
    visible_when = db.Column(db.String(1000))
    # Drawn on the standalone «ثبت اطلاعات» page too, or only inside process
    # stages (the pump-selection forms belong to the کارتابل).
    show_on_entry = db.Column(db.Boolean, nullable=False, default=True)
    # «فیلدهای محاسباتی پنهان باشند»: the section's formula fields are folded
    # behind a «نمایش محاسبات» toggle — the readings are typed, the dozen
    # numbers worked out of them stay out of the way until somebody asks.
    collapse_formulas = db.Column(db.Boolean, nullable=False, default=False)
    # «گروه تکرارشونده»: sections sharing this key are the points of one test
    # (نقطه ۱ … ۵) — the first is shown, the others open with «➕» as needed.
    repeat_group = db.Column(db.String(40))
    # «چیدمان»: '' — fields in columns; 'grid' — «جدول ردیفی»: fields whose
    # names end in a number (fc_q1 … fc_q5) are the rows of one table, a
    # column per quantity, the row named by ``grid_label`` («کارکرد {n}»).
    layout = db.Column(db.String(20))
    grid_label = db.Column(db.String(80))

    fields = db.relationship("FormField", back_populates="section",
                             cascade="all, delete-orphan", order_by="FormField.sort_order")

    def to_dict(self, include_fields=False, active_only=True):
        data = {
            "id": self.id, "code": self.code, "title": self.title, "icon": self.icon,
            "sort_order": self.sort_order, "full_width": self.full_width,
            "columns": self.columns, "is_active": self.is_active,
            "description": self.description,
            "visible_when": self.visible_when,
            "show_on_entry": self.show_on_entry is not False,
            "collapse_formulas": bool(self.collapse_formulas),
            "repeat_group": self.repeat_group or None,
            "layout": self.layout or "",
            "grid_label": self.grid_label or None,
        }
        if include_fields:
            fields = [f for f in self.fields if f.is_active or not active_only]
            if active_only:
                # drawn for a form: a «فیلد مشترک» becomes the field it shows
                drawn = [f.render_dict(active_only=True) for f in fields]
                data["fields"] = [d for d in drawn if d is not None]
            else:
                data["fields"] = [f.to_dict(active_only=False) for f in fields]
        return data


class FormField(db.Model):
    __tablename__ = "form_fields"

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("form_sections.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    field_name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    field_type = db.Column(db.String(30), nullable=False, default="text")
    # Column on Record this field writes to. NULL ⇒ stored as a dynamic value.
    model_attr = db.Column(db.String(80))
    # Lookup category supplying the options, when the field is a choice field.
    lookup_category = db.Column(db.String(60))
    placeholder = db.Column(db.String(200))
    help_text = db.Column(db.Text)
    default_value = db.Column(db.String(200))
    is_required = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Built-in fields mirror the original form; they may be hidden or renamed
    # but not deleted, because Record columns and reports depend on them.
    is_builtin = db.Column(db.Boolean, nullable=False, default=False)
    allow_other = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    col_span = db.Column(db.Integer, nullable=False, default=1)
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    max_length = db.Column(db.Integer)
    step = db.Column(db.String(20))
    # "field=value" — the field is only shown while that other field holds that
    # value. Used for «نام پیمانکار», which is meaningless unless the work was
    # done by a contractor (مجری = پیمانی).
    visible_when = db.Column(db.String(1000))
    # Where this field's suggested value comes from on the well's last
    # operation: another field's name, or «@op_date» / «@j_year» / «@j_month»
    # for when it happened. «تیپ الکتروموتور قبلی» is «تیپ الکتروموتور فعلی»
    # as it was the last time this well was worked on — the admin says so in
    # the form builder instead of the code knowing it.
    prefill_from = db.Column(db.String(80))
    # «فیلد مشترک»: field_name of the field this one shows and writes.
    mirror_of = db.Column(db.String(80))
    # «محاسباتی»: the formula, over fields as [field_name] or [label].
    formula = db.Column(db.Text)
    # «مستند»: accepted file types (e.g. «image/*,.pdf») and one or many files.
    file_accept = db.Column(db.String(200))
    file_multiple = db.Column(db.Boolean, nullable=False, default=True)
    # «تأیید گزینه»: answers (option values, JSON list) that need somebody's
    # approval — whichever stage records one of them cannot be finalised until
    # that user (``approval_user_id``) has approved it.
    approval_options = db.Column(db.Text)
    approval_user_id = db.Column(db.Integer)
    # Several approvers, every one of whom must approve (comma-separated ids;
    # ``approval_user_id`` is kept as the first of them).
    approval_user_ids = db.Column(db.String(200))
    # A choice field the approver answers when approving — «ارجاع به امین»
    # where امین also says where the work goes next.
    approval_answer_field = db.Column(db.String(80))
    # «مرحله‌ی پرکردن»: workflow stage ids (comma-separated) where this field is
    # filled. On that stage it is asked, whatever forms the stage carries;
    # before it the field is not shown, after it it is shown read-only.
    fill_stage_ids = db.Column(db.String(200))
    # Several «تأیید گزینه» rules on one field, each its own answers → its own
    # approvers (JSON: [{"options": [...], "approvers": [ids], "answer_field": name}]).
    # When empty, the single rule in the columns above is the field's rule.
    approval_rules = db.Column(db.Text)
    # «مانع ارسال»: answers (JSON list) with which the stage cannot be sent on.
    block_options = db.Column(db.Text)
    # «محاسباتی»: what the formula gives — a number (default) or a text.
    result_type = db.Column(db.String(10))
    # «نمودار»: JSON {"series": [{"label", "x": [fields], "y": [fields],
    # "axis": "left"|"right", "trend": "poly2"|"poly2_0"|"power"|"linear"|""}],
    # "x_label", "y_label", "y2_label"}
    chart_config = db.Column(db.Text)
    # «اقلام انبار»: JSON {"warehouse": "equipment"|"parts", "direction":
    # "in"|"out", "reason": …, "kinds": […], "conditions": […], "spec": bool}
    wh_config = db.Column(db.Text)
    # «طبقات از کاتالوگ»: the field naming the pump type this stage count
    # belongs to — the choices are that type's models in the pump catalogue
    # («384/10»), and picking one fills the type in too.
    stages_of = db.Column(db.String(80))
    show_in_table = db.Column(db.Boolean, nullable=False, default=False)
    table_order = db.Column(db.Integer, nullable=False, default=0)
    export_header = db.Column(db.String(200))

    section = db.relationship("FormSection", back_populates="fields")
    options = db.relationship("FormFieldOption", back_populates="field",
                              cascade="all, delete-orphan",
                              order_by="FormFieldOption.sort_order")

    CHOICE_TYPES = ("select", "radio", "checkbox", "multiselect",
                    "autocomplete", "checklist")

    @property
    def is_choice(self):
        return self.field_type in self.CHOICE_TYPES

    @property
    def options_source(self):
        """Where this field's options live, so the editor knows what to edit.

        ``lookup``  — a shared category in ``lookup_items``; editing it changes
                      every field that draws on the same list.
        ``own``     — options attached to this field alone.
        ``months``  — the built-in Jalali month list.
        ``wells``   — the wells table (the well autocomplete).
        """
        if self.field_type == "numbers":
            return "own"                  # the names of its parts
        if not self.is_choice:
            return None
        if self.lookup_category == "__months__":
            return "months"
        if self.field_name == "well":
            return "wells"
        return "lookup" if self.lookup_category else "own"

    def to_dict(self, active_only=True):
        opts = [o for o in self.options if o.is_active or not active_only]
        return {
            "id": self.id, "section_id": self.section_id, "section": self.section.code
            if self.section else None,
            "field_name": self.field_name, "label": self.label,
            "field_type": self.field_type, "model_attr": self.model_attr,
            "lookup_category": self.lookup_category, "placeholder": self.placeholder,
            "help_text": self.help_text, "default_value": self.default_value,
            "is_required": self.is_required, "is_active": self.is_active,
            "prefill_from": self.prefill_from,
            "is_builtin": self.is_builtin, "allow_other": self.allow_other,
            "sort_order": self.sort_order, "col_span": self.col_span,
            "min_value": self.min_value, "max_value": self.max_value,
            "max_length": self.max_length, "step": self.step,
            "visible_when": self.visible_when,
            "show_in_table": self.show_in_table, "table_order": self.table_order,
            "export_header": self.export_header or self.label,
            "own_options": [o.to_dict() for o in opts],
            "is_choice": self.is_choice,
            "options_source": self.options_source,
            "mirror_of": self.mirror_of, "formula": self.formula,
            "file_accept": self.file_accept, "file_multiple": self.file_multiple,
            "approval_options": self.approval_option_list,
            "approval_user_id": self.approval_user_id,
            "approval_user_ids": self.approver_ids,
            "approval_answer_field": self.approval_answer_field,
            "approval_rules": self.approval_rule_list,
            "block_options": self.block_option_list,
            "result_type": self.result_type or "number",
            "chart_config": self.chart_spec,
            "wh_config": (self._json(self.wh_config, {})
                          if self.field_type == "wh_lines" else None),
            "stages_of": self.stages_of or None,
            "part_labels": self.part_labels if self.field_type == "numbers" else None,
            "fill_stage_ids": self.fill_stage_list,
        }

    @staticmethod
    def _json(raw, default):
        import json
        try:
            got = json.loads(raw) if raw else default
        except ValueError:
            return default
        return got if isinstance(got, type(default)) else default

    @property
    def approval_rule_list(self) -> list:
        """Every «تأیید گزینه» rule of this field: which answers, whose approval,
        and the question the approver answers (if any)."""
        out = []
        for r in self._json(self.approval_rules, []):
            if not isinstance(r, dict):
                continue
            opts = [str(x) for x in r.get("options") or [] if str(x).strip()]
            who = [int(x) for x in r.get("approvers") or [] if str(x).isdigit()]
            if opts and who:
                # «الزامی»: the stage waits for this ruling. Otherwise the
                # referral only tells these people what was recorded.
                out.append({"options": opts, "approvers": who,
                            "answer_field": r.get("answer_field") or None,
                            "required": bool(r.get("required"))})
        if out:
            return out
        if self.approval_option_list and self.approver_ids:
            return [{"options": self.approval_option_list, "approvers": self.approver_ids,
                     "answer_field": self.approval_answer_field, "required": False}]
        return []

    @property
    def block_option_list(self) -> list:
        return [str(x) for x in self._json(self.block_options, []) if str(x).strip()]

    @property
    def chart_spec(self) -> dict | None:
        if self.field_type != "chart":
            return None
        return self._json(self.chart_config, {})

    @property
    def part_labels(self) -> list:
        """The names of a «چند مقدار عددی» field's parts (its own options)."""
        labels = [o.label or o.value for o in self.options if o.is_active]
        return labels or list(DEFAULT_PART_LABELS)

    @property
    def approver_ids(self) -> list:
        """Everyone who must approve this field's marked answers."""
        ids = [int(x) for x in (self.approval_user_ids or "").split(",") if x.strip().isdigit()]
        if self.approval_user_id and self.approval_user_id not in ids:
            ids.insert(0, self.approval_user_id)
        return ids

    @property
    def approval_option_list(self) -> list:
        import json
        try:
            got = json.loads(self.approval_options or "[]")
        except ValueError:
            return []
        return [str(x) for x in got if str(x).strip()] if isinstance(got, list) else []

    @property
    def fill_stage_list(self) -> list:
        return [int(x) for x in (self.fill_stage_ids or "").split(",") if x.strip().isdigit()]

    def mirror_source(self, _seen=None):
        """The field a «فیلد مشترک» finally draws, following chains."""
        if self.field_type != "mirror" or not self.mirror_of:
            return self
        seen = _seen or set()
        if self.id in seen:
            return None
        seen.add(self.id)
        target = FormField.query.filter_by(field_name=self.mirror_of).first()
        if target is None:
            return None
        return target.mirror_source(seen)

    def render_dict(self, active_only=True):
        """What a form draws for this field.

        An ordinary field is itself. A «فیلد مشترک» is drawn as the field it
        points at — its type, options and field_name, so the answer lands in
        one place — but with this form's label, position and rule.
        """
        if self.field_type != "mirror":
            return self.to_dict(active_only=active_only)
        source = self.mirror_source()
        if source is None or not source.is_active:
            return None
        data = source.to_dict(active_only=active_only)
        data.update({
            "section_id": self.section_id,
            "section": self.section.code if self.section else None,
            "label": self.label or source.label,
            "sort_order": self.sort_order, "col_span": self.col_span,
            "help_text": self.help_text or source.help_text,
            "visible_when": self.visible_when or source.visible_when,
            # required here even if optional where it lives («عمق نصب» in the
            # install form, though «عمق نصب فعلی» is optional on the entry page)
            "is_required": bool(source.is_required or self.is_required),
            "mirror_id": self.id, "mirror_name": self.field_name,
            "mirrored": True,
        })
        return data


class FormFieldOption(db.Model):
    """Options attached directly to a field rather than to a lookup category.

    Used by admin-created fields; built-in choice fields point at a shared
    lookup category instead, so «پیمانکار» stays one list everywhere.
    """
    __tablename__ = "form_field_options"

    id = db.Column(db.Integer, primary_key=True)
    field_id = db.Column(db.Integer, db.ForeignKey("form_fields.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    value = db.Column(db.String(200), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(16))
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    field = db.relationship("FormField", back_populates="options")

    def to_dict(self):
        return {"id": self.id, "value": self.value, "label": self.label,
                "icon": self.icon, "sort_order": self.sort_order,
                "is_active": self.is_active}


class RecordDynamicValue(db.Model):
    """Answer to an admin-created field."""
    __tablename__ = "record_dynamic_values"
    __table_args__ = (db.UniqueConstraint("record_id", "field_id", name="uq_record_field"),)

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    field_id = db.Column(db.Integer, db.ForeignKey("form_fields.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    value_text = db.Column(db.Text)
    value_num = db.Column(db.Float)
    value_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)

    record = db.relationship("Record", back_populates="dynamic_values")
    field = db.relationship("FormField")

    @property
    def value(self):
        """The answer as the operator typed it.

        A date comes back in Jalali, not ISO: this is what the edit form puts
        straight back into a jalali_date input and what the exports print, and
        an operator who entered ۱۴۰۵/۰۶/۲۳ must never be shown 2026-09-14.
        """
        if self.value_date is not None:
            from ..services.jalali import to_jalali_str
            return to_jalali_str(self.value_date)
        if self.value_num is not None:
            return self.value_num
        return self.value_text
