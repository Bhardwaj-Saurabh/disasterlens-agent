"""name_variants FunctionTool — exposes data/variants.py to the agent.

The Coordinator calls this BEFORE searching for any name with diacritics,
non-Roman script, or potential nickname/calque expansions. The output is fed
back into the Elastic search as additional query terms.
"""
from __future__ import annotations

from data.variants import expand


def name_variants(name: str) -> dict:
    """Return all known variants of a name plus the rule that produced each.

    Use this BEFORE searching for any non-Roman-script name (Arabic, Vietnamese
    with diacritics) and any name where a nickname or diacritic-stripped form
    might appear in registrar entries (Carlos↔Carlitos, María↔Maria,
    Mohammed↔Muhammad↔محمد, Nguyễn↔Nguyen).

    Args:
        name: The name as the seeker wrote it, preserving script and diacritics.

    Returns:
        A dict with:
          - `original`: the input string
          - `variants`: a list of {surface_form, rule} objects
          - `all_surface_forms`: a flat de-duplicated list of strings suitable
            for use as Elasticsearch query terms (includes the original)
    """
    expanded = expand(name)
    surface_forms = [name] + [v.surface_form for v in expanded]
    return {
        "original": name,
        "variants": [
            {"surface_form": v.surface_form, "rule": v.rule}
            for v in expanded
        ],
        "all_surface_forms": list(dict.fromkeys(surface_forms)),  # de-dup, preserve order
    }
