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
from ..models.workflow import (NODE_PHASE, TEMPLATE_PUBLISHED, WorkflowEdge,
                               WorkflowNodePrincipal)
from .seed_data import (FORM_SECTIONS, LOOKUP_CATEGORIES, WORKFLOW_CODE,
                        WORKFLOW_EDGES, WORKFLOW_NODES)
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
    """Draw the starting process map, adding only what is missing.

    Three things this deliberately does *not* do. It does not assign anybody:
    the accounts for the water centre and the engineers belong to the admin,
    and a node without an owner is reported in the designer rather than
    silently skipped. It does not touch a map the admin has already drawn —
    once arrows exist, the process is theirs. And it does not create a second
    copy of a process an older release already seeded: the six numbered stages
    are adopted as nodes, keeping their owners, their entries and their
    documents.
    """
    _repair_template_columns()
    workflow = (WorkflowDefinition.query.filter_by(code=WORKFLOW_CODE)
                .order_by(WorkflowDefinition.version.desc()).first())
    created = False
    if workflow is None:
        workflow = WorkflowDefinition(
            code=WORKFLOW_CODE, version=1,
            name="فرایند اصلی کارگاه الکتروپمپ",
            description="از اعلام خرابی تا ثبت نهایی رکورد. هر گره، هر پیکان "
                        "و هر شرط در «نقشه فرایند» قابل تغییر است.",
            status=TEMPLATE_PUBLISHED, is_active=True)
        db.session.add(workflow)
        db.session.flush()
        created = True

    drawn = WorkflowEdge.query.filter_by(workflow_id=workflow.id).count()
    if drawn:
        # The map is the admin's from here on; the one thing still worth
        # checking is that the start node asks for everything the later phases
        # expect to have been settled there.
        return {"workflow_created": created, "nodes_added": 0, "edges_added": 0,
                **_ensure_start_items(workflow)}

    sections = {s.code: s for s in FormSection.query.all()}
    fields = {f.field_name: f for f in FormField.query.all()}
    existing = {s.node_key: s for s in workflow.stages if s.node_key}
    by_number = {s.stage_number: s for s in workflow.stages}
    nodes, added_nodes, added_items = {}, 0, 0

    for spec in WORKFLOW_NODES:
        node = existing.get(spec["key"])
        if node is None and spec.get("legacy_stage") is not None:
            node = by_number.get(spec["legacy_stage"])     # adopt the old row
        if node is None:
            node = WorkflowStage(workflow_id=workflow.id,
                                 stage_number=spec["stage_number"],
                                 title=spec["title"])
            db.session.add(node)
            added_nodes += 1
        node.node_key = spec["key"]
        node.node_type = spec["type"]
        node.icon = spec.get("icon")
        node.pos_x, node.pos_y = spec["x"], spec["y"]
        node.width, node.height = spec["width"], spec["height"]
        node.is_active = True
        if spec.get("config"):
            node.set_config(spec["config"])
        if not node.description:
            hint = spec.get("hint")
            node.description = (spec["description"]
                                + (f"\n\nمتولی پیشنهادی: {hint}" if hint else ""))
        db.session.flush()
        nodes[spec["key"]] = node

        # Only lay out a node's form when it has none: what the admin dropped
        # on a stage in the old builder stays exactly where they put it.
        if node.items:
            continue
        for order, (kind, code, optional, read_only) in enumerate(spec["items"]):
            target = sections.get(code) if kind == "section" else fields.get(code)
            if target is None:
                log.warning("Process node %s refers to a missing %s %r",
                            spec["key"], kind, code)
                continue
            db.session.add(WorkflowStageItem(
                stage_id=node.id,
                section_id=target.id if kind == "section" else None,
                field_id=target.id if kind == "field" else None,
                sort_order=order, is_optional=optional,
                is_read_only=read_only))
            added_items += 1

    # A node an older release wrote that the map no longer names keeps its
    # rows — an instance may still refer to it — but leaves the canvas.
    for node in workflow.stages:
        if node.node_key not in nodes:
            node.is_active = False

    added_edges = 0
    for source, target, label, condition, priority in WORKFLOW_EDGES:
        if source not in nodes or target not in nodes:
            continue
        edge = WorkflowEdge(workflow_id=workflow.id,
                            source_id=nodes[source].id,
                            target_id=nodes[target].id,
                            label=label, priority=priority)
        edge.set_condition(condition)
        db.session.add(edge)
        added_edges += 1

    # The old release put «اطلاعات چاه و نصب» on the same stage as the action
    # question; the map has them as two nodes, so the section moves across.
    _split_legacy_item(nodes, "action", "well_install", "well_install")

    db.session.commit()
    log.info("Process map seeded: %s nodes, %s arrows", added_nodes, added_edges)
    return {"workflow_created": created, "nodes_added": added_nodes,
            "stage_items_added": added_items, "edges_added": added_edges}


