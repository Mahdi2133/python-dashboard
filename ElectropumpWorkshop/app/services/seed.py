"""Idempotent seeding of reference data.

Runs on every startup but only ever *adds* what is missing, so restarting the
EXE never resets a live database (requirement 3) and never resurrects an
option the admin deactivated.
"""
import logging

from ..extensions import db
from ..models import (FormField, FormSection, LookupAlias, LookupCategory,
                      LookupItem, Record, Well, WellAlias)
from .seed_data import FORM_SECTIONS, LOOKUP_CATEGORIES
from .seed_wells import WELLS_REFERENCE

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
    """Load the well register, then make sure no two wells share a name.

    The register is matched to what is already stored with the Persian fold, so
    a well the operations sheet spelled «ازاد شهر 2» is recognised as the
    reference's «آزاد شهر 2» and gains its PM code instead of becoming a second
    row. Fields already filled in by hand are left alone; only blanks are
    completed from the reference.
    """
    from .lookups import fold_persian, resolve_id, well_key

    existing, loose = {}, {}
    for well in Well.query.all():
        existing.setdefault(fold_persian(well.name), []).append(well)
        # A second index on the looser key, so the reference's «ده غیبی 1»
        # recognises a stored «ده غیبی یک» as the same well instead of adding a
        # duplicate beside it.
        loose.setdefault(well_key(well.name), []).append(well)

    added = updated = 0
    for name, pm_code, well_class, centre, kind, address in WELLS_REFERENCE:
        key = fold_persian(name)
        matches = existing.get(key) or loose.get(well_key(name))
        if not matches:
            well = Well(name=name, pm_code=pm_code or None,
                        well_class=well_class or None,
                        center_id=resolve_id("center", centre) if centre else None,
                        address=address or None, status=kind or "active",
                        is_active=True, is_verified=True)
            db.session.add(well)
            db.session.flush()
            existing[key] = [well]
            loose.setdefault(well_key(name), []).append(well)
            added += 1
            continue
        # When the loose key matched several rows, the register's identifiers
        # belong on the one already carrying this PM code, else the verified one.
        well = next((w for w in matches if pm_code and w.pm_code == pm_code),
                    next((w for w in matches if w.is_verified), matches[0]))
        changed = False
        # These four come from the register and nowhere else — operators do not
        # type PM codes — so the reference overwrites them. That is the point of
        # designating it the reference: an earlier, less accurate import must
        # not keep winning. The *name* is never touched.
        for attr, value in (("pm_code", pm_code), ("well_class", well_class)):
            if value and getattr(well, attr) != value:
                setattr(well, attr, value)
                changed = True
        if address and not well.address:
            well.address = address
            changed = True
        if centre:
            centre_id = resolve_id("center", centre)
            if centre_id and well.center_id != centre_id:
                well.center_id = centre_id
                changed = True
        if not well.is_verified:
            well.is_verified = True
            changed = True
        if changed:
            updated += 1
    db.session.commit()
    return {"wells_added": added, "wells_updated": updated}


