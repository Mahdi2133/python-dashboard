"""Idempotent seeding of reference data.

Runs on every startup but only ever *adds* what is missing, so restarting the
EXE never resets a live database (requirement 3) and never resurrects an
option the admin deactivated.
"""
import logging

from ..extensions import db
from ..models import (FormField, FormSection, LookupAlias, LookupCategory,
                      LookupItem, Record, Well, WellAlias,
                      WorkflowDefinition, WorkflowStage, WorkflowStageItem)
from .seed_data import (FORM_SECTIONS, LOOKUP_CATEGORIES, WORKFLOW_CODE,
                        WORKFLOW_STAGES)
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
                    sort_order=idx, is_locked=item_spec.get("locked", False),
                    notes="منبع: " + ("فرم HTML" if item_spec["source"] == "html"
                                      else "اکسل کارگاه"),
                )
                db.session.add(item)
                db.session.flush()
                added_items += 1

            if item_spec.get("locked") and not item.is_locked:
                item.is_locked = True       # a rule added after this DB was made

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


def _take_name(well: Well, better: str) -> bool:
    """Rename ``well`` to ``better``, moving whoever holds that name aside.

    ``wells.name`` is unique across active and retired rows alike, and the
    better spelling is usually sitting on the retired duplicate we just merged
    away. That row is parked under a suffixed name — it is history, not a well
    anyone will look up — and its old name becomes an alias of the survivor.
    """
    if not better or better == well.name:
        return False
    holder = Well.query.filter(Well.name == better, Well.id != well.id).first()
    if holder is not None:
        if holder.is_active:
            return False            # two live wells; not ours to rename
        holder.name = f"{better} (ادغام‌شده #{holder.id})"
        db.session.flush()
    previous = well.name
    well.name = better
    db.session.flush()
    if previous and not WellAlias.query.filter_by(alias=previous).first():
        db.session.add(WellAlias(well_id=well.id, alias=previous))
    # An alias equal to the name is noise, and makes the same well look like a
    # match twice when the picker ranks aliases alongside names.
    WellAlias.query.filter_by(well_id=well.id, alias=better).delete()
    log.info("Well %r renamed to the better spelling %r", previous, better)
    return True


def _absorb_well(keeper: Well, dup: Well) -> int:
    """Move ``dup``'s work onto ``keeper`` and retire it. Returns records moved."""
    from .lookups import best_name, well_key

    moved = Record.query.filter_by(well_id=dup.id).update(
        {"well_id": keeper.id}, synchronize_session=False)
    # Which row survives is decided by the register's identifiers; what it is
    # *called* is decided by which spelling reads better. «اسلام اباد 16»
    # carries the official PM code, but the well is «اسلام آباد 16».
    if well_key(dup.name) == well_key(keeper.name):
        _take_name(keeper, best_name([keeper.name, dup.name]))
    if (dup.name != keeper.name
            and not WellAlias.query.filter_by(alias=dup.name).first()):
        db.session.add(WellAlias(well_id=keeper.id, alias=dup.name))
    for attr in ("pm_code", "well_class", "address", "code", "center_id", "depth"):
        if not getattr(keeper, attr) and getattr(dup, attr):
            setattr(keeper, attr, getattr(dup, attr))
    dup.is_active = False
    dup.notes = (dup.notes or "") + f" [در «{keeper.name}» ادغام شد]"
    return moved


def normalize_well_names() -> dict:
    """Adopt the best spelling each well is known by.

    A candidate must be a name this well already answers to: either the same
    name spelled differently («اسلام اباد 16» → «اسلام آباد 16») or the same
    name without its قدیم/جدید tail («حجت 1 (جدید)» → «حجت 1», which it already
    absorbed). It never invents a name, and «چهارراه گیتی» never becomes
    «چهارراه گیتی (BOT)». The previous spelling stays as an alias, so anyone
    searching the old way still finds the well and its records.
    """
    from .lookups import preferred_name, qualifier_base_key, well_key

    renamed = 0
    for well in Well.query.filter_by(is_active=True).all():
        key = well_key(well.name)
        base = qualifier_base_key(well.name)
        candidates = [well.name] + [
            a.alias for a in well.aliases
            if well_key(a.alias) == key or (base and well_key(a.alias) == base)]
        if len(candidates) < 2:
            continue
        if _take_name(well, preferred_name(candidates)):
            renamed += 1
    db.session.commit()
    if renamed:
        log.info("Adopted a better spelling for %s wells", renamed)
    return {"wells_renamed": renamed}