# Items the workshop's start node must carry, because every later phase shows
# them locked instead of asking again. Applied once per database: after that
# the admin may take them off and they stay off.
_START_ITEMS_KEY = "workflow_start_items_v1"


def _ensure_start_items(workflow) -> dict:
    """Put on the start node what the rest of the map assumes it settled.

    The well is chosen once and never searched for again, which only works if
    the node that opens the process actually asks for it. An installation
    upgraded from the six-stage release has a start node that asks only for the
    operation, so the missing item is added — once, and recorded, so an admin
    who then removes it is not overruled at the next restart.
    """
    from ..models.meta import AppMeta
    if AppMeta.get(_START_ITEMS_KEY):
        return {}
    spec = next((n for n in WORKFLOW_NODES if n["type"] == "start"), None)
    start = next((n for n in workflow.nodes if n.node_type == "start"), None)
    if spec is None or start is None:
        return {}
    have = {(i.kind, i.section.code if i.section
             else i.field.field_name if i.field else None) for i in start.items}
    added = 0
    for order, (kind, code, optional, read_only) in enumerate(spec["items"]):
        if (kind, code) in have:
            continue
        target = (FormSection.query.filter_by(code=code).first() if kind == "section"
                  else FormField.query.filter_by(field_name=code).first())
        if target is None:
            continue
        db.session.add(WorkflowStageItem(
            stage_id=start.id,
            section_id=target.id if kind == "section" else None,
            field_id=target.id if kind == "field" else None,
            sort_order=len(start.items) + order,
            is_optional=optional, is_read_only=read_only))
        added += 1
    AppMeta.set(_START_ITEMS_KEY, "done")
    db.session.commit()
    if added:
        log.info("Added %s missing item(s) to the start node", added)
    return {"start_items_added": added}


def _repair_template_columns():
    """Fill in the version and status of a template written before they existed.

    A database built by ``create_all`` rather than by the migrations gets the
    new columns empty rather than defaulted, and a template with no version
    cannot be ordered or copied. One pass, then never again.
    """
    fixed = 0
    for workflow in WorkflowDefinition.query.all():
        if workflow.version is None:
            workflow.version = 1
            fixed += 1
        if not workflow.status:
            workflow.status = TEMPLATE_PUBLISHED
            fixed += 1
    for node in WorkflowStage.query.filter(
            db.or_(WorkflowStage.node_type.is_(None),
                   WorkflowStage.node_key.is_(None))).all():
        node.node_type = node.node_type or NODE_PHASE
        node.node_key = node.node_key or f"s{node.stage_number}"
        fixed += 1
    if fixed:
        db.session.commit()
        log.info("Repaired %s process-template columns", fixed)


def _split_legacy_item(nodes, from_key, to_key, section_code):
    """Move one section from one node to another, once."""
    source, target = nodes.get(from_key), nodes.get(to_key)
    if source is None or target is None:
        return
    section = FormSection.query.filter_by(code=section_code).one_or_none()
    if section is None:
        return
    moved = [i for i in source.items if i.section_id == section.id]
    if not moved:
        return
    if any(i.section_id == section.id for i in target.items):
        for item in moved:
            db.session.delete(item)
        return
    for item in moved:
        item.stage_id = target.id
        item.sort_order = 0


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


def seed_all(force: bool = False) -> dict:
    result = {}
    result.update(seed_admin())
    result.update(seed_lookups())
    result.update(seed_wells())
    result.update(deduplicate_wells())
    result.update(normalize_well_names())
    result.update(seed_form())
    result.update(apply_builtin_field_fixes())
    result.update(seed_workflow())
    result["changed"] = any(v for k, v in result.items() if isinstance(v, int))
    if result["changed"]:
        log.info("Seed applied: %s", result)
    return result
