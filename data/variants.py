"""Deterministic name-variant generator.

Given an original name, produces a labelled list of spelling variants that a
disaster registrar might plausibly write down — each tagged with the rule that
produced it. The (original, variant, rule) triples are the gold set used by the
eval scoreboard (PRD §13).

Rules implemented (PRD §7 stress-case rows):
  1. fold_diacritics    — Carlos Martínez → Carlos Martinez
  2. nickname           — Carlos → Carlitos / Charles  (from data/analysis/nicknames.txt)
  3. initial_form       — Carlos Martinez → C. Martinez  /  Carlos M.
  4. arabic_romanise    — مُحَمَّد → Mohammed / Muhammad / Mohamed / Mohd
  5. vietnamese_fold    — Nguyễn Văn Anh → Nguyen Van Anh
  6. name_order_swap    — Nguyen Van Anh → Van Anh Nguyen
  7. anglicise_spanish  — Ramón → Raymond  (also via nickname rule; bidirectional)

`expand(name)` returns a list[Variant]. The original is NOT included.

Run a demo against the PRD §7 stress cases:
    uv run python -m data.variants
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NICKNAMES_FILE = Path(__file__).resolve().parents[1] / "data" / "analysis" / "nicknames.txt"


@dataclass(frozen=True)
class Variant:
    surface_form: str
    rule: str

    def __repr__(self) -> str:
        return f"Variant({self.surface_form!r}, rule={self.rule})"


# ── Rule 1 + 5: Unicode-aware diacritic stripping ─────────────────────────
# Folds Latin and Vietnamese diacritics ("María" → "Maria", "Nguyễn" → "Nguyen")
# AND Arabic harakat (vocalisation marks: "مُحَمَّد" → "محمد"). Strips all
# combining-mark characters (Unicode category Mn) after NFKD decomposition.

def _strip_combining_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn")


def fold_diacritics(name: str) -> str:
    """Latin / Vietnamese diacritic strip. ASCII-safe output."""
    return _strip_combining_marks(name)


# ── Rule 2 + 7: Nickname / calque equivalence-group lookup ────────────────
# Reads data/analysis/nicknames.txt — the same file feeding the Elastic
# synonym_graph. Single source of truth.

@lru_cache(maxsize=1)
def _load_nickname_groups() -> list[frozenset[str]]:
    groups: list[frozenset[str]] = []
    for raw in NICKNAMES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = frozenset(t.strip().lower() for t in line.split(",") if t.strip())
        if len(tokens) > 1:
            groups.append(tokens)
    return groups


def _nickname_alternates(token: str) -> list[str]:
    token_lower = token.lower()
    out: list[str] = []
    for group in _load_nickname_groups():
        if token_lower in group:
            out.extend(t for t in group if t != token_lower)
    return out


def nickname_variants(name: str) -> list[Variant]:
    """For each token in the name, emit one variant per nickname/calque alternate."""
    tokens = name.split()
    if not tokens:
        return []
    out: list[Variant] = []
    for i, token in enumerate(tokens):
        for alt in _nickname_alternates(token):
            new_tokens = tokens[:i] + [alt.title()] + tokens[i + 1 :]
            out.append(Variant(" ".join(new_tokens), rule="nickname"))
    return out


# ── Rule 3: initial form ──────────────────────────────────────────────────
# Disaster registrars frequently shorten one of the name parts to an initial
# (Carlos Martinez → "Carlos M." or "C. Martinez"). Both directions are
# realistic; we emit both when the name has ≥ 2 tokens.

def initial_form_variants(name: str) -> list[Variant]:
    tokens = name.split()
    if len(tokens) < 2:
        return []
    out: list[Variant] = []
    # last token → initial
    out.append(Variant(f"{' '.join(tokens[:-1])} {tokens[-1][0]}.", rule="initial_form"))
    # first token → initial
    out.append(Variant(f"{tokens[0][0]}. {' '.join(tokens[1:])}", rule="initial_form"))
    return out


# ── Rule 4: Arabic-script romanisation ───────────────────────────────────
# Hand-curated table for the names that appear in PRD §7 stress cases and the
# nickname groups. Going from Arabic script to Roman cannot be done by ICU
# folding alone (which only strips harakat); script-to-script transliteration
# needs a vocabulary. This table is intentionally small — extend it when the
# synthetic data introduces a new Arabic-script name.

_ARABIC_ROMANISATIONS: dict[str, list[str]] = {
    "محمد":   ["Mohammed", "Muhammad", "Mohamed", "Mohammad", "Mohd"],
    "أحمد":   ["Ahmed", "Ahmad"],
    "حسن":    ["Hassan", "Hasan"],
    "حسين":   ["Hussein", "Hussain", "Husain"],
    "علي":    ["Ali", "Aly"],
    "عمر":    ["Omar", "Umar"],
    "يوسف":   ["Yusuf", "Yousef", "Yousuf"],
    "إبراهيم": ["Ibrahim", "Ebrahim"],
    "خالد":   ["Khaled", "Khalid"],
    "فاطمة":  ["Fatima", "Fatma", "Fatimah"],
    "عائشة":  ["Aisha", "Aysha", "Ayesha"],
    "زينب":   ["Zainab", "Zaynab", "Zeinab"],
    "خان":    ["Khan"],
}


def arabic_romanise_variants(name: str) -> list[Variant]:
    """Romanise Arabic-script tokens. Folds harakat first so unvowelled and
    fully-vowelled forms collapse to the same lookup key."""
    tokens = name.split()
    folded = [_strip_combining_marks(t) for t in tokens]
    has_arabic = any(_ARABIC_ROMANISATIONS.get(t) for t in folded)
    if not has_arabic:
        return []
    out: list[Variant] = []
    romanisations_per_token = [_ARABIC_ROMANISATIONS.get(t, [t]) for t in folded]

    def cartesian(idx: int, acc: list[str]) -> None:
        if idx == len(romanisations_per_token):
            surface = " ".join(acc)
            out.append(Variant(surface, rule="arabic_romanise"))
            return
        for r in romanisations_per_token[idx]:
            cartesian(idx + 1, acc + [r])

    cartesian(0, [])
    return out


# ── Rule 6: name-order swap ───────────────────────────────────────────────
# Vietnamese names are written family-first ("Nguyen Van Anh") but seekers
# coming from English-speaking systems often write them given-first
# ("Van Anh Nguyen"). For 2-token names this is just a swap; for 3-token
# names we rotate the family name to the end.

def name_order_swap_variants(name: str) -> list[Variant]:
    tokens = name.split()
    if len(tokens) < 2:
        return []
    if len(tokens) == 2:
        return [Variant(f"{tokens[1]} {tokens[0]}", rule="name_order_swap")]
    # ≥3 tokens: rotate first token to end (family-name-last convention)
    return [Variant(" ".join(tokens[1:] + tokens[:1]), rule="name_order_swap")]


# ── Aggregator ────────────────────────────────────────────────────────────

def expand(name: str) -> list[Variant]:
    """Apply all rules; return de-duplicated variants tagged by rule.

    The original name is NOT in the output. If a variant equals the original
    (case-insensitively, after whitespace-normalisation), it is dropped.
    """
    original_normalised = " ".join(name.split()).lower()
    seen: set[tuple[str, str]] = set()
    out: list[Variant] = []

    candidates: list[Variant] = []

    folded = fold_diacritics(name)
    if folded != name:
        candidates.append(Variant(folded, rule="fold_diacritics"))

    # Apply nickname rule on both the original and the folded form so we
    # catch "Ramón → Raymond" (need to lookup 'ramon' not 'ramón')
    candidates.extend(nickname_variants(folded))
    candidates.extend(initial_form_variants(folded))
    candidates.extend(arabic_romanise_variants(name))

    # Name-order swap applies to the romanised forms AND the folded form
    for swap_base in (folded, *[v.surface_form for v in arabic_romanise_variants(name)]):
        candidates.extend(name_order_swap_variants(swap_base))

    for v in candidates:
        key = (" ".join(v.surface_form.split()).lower(), v.rule)
        if key in seen or key[0] == original_normalised:
            continue
        seen.add(key)
        out.append(v)
    return out


# ── Demo / PRD §7 stress-case check ───────────────────────────────────────

_STRESS_CASES: list[tuple[str, str, str]] = [
    # (seeker_form, expected_variant_to_be_among_outputs, rule)
    ("Carlos Martínez",  "Carlos Martinez",  "fold_diacritics"),
    ("Carlos Martínez",  "Carlitos Martinez", "nickname"),
    ("Carlos Martinez",  "Carlos M.",        "initial_form"),
    ("Mohammed Khan",    "Muhammad Khan",    "nickname"),
    ("محمد خان",         "Mohammed Khan",    "arabic_romanise"),
    ("محمد خان",         "Muhammad Khan",    "arabic_romanise"),
    ("Nguyễn Văn Anh",   "Nguyen Van Anh",   "fold_diacritics"),
    ("Nguyen Van Anh",   "Van Anh Nguyen",   "name_order_swap"),
    ("Ramón Hernández",  "Raymond Hernandez", "nickname"),
    ("Catherine",        "Kate",             "nickname"),
    ("Catherine",        "Cathy",            "nickname"),
]


def _demo() -> int:
    """Verify each PRD stress case produces the expected variant. Returns exit code."""
    failures = 0
    for seeker, expected, expected_rule in _STRESS_CASES:
        variants = expand(seeker)
        match = next(
            (v for v in variants
             if v.surface_form.lower() == expected.lower() and v.rule == expected_rule),
            None,
        )
        if match is None:
            failures += 1
            surface_forms = [f"{v.surface_form}({v.rule})" for v in variants]
            print(f"  ✗ {seeker!r:30}  expected {expected!r} via {expected_rule}")
            print(f"      got: {surface_forms}")
        else:
            print(f"  ✓ {seeker!r:30}  →  {expected!r}  [{expected_rule}]")
    print(f"\n{'✓ all pass' if failures == 0 else f'✗ {failures} failures'}  ({len(_STRESS_CASES) - failures}/{len(_STRESS_CASES)})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_demo())