def deduplicate_wells() -> dict:
    """Fold wells whose names differ only in spelling into one row.

    The operations spreadsheets spell the same well several ways, which is why
    the picker used to show «ازاد شهر 2» and «آزاد شهر 2» — and «ده غیبی یک»
    and «ده غیبی 1» — side by side. ``well_key`` decides what "the same name"
    means; the survivor is the row the reference register recognises (it
    carries the PM code), and the others hand over their records, become
    aliases of the survivor and are deactivated, so no history is lost and no
    name appears twice.

    Two wells that carry *different* PM codes are never merged however alike
    their names read: the register's own key outranks any spelling rule, and a
    wrong merge would move one well's operations onto another.
    """
    from .lookups import pm_digits, well_key

    groups = {}
    for well in Well.query.filter_by(is_active=True).all():
        groups.setdefault(well_key(well.name), []).append(well)
        # The PM code is the register's own unique key, so two rows carrying the
        # same one are the same well however their names were spelled.
        if well.pm_code:
            groups.setdefault(("pm", well.pm_code), []).append(well)
        # The two source workbooks write that key differently — «10/24/41» in
        # one and «102441» in the other — which is how «گلشهر9 جدید» ended up
        # beside «گلشهر9 جدید (BOT)», and «خاتم» beside «خاتم الانبیاء 1». The
        # کلاسه must agree as well: on this register the digits alone could in
        # principle collide (10/22/7 and 10/2/27 both read 10227), while the
        # pair together identifies a well exactly.
        if well.pm_code and well.well_class:
            groups.setdefault(("pm+class", pm_digits(well.pm_code),
                               well.well_class), []).append(well)

    merged = moved = kept_apart = 0
    done = set()
    for key, wells in groups.items():
        wells = [w for w in wells if w.id not in done and w.is_active]
        if len(wells) < 2:
            continue
        codes = {pm_digits(w.pm_code) for w in wells if w.pm_code}
        if len(codes) > 1 and not isinstance(key, tuple):
            # Same spelling, two register entries: a real pair of wells whose
            # names collide. Leave both — the picker shows the PM code beside
            # the name, which is what tells them apart.
            kept_apart += 1
            log.warning("Not merging %s: conflicting PM codes %s",
                        [w.name for w in wells], sorted(codes))
            continue
        # Prefer the row with a PM code, and among those the one spelling it
        # the canonical way («10/24/41»): that is the row Well_Details — the
        # register designated the authority — contributed. Then the one
        # carrying the most work.
        wells.sort(key=lambda w: (bool(w.pm_code), "/" in (w.pm_code or ""),
                                  w.is_verified,
                                  w.records.filter_by(is_active=True).count()),
                   reverse=True)
        keeper, others = wells[0], wells[1:]
        for dup in others:
            moved += Record.query.filter_by(well_id=dup.id).update(
                {"well_id": keeper.id}, synchronize_session=False)
            if (dup.name != keeper.name
                    and not WellAlias.query.filter_by(alias=dup.name).first()):
                db.session.add(WellAlias(well_id=keeper.id, alias=dup.name))
            for attr in ("pm_code", "well_class", "address", "code", "center_id",
                         "depth"):
                if not getattr(keeper, attr) and getattr(dup, attr):
                    setattr(keeper, attr, getattr(dup, attr))
            dup.is_active = False
            dup.notes = (dup.notes or "") + f" [در «{keeper.name}» ادغام شد]"
            done.add(dup.id)
            merged += 1
    db.session.commit()
    if merged:
        log.info("Merged %s duplicate wells, moved %s records", merged, moved)
    return {"wells_merged": merged, "records_moved": moved,
            "kept_apart": kept_apart}


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
                visible_when=fspec.get("visible_when"),
                show_in_table=fspec.get("show_in_table", False),
                table_order=fspec.get("table_order", 0),
                export_header=fspec.get("export_header"),
            ))
            added_fields += 1
    db.session.commit()
    return {"sections": added_sections, "fields": added_fields}


# Corrections to built-in field definitions that must also reach databases
# seeded by an earlier release. Each entry is applied only while the column
# still holds the value the old release wrote, so an admin's own edit is never
# overwritten.  field_name -> {attr: (expected_old, new)}
_BUILTIN_FIXES = {
    "contractor": {
        # Only asked for when the work was contracted out, and therefore no
        # longer mandatory for in-house jobs.
        "visible_when": (None, "executor=پیمانی"),
        "is_required": (True, False),
        "sort_order": (3, 4),
        "help_text": (None, "فقط وقتی مجری «پیمانی» باشد پرسیده می‌شود."),
    },
    "executor": {
        "sort_order": (4, 3),
        "help_text": ("از شیت «99-403» اکسل کارگاه: امانی یا پیمانی.",
                      "کار توسط نیروی امانی انجام شده یا پیمانکار؟"),
    },
}


def apply_builtin_field_fixes() -> dict:
    changed = 0
    for field_name, fixes in _BUILTIN_FIXES.items():
        field = FormField.query.filter_by(field_name=field_name,
                                          is_builtin=True).one_or_none()
        if field is None:
            continue
        for attr, (old, new) in fixes.items():
            if getattr(field, attr) == old:
                setattr(field, attr, new)
                changed += 1
    if changed:
        db.session.commit()
        log.info("Applied %s corrections to built-in fields", changed)
    return {"builtin_fixes": changed}


def seed_admin() -> dict:
    """Create the first administrator so a fresh install can be logged into.

    Only ever runs when the user table is empty. The password is the well-known
    default and the account is flagged to force a change at first login, which
    the login screen enforces.
    """
    from ..models.auth import AppUser
    if AppUser.query.count():
        return {"admin_created": 0}
    admin = AppUser(username="admin", role="admin", is_active=True,
                    first_name="مدیر", last_name="سیستم",
                    must_change_password=True,
                    notes="حساب پیش‌فرض؛ پس از اولین ورود رمز عبور را تغییر دهید.")
    admin.set_password("admin")
    db.session.add(admin)
    db.session.commit()
    log.warning("Default administrator created (admin/admin) — must be changed")
    return {"admin_created": 1}


def seed_all(force: bool = False) -> dict:
    result = {}
    result.update(seed_admin())
    result.update(seed_lookups())
    result.update(seed_wells())
    result.update(deduplicate_wells())
    result.update(seed_form())
    result.update(apply_builtin_field_fixes())
    result["changed"] = any(v for k, v in result.items() if isinstance(v, int))
    if result["changed"]:
        log.info("Seed applied: %s", result)
    return result
