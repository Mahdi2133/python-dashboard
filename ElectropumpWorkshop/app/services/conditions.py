"""«نمایش فقط وقتی…» rules, which may now be several on one form or field.

A form or a field can be opened by more than one question: «پارامترهای
هوادهی» by «علت خرابی = هوادهی» and also by «نتیجه تست = دبی کم». Each
source field gets its own rule, and the thing is shown when *any* of them is
met. Stored in the one ``visible_when`` column, rules separated by «;»:

    failure=هوادهی|کاهش آبدهی;test_result=دبی کم

A rule with no values («failure=») is a link to nothing yet and opens for
nothing, as before.
"""
SEP = ";"


def parse_rules(raw) -> list:
    """``[(source_field, [values...]), ...]`` in the order they were written."""
    out = []
    for part in str(raw or "").split(SEP):
        part = part.strip()
        if "=" not in part:
            continue
        on, _, values = part.partition("=")
        on = on.strip()
        if on:
            out.append((on, [v.strip() for v in values.split("|") if v.strip()]))
    return out


def join_rules(rules) -> str | None:
    text = SEP.join(f"{on}=" + "|".join(values) for on, values in rules)
    return text or None


def rule_for(raw, source: str):
    """The values ``source`` opens this with, or None when it is not linked."""
    for on, values in parse_rules(raw):
        if on == source:
            return values
    return None


def with_rule(raw, source: str, values) -> str | None:
    """``raw`` with the rule for ``source`` replaced — or removed when None.

    The rules on other source fields are kept: linking a form to a second
    question no longer takes it away from the first.
    """
    rules = [(on, vals) for on, vals in parse_rules(raw) if on != source]
    if values is not None:
        rules.append((source, list(dict.fromkeys(values))))
    return join_rules(rules)