def _merge_qualifier_variants(done: set) -> tuple:
    """Fold «امامیه 17 (جدید)» and «امامیه 17 (قدیم)» back into «امامیه 17».

    Operators annotate a well as قدیم or جدید while typing, and each spelling
    became its own row, so the picker offered three entries for one well and
    the records table listed the same well three ways.

    Wells are grouped by the name they share once a trailing قدیم/جدید is
    taken off, so it works in either direction: the annotation may be the row
    without a PM code («امام رضا 13 ( قدیم )» beside the register's «امام رضا
    13») or the one with it («چهار برج قدیم» beside «چهاربرج»). A group whose
    members carry *different* PM codes is left alone — those are two register
    entries, not one well written twice — and the survivor takes the plainest
    name in the group.
    """
    from .lookups import pm_digits, preferred_name, qualifier_base_key, well_key

    groups = {}
    for well in Well.query.filter_by(is_active=True).all():
        if well.id in done:
            continue
        groups.setdefault(qualifier_base_key(well.name) or well_key(well.name),
                          []).append(well)

    merged = moved = 0
    for key, wells in groups.items():
        if len(wells) < 2:
            continue
        if not any(qualifier_base_key(w.name) for w in wells):
            continue                    # nothing here is a qualified variant
        codes = {pm_digits(w.pm_code) for w in wells if w.pm_code}
        if len(codes) > 1:
            log.warning("Not folding %s: they are separate register entries %s",
                        [w.name for w in wells], sorted(codes))
            continue
        wells.sort(key=lambda w: (bool(w.pm_code), w.is_verified,
                                  w.records.filter_by(is_active=True).count()),
                   reverse=True)
        keeper, others = wells[0], wells[1:]
        name = preferred_name([w.name for w in wells])
        for dup in others:
            moved += _absorb_well(keeper, dup)
            done.add(dup.id)
            merged += 1
            log.info("Merged qualifier variant %r into %r", dup.name, keeper.name)
        _take_name(keeper, name)
    return merged, moved


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
            moved += _absorb_well(keeper, dup)
            done.add(dup.id)
            merged += 1

    q_merged, q_moved = _merge_qualifier_variants(done)
    merged += q_merged
    moved += q_moved
    db.session.commit()
    if merged:
        log.info("Merged %s duplicate wells, moved %s records", merged, moved)
    return {"wells_merged": merged, "records_moved": moved,
            "kept_apart": kept_apart}



