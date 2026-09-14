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

from ..extensions import db

FIELD_TYPES = (
    "text", "number", "textarea", "date", "jalali_date", "select", "radio",
    "checkbox", "multiselect", "autocomplete",
)


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

    fields = db.relationship("FormField", back_populates="section",
                             cascade="all, delete-orphan", order_by="FormField.sort_order")

    def to_dict(self, include_fields=False, active_only=True):
        data = {
            "id": self.id, "code": self.code, "title": self.title, "icon": self.icon,
            "sort_order": self.sort_order, "full_width": self.full_width,
            "columns": self.columns, "is_active": self.is_active,
            "description": self.description,
        }
        if include_fields:
            fields = [f for f in self.fields if f.is_active or not active_only]
            data["fields"] = [f.to_dict(active_only=active_only) for f in fields]
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
    visible_when = db.Column(db.String(120))
    show_in_table = db.Column(db.Boolean, nullable=False, default=False)
    table_order = db.Column(db.Integer, nullable=False, default=0)
    export_header = db.Column(db.String(200))

    section = db.relationship("FormSection", back_populates="fields")
    options = db.relationship("FormFieldOption", back_populates="field",
                              cascade="all, delete-orphan",
                              order_by="FormFieldOption.sort_order")

    CHOICE_TYPES = ("select", "radio", "checkbox", "multiselect", "autocomplete")

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
        }


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    record = db.relationship("Record", back_populates="dynamic_values")
    field = db.relationship("FormField")

    @property
    def value(self):
        if self.value_date is not None:
            return self.value_date.isoformat()
        if self.value_num is not None:
            return self.value_num
        return self.value_text
