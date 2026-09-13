"""Idempotent seeding of reference data.

Runs on every startup but only ever *adds* what is missing, so restarting the
EXE never resets a live database (requirement 3) and never resurrects an
option the admin deactivated.
"""
import logging

from ..extensions import db
from ..models import (FormField, FormSection, LookupAlias, LookupCategory,
                      LookupItem, Well)
from .seed_data import FORM_SECTIONS, LOOKUP_CATEGORIES
from .seed_wells import ALL_WELLS

log = logging.getLogger(__name__)


def seed_lookups() -> dict:
    added_cats = added_items = added_aliases = 0
    for order, spec in enumerate(LOOKUP_CATEGORIES):
        cat = LookupCategory.query.filter_by(code=spec["code"]).one_or_none()
        if cat is None:
            cat = LookupCategory(
                code=spec["code"], name_fa=spec["name_fa"],
                allows_multiple=spec.get("multiple", False),
                is_system=spec.get("is_system", True), sort_order=order,
            )
            db.session.add(cat)
            db.session.flush()
            added_cats += 1

        existing = {i.value: i for i in cat.items}
        for idx, item_spec in enumerate(spec["items"]):
            item = existing.get(item_spec["value"])
            if item is None:
                item = LookupItem(
                    category_id=cat.id, value=item_spec["value"],
                    label=item_spec["label"], icon=item_spec.get("icon"),
                    sort_order=idx,
                    notes="منبع: " + ("فرم HTML" if item_spec["source"] == "html"
                                      else "اکسل کارگاه"),
                )
                db.session.add(item)
                db.session.flush()
                added_items += 1

            known = {a.alias for a in item.aliases}
            for alias in item_spec.get("aliases", []):
                if alias in known:
                    continue
                # An alias may only belong to one option within a category.
                clash = LookupAlias.query.filter_by(category_id=cat.id,
                                                    alias=alias).one_or_none()
                if clash is not None:
                    continue
                db.session.add(LookupAlias(category_id=cat.id, item_id=item.id,
                                           alias=alias))
                added_aliases += 1
    db.session.commit()
    return {"categories": added_cats, "items": added_items, "aliases": added_aliases}


def seed_wells() -> dict:
    existing = {row[0] for row in db.session.query(Well.name).all()}
    added = 0
    for name in ALL_WELLS:
        # ALL_WELLS is transcribed from the HTML and repeats a couple of names.
        if name in existing:
            continue
        existing.add(name)
        db.session.add(Well(name=name, is_active=True, is_verified=True))
        added += 1
    db.session.commit()
    return {"wells": added}


def seed_form() -> dict:
    added_sections = added_fields = 0
    for order, spec in enumerate(FORM_SECTIONS):
        section = FormSection.query.filter_by(code=spec["code"]).one_or_none()
        if section is None:
            section = FormSection(
                code=spec["code"], title=spec["title"], icon=spec.get("icon"),
                sort_order=order, full_width=spec.get("full_width", False),
                columns=spec.get("columns", 3),
            )
            db.session.add(section)
            db.session.flush()
            added_sections += 1

        for idx, fspec in enumerate(spec["fields"]):
            if FormField.query.filter_by(field_name=fspec["field_name"]).first():
                continue
            db.session.add(FormField(
                section_id=section.id,
                field_name=fspec["field_name"], label=fspec["label"],
                field_type=fspec["field_type"], model_attr=fspec.get("model_attr"),
                lookup_category=fspec.get("lookup_category"),
                placeholder=fspec.get("placeholder"), help_text=fspec.get("help_text"),
                default_value=fspec.get("default_value"),
                is_required=fspec.get("required", False),
                is_builtin=True, allow_other=fspec.get("allow_other", False),
                sort_order=idx, col_span=fspec.get("col_span", 1),
                min_value=fspec.get("min_value"), max_value=fspec.get("max_value"),
                max_length=fspec.get("max_length"), step=fspec.get("step"),
                show_in_table=fspec.get("show_in_table", False),
                table_order=fspec.get("table_order", 0),
                export_header=fspec.get("export_header"),
            ))
            added_fields += 1
    db.session.commit()
    return {"sections": added_sections, "fields": added_fields}


def seed_all(force: bool = False) -> dict:
    result = {}
    result.update(seed_lookups())
    result.update(seed_wells())
    result.update(seed_form())
    result["changed"] = any(v for k, v in result.items() if isinstance(v, int))
    if result["changed"]:
        log.info("Seed applied: %s", result)
    return result