def seed_workflow() -> dict:
    """Create the process definition, adding only what is missing.

    Stage owners are left unassigned: the accounts for مرکز آبرسانی and the
    engineers belong to the admin, not to a seed file, and a stage without an
    owner is reported in the process builder rather than silently skipped.
    Once the admin has arranged a stage, this never rearranges it again — only
    a stage that does not exist yet is created.
    """
    workflow = WorkflowDefinition.query.filter_by(code=WORKFLOW_CODE).one_or_none()
    created = False
    if workflow is None:
        workflow = WorkflowDefinition(
            code=WORKFLOW_CODE, name="فرایند اصلی کارگاه الکتروپمپ",
            description="از اعلام خرابی تا ثبت نهایی رکورد، در شش مرحله.",
            is_active=True)
        db.session.add(workflow)
        db.session.flush()
        created = True

    sections = {s.code: s for s in FormSection.query.all()}
    fields = {f.field_name: f for f in FormField.query.all()}
    added_stages = added_items = 0

    for spec in WORKFLOW_STAGES:
        stage = WorkflowStage.query.filter_by(
            workflow_id=workflow.id, stage_number=spec["stage_number"]).one_or_none()
        if stage is not None:
            continue                      # the admin owns it from here on
        stage = WorkflowStage(
            workflow_id=workflow.id, stage_number=spec["stage_number"],
            title=spec["title"],
            description=f"{spec['description']}\n\nمتولی پیشنهادی: {spec['hint']}",
            applies_to=spec["applies_to"], is_active=True)
        db.session.add(stage)
        db.session.flush()
        added_stages += 1
        for order, (kind, code, applies, optional) in enumerate(spec["items"]):
            target = sections.get(code) if kind == "section" else fields.get(code)
            if target is None:
                log.warning("Workflow stage %s refers to a missing %s %r",
                            spec["stage_number"], kind, code)
                continue
            db.session.add(WorkflowStageItem(
                stage_id=stage.id,
                section_id=target.id if kind == "section" else None,
                field_id=target.id if kind == "field" else None,
                sort_order=order, applies_to=applies, is_optional=optional))
            added_items += 1
    db.session.commit()
    return {"workflow_created": created, "stages_added": added_stages,
            "stage_items_added": added_items}


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
    "failure": {
        # Renamed when the process split the two branches apart: an install has
        # no fault to report, so this became the کشیدن-only question.
        "label": ("شرح خرابی از نظر بهره‌بردار", "علت خرابی"),
        "visible_when": (None, "operation_kind=کشیدن"),
        "help_text": (None, "فقط در عملیات «کشیدن» پرسیده می‌شود."),
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


# ── undoing the graph release ────────────────────────────────────────────────
# One release turned the six stages into a node-and-arrow map: it added a
# decision, an action and an end node, split «اطلاعات چاه و نصب» onto a node of
# its own, drew arrows between them and — the part that actually broke things —
# left the process definition deactivated, so the process builder loaded
# nothing at all and sat on «در حال بارگذاری» forever.
#
# The engine is back on plain numbered stages. A database that was opened by
# that release therefore carries rows this code cannot run, and this puts them
# back. It runs once, is recorded in app_meta, and touches nothing an admin
# might have meant: records, instances, entries, documents and the owners of
# the six stages are all left exactly as they are.
_GRAPH_ROLLBACK_KEY = "workflow_graph_rollback_v1"

# What that release added, by the key it wrote on each node.
_GRAPH_ONLY_NODES = ("kind", "save", "end")     # decision · action · end
_GRAPH_SPLIT_NODE = "well_install"              # split out of stage 4
_GRAPH_EXTRA_FIELDS = ("well",)                 # added to the step-zero form


def rollback_graph_release() -> dict:
    """Bring a database opened by the graph release back to plain stages.

    ``node_key`` and friends are columns the models no longer have, so they are
    read with SQL rather than through the ORM — which is the whole point: this
    function knows about a shape the rest of the code has forgotten.
    """
    from sqlalchemy import inspect as sa_inspect
    from ..models.meta import AppMeta

    if AppMeta.get(_GRAPH_ROLLBACK_KEY):
        return {}
    columns = {c["name"] for c in
               sa_inspect(db.engine).get_columns("workflow_stages")}
    if "node_key" not in columns:
        AppMeta.set(_GRAPH_ROLLBACK_KEY, "not-needed")
        db.session.commit()
        return {}

    result = {"reactivated": 0, "graph_nodes_removed": 0, "items_restored": 0,
              "extra_items_removed": 0, "arrows_removed": 0}

    # 1 ── the arrows go first, so removing a node cannot orphan one.
    for table in ("workflow_edges", "workflow_node_principals",
                  "workflow_events"):
        try:
            removed = db.session.execute(
                db.text(f"DELETE FROM {table}")).rowcount or 0
        except Exception:                      # table never existed here
            db.session.rollback()
            continue
        if table == "workflow_edges":
            result["arrows_removed"] = removed

    def node_ids(*keys):
        rows = db.session.execute(
            db.text("SELECT id, node_key FROM workflow_stages "
                    "WHERE node_key IS NOT NULL")).fetchall()
        return {key: ident for ident, key in rows if key in keys}

    found = node_ids(_GRAPH_SPLIT_NODE, *_GRAPH_ONLY_NODES)

    # 2 ── «اطلاعات چاه و نصب» belongs on stage 4, where it was.
    split = db.session.get(WorkflowStage, found[_GRAPH_SPLIT_NODE]) \
        if _GRAPH_SPLIT_NODE in found else None
    if split is not None:
        home = WorkflowStage.query.filter_by(workflow_id=split.workflow_id,
                                             stage_number=4).one_or_none()
        for item in list(split.items):
            already = home is not None and any(
                i.section_id == item.section_id and i.field_id == item.field_id
                for i in home.items)
            if home is None or already:
                continue                       # the duplicate the split made;
                                               # the node's own delete takes it
            else:
                # Move it between the collections, not by writing the foreign
                # key: the node is deleted next, and delete-orphan would take
                # anything still sitting in its own list with it.
                split.items.remove(item)
                home.items.append(item)
                result["items_restored"] += 1
        db.session.flush()
        _drop_node(split, result)

    # 3 ── a decision, an action and an end are not stages; the engine has no
    #      way to run them and the کارتابل would list them as work.
    for key in _GRAPH_ONLY_NODES:
        if key in found:
            node = db.session.get(WorkflowStage, found[key])
            if node is not None:
                _drop_node(node, result)

    # 4 ── the step-zero form got a field the start dialog already asks for.
    intake = WorkflowStage.query.filter_by(stage_number=0).one_or_none()
    if intake is not None:
        for item in list(intake.items):
            if item.field is not None and item.field.field_name in _GRAPH_EXTRA_FIELDS:
                db.session.delete(item)
                result["extra_items_removed"] += 1

    # 5 ── and the reason the page hung: nothing was active any more.
    if not WorkflowDefinition.query.filter_by(is_active=True).count():
        oldest = (WorkflowDefinition.query
                  .order_by(WorkflowDefinition.id).first())
        if oldest is not None:
            oldest.is_active = True
            result["reactivated"] = 1

    AppMeta.set(_GRAPH_ROLLBACK_KEY, "done")
    db.session.commit()
    if any(result.values()):
        log.warning("Rolled back the graph release: %s", result)
    return result


def _drop_node(node, result):
    """Remove a node the stage engine cannot run — unless it holds history."""
    from ..models.workflow import WorkflowStageEntry
    used = WorkflowStageEntry.query.filter_by(stage_id=node.id).count()
    if used:
        # Somebody's work is attached to it. Take it off the list instead of
        # deleting it, so the history it carries survives.
        node.is_active = False
    else:
        db.session.delete(node)
    result["graph_nodes_removed"] += 1


# ── where each operation opens ───────────────────────────────────────────────
#
# Until now the code knew: کشیدن begins at stage 1, نصب at stage 3. Now the
# stages say so themselves, so a database written before that has to be told
# once what it already meant. After this the admin owns the answer and nothing
# here touches it again.
_ENTRY_SEED_KEY = "workflow_entry_stages_v1"


def seed_entry_stages() -> dict:
    """Mark the stages each operation used to begin at."""
    from ..models.meta import AppMeta
    from ..models.workflow import (APPLIES_INSTALL, APPLIES_PULL,
                                   WorkflowStage)
    from .workflow import STAGE_FIRST_INSTALL, STAGE_FIRST_PULL

    if AppMeta.get(_ENTRY_SEED_KEY):
        return {}
    marked = 0
    for workflow in WorkflowDefinition.query.all():
        if any(s.can_start for s in workflow.stages):
            continue                      # an admin has already said so
        for number in (STAGE_FIRST_PULL, STAGE_FIRST_INSTALL):
            stage = next((s for s in workflow.stages
                          if s.stage_number == number and s.is_active), None)
            if stage is None or stage.can_start:
                continue
            # A stage bound to the other branch cannot be this one's door.
            if number == STAGE_FIRST_PULL and stage.applies_to == APPLIES_INSTALL:
                continue
            if number == STAGE_FIRST_INSTALL and stage.applies_to == APPLIES_PULL:
                continue
            stage.can_start = True
            marked += 1
    AppMeta.set(_ENTRY_SEED_KEY, "done")
    db.session.commit()
    return {"entry_stages_marked": marked} if marked else {}


# ── which operation each start door opens ────────────────────────────────────
#
# A door used to open whatever its «شامل» admitted, so a stage that is passed
# through by both operations opened both — and the earliest such door swallowed
# the other one. The workshop's rule is کشیدن from مرکز آبرسانی (stage 1) and
# نصب from کارگاه (stage 3), so the two doors the engine used to know about are
# told so once. Any other door keeps following its «شامل», and the admin owns
# all of it from here on.
_START_KIND_KEY = "workflow_start_kinds_v1"


def seed_start_kinds() -> dict:
    from ..models.meta import AppMeta
    from ..models.workflow import (APPLIES_INSTALL, APPLIES_PULL,
                                   WorkflowStage)
    from .workflow import STAGE_FIRST_INSTALL, STAGE_FIRST_PULL

    if AppMeta.get(_START_KIND_KEY):
        return {}
    told = 0
    for stage in WorkflowStage.query.filter(
            WorkflowStage.can_start.is_(True),
            WorkflowStage.start_kind.is_(None)).all():
        if stage.stage_number == STAGE_FIRST_PULL \
                and stage.applies_to != APPLIES_INSTALL:
            stage.start_kind = APPLIES_PULL
            told += 1
        elif stage.stage_number == STAGE_FIRST_INSTALL \
                and stage.applies_to != APPLIES_PULL:
            stage.start_kind = APPLIES_INSTALL
            told += 1
    AppMeta.set(_START_KIND_KEY, "done")
    db.session.commit()
    return {"start_kinds_set": told} if told else {}


# Runs opened before ``entry_stage`` existed have no door recorded. Their path
# was computed as "the earliest door for the operation", so that is written
# down once, before anyone moves a door and the path of a live job shifts
# under it.
_ENTRY_BACKFILL_KEY = "workflow_entry_backfill_v1"


def backfill_entry_stages() -> dict:
    from ..models import WorkflowInstance
    from ..models.meta import AppMeta
    from .workflow import first_stage_number

    if AppMeta.get(_ENTRY_BACKFILL_KEY):
        return {}
    filled = 0
    for inst in WorkflowInstance.query.filter(
            WorkflowInstance.entry_stage.is_(None)).all():
        inst.entry_stage = first_stage_number(inst.operation_kind, inst.workflow)
        filled += 1
    AppMeta.set(_ENTRY_BACKFILL_KEY, "done")
    db.session.commit()
    return {"entry_stages_backfilled": filled} if filled else {}


# The «…قبلی» fields the engine used to fill from a fixed list, written onto the
# fields themselves once so the admin can see, change and extend them.
_PREFILL_KEY = "form_prefill_sources_v1"


def seed_prefill_sources() -> dict:
    from ..models.meta import AppMeta
    from .workflow import PREVIOUS_SOURCES

    if AppMeta.get(_PREFILL_KEY):
        return {}
    told = 0
    for name, source in PREVIOUS_SOURCES.items():
        field = FormField.query.filter_by(field_name=name).first()
        if field is not None and not field.prefill_from:
            field.prefill_from = source
            told += 1
    AppMeta.set(_PREFILL_KEY, "done")
    db.session.commit()
    return {"prefill_sources_set": told} if told else {}


_BACK_KEY = "workflow_default_return_v1"


def seed_default_return() -> dict:
    """Give every stage but the first a way back, once.

    «ارجاع» hands on the *next* stage, so a reviewer who wanted the work back
    with مرکز آبرسانی and referred it to them handed them کارگاه مکانیک's
    forms instead. The way back is a «برگشت» decision; each stage gets one
    whose target the decider picks from the stages already filled. It is an
    ordinary action: the admin can rename it, limit it to some people or
    delete it, and this runs only once so a deletion stays deleted.
    """
    import json
    from ..models import WorkflowDefinition
    from ..models.meta import AppMeta

    if AppMeta.get(_BACK_KEY):
        return {}
    given = 0
    for workflow in WorkflowDefinition.query.all():
        live = sorted((st for st in workflow.stages if st.is_active),
                      key=lambda st: st.stage_number)
        for stage in live[1:]:
            if stage.stage_number == 0 or stage.actions:
                continue
            stage.actions_json = json.dumps([{
                "id": "back", "kind": "return",
                "label": "برگشت به مرحله‌ی قبل برای اصلاح",
                "target_stage": None, "needs_docs": False, "user_ids": []}],
                ensure_ascii=False)
            given += 1
    AppMeta.set(_BACK_KEY, "done")
    db.session.commit()
    return {"default_returns_added": given} if given else {}


_REVIEW_KEY = "workflow_review_decision_v1"


def seed_review_decision() -> dict:
    """«نیاز به کشیدن ندارد» brings up «توقف» by itself, once.

    Wherever the stage that asks «نتیجه بررسی» is, it gets a stop decision
    tied to that answer, and keeps a «برگشت برای اصلاح» beside it, so the
    reviewer who finds the well need not be pulled either closes the run or
    sends it back — «ارسال» to the workshop stops making sense. Ordinary
    actions the admin can change or delete; this runs only once.
    """
    import json
    from ..models import WorkflowDefinition
    from ..models.meta import AppMeta

    if AppMeta.get(_REVIEW_KEY):
        return {}
    field = FormField.query.filter_by(field_name="review_decision").first()
    given = 0
    if field is not None:
        rule = "review_decision=نیاز به کشیدن ندارد"
        for workflow in WorkflowDefinition.query.all():
            for stage in workflow.stages:
                if not stage.is_active or not any(
                        i.field_id == field.id or
                        (i.section_id and i.section_id == field.section_id)
                        for i in stage.items):
                    continue
                acts = stage.actions
                if not any(a["kind"] == "stop" for a in acts):
                    acts.insert(0, {"id": "stop", "kind": "stop",
                                    "label": "نیاز به کشیدن ندارد — توقف فرایند",
                                    "target_stage": None, "needs_docs": False,
                                    "user_ids": [], "when": rule})
                if not any(a["kind"] == "return" for a in acts):
                    acts.append({"id": "back", "kind": "return",
                                 "label": "برگشت به مرحله‌ی قبل برای اصلاح",
                                 "target_stage": None, "needs_docs": False,
                                 "user_ids": [], "when": None})
                stage.actions_json = json.dumps(acts, ensure_ascii=False)
                given += 1
    AppMeta.set(_REVIEW_KEY, "done")
    db.session.commit()
    return {"review_decisions_added": given} if given else {}


from .seed_failure import seed_failure_forms


def seed_all(force: bool = False) -> dict:
    result = {}
    result.update(seed_admin())
    result.update(seed_lookups())
    result.update(seed_wells())
    result.update(deduplicate_wells())
    result.update(normalize_well_names())
    result.update(seed_form())
    result.update(apply_builtin_field_fixes())
    result.update(rollback_graph_release())
    result.update(seed_workflow())
    result.update(seed_entry_stages())
    result.update(seed_failure_forms())
    result.update(seed_start_kinds())
    result.update(backfill_entry_stages())
    result.update(seed_prefill_sources())
    result.update(seed_default_return())
    result.update(seed_review_decision())
    from .seed_pump_selection import seed_pump_selection_forms
    result.update(seed_pump_selection_forms())
    from .catalogue import seed_catalogue
    result.update(seed_catalogue())
    result["changed"] = any(v for k, v in result.items() if isinstance(v, int))
    if result["changed"]:
        log.info("Seed applied: %s", result)
    return result
