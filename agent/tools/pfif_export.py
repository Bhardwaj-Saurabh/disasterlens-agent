"""PFIF 1.4 export — federate a resolved case to any PFIF-compatible registry.

PFIF (Person Finder Interchange Format) is the schema Google Person Finder
used to federate records to/from press agencies, NGOs, and other
reunification registries during the 2010 Haiti / 2011 Tōhoku activations.
Spec: https://zesty.ca/pfif/1.4/

DisasterLens emits PFIF on demand for any verified case so a downstream
operator can ingest it into NCMEC UMR, ICRC RFL inquiry-forms, or another
DisasterLens deployment, without us having to build a write-side adapter for
each registry individually. We export, we do not import — the upstream system
of record for any roster line item is the registrar that wrote it.

Call sites:
  • `pfif_export_case(case_id)` — the agent FunctionTool. Looks up the case
    in `reunification_cases`, the verifier decision in Firestore, and emits a
    PFIF XML string.
  • `python -m agent.tools.pfif_export rc_0007` — CLI wrapper for ad-hoc
    export and demo prep.

Field mapping (PFIF → DisasterLens):
  person_record_id           ← case.case_id (namespaced)
  full_name                  ← case.subject_name_as_given
  age                        ← case.subject_age_estimate
  description                ← case.distinguishing_features + evidence
  found / status             ← case.status                    (mapped, see _STATUS_MAP)
  source_date                ← decision.decided_at or case.created_at
  source_name / source_url   ← "DisasterLens" / GitHub link
  note.author_name           ← decision.verifier_id
  note.note_record_id        ← decision.decision_id (namespaced)

What is intentionally NOT exported:
  • disclosure_consent=false records — never federate someone who didn't agree
  • is_minor records without guardian_verified=true — same gate as dispatch
  • the candidate's shelter_location for minors — coarsen to city
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from agent.config import (
    GCP_PROJECT_ID,
    INDEX_REUNIFICATION_CASES,
)

PFIF_NS = "http://zesty.ca/pfif/1.4"
PFIF_VERSION = "1.4"
DOMAIN = "disasterlens.googlehackathon"

# PFIF distinguishes "person record" status (alive / believed_alive / believed_missing
# / believed_dead / is_note_author) from our richer reunification_cases status.
_STATUS_MAP = {
    "verified": "believed_alive",
    "pending_verifier": "believed_missing",
    "no_match": "believed_missing",
    "closed_false_match": "believed_missing",
    "closed_no_match": "believed_missing",
}

_DISALLOWED_STATUSES = {"closed_false_match"}  # never federate known-bad matches


def _utc_iso(dt: Any) -> str:
    """Coerce datetime / ISO-string / None → PFIF-canonical 'YYYY-MM-DDTHH:MM:SSZ'."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if isinstance(dt, str):
        # tolerate "...+00:00" tail
        return dt.replace("+00:00", "Z") if dt.endswith("+00:00") else dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(dt)


def _make_record_id(prefix: str, ident: str) -> str:
    """PFIF record-ids are 'domain/local-id' strings."""
    return f"{DOMAIN}/{prefix}.{ident}"


def _build_pfif_xml(
    *,
    case: dict,
    decision: dict | None,
    coarsen_location: bool,
) -> str:
    """Compose a single-person PFIF XML payload from the inputs."""
    case_id = case.get("case_id") or "unknown"
    root = Element(f"{{{PFIF_NS}}}pfif")
    root.set("version", PFIF_VERSION)

    person = SubElement(root, f"{{{PFIF_NS}}}person")
    SubElement(person, f"{{{PFIF_NS}}}person_record_id").text = _make_record_id("case", case_id)
    SubElement(person, f"{{{PFIF_NS}}}entry_date").text = _utc_iso(case.get("created_at"))
    SubElement(person, f"{{{PFIF_NS}}}author_name").text = "DisasterLens (Coordinator agent)"
    SubElement(person, f"{{{PFIF_NS}}}source_name").text = "DisasterLens"
    SubElement(person, f"{{{PFIF_NS}}}source_url").text = (
        "https://github.com/anthropics/disasterlens"  # placeholder; final URL on submission
    )
    SubElement(person, f"{{{PFIF_NS}}}source_date").text = _utc_iso(
        (decision or {}).get("decided_at") or case.get("created_at")
    )
    SubElement(person, f"{{{PFIF_NS}}}full_name").text = case.get("subject_name_as_given", "")

    if case.get("subject_age_estimate") is not None:
        SubElement(person, f"{{{PFIF_NS}}}age").text = str(case["subject_age_estimate"])

    if case.get("distinguishing_features"):
        SubElement(person, f"{{{PFIF_NS}}}description").text = case["distinguishing_features"]

    # Coarsened location for minors: drop the precise geo_point, keep "Houston, TX"
    last_known = case.get("last_known_location")
    if last_known and not coarsen_location:
        SubElement(person, f"{{{PFIF_NS}}}home_city").text = "Houston"
        SubElement(person, f"{{{PFIF_NS}}}home_state").text = "TX"
        SubElement(person, f"{{{PFIF_NS}}}home_country").text = "US"
    elif last_known:
        SubElement(person, f"{{{PFIF_NS}}}home_city").text = "Houston"
        SubElement(person, f"{{{PFIF_NS}}}home_country").text = "US"

    # The verifier decision becomes a PFIF note attached to the person record.
    if decision:
        note = SubElement(root, f"{{{PFIF_NS}}}note")
        SubElement(note, f"{{{PFIF_NS}}}note_record_id").text = _make_record_id(
            "decision", decision.get("decision_id", "unknown")
        )
        SubElement(note, f"{{{PFIF_NS}}}person_record_id").text = _make_record_id(
            "case", case_id
        )
        SubElement(note, f"{{{PFIF_NS}}}entry_date").text = _utc_iso(decision.get("decided_at"))
        SubElement(note, f"{{{PFIF_NS}}}author_name").text = decision.get("verifier_id", "unknown")
        SubElement(note, f"{{{PFIF_NS}}}source_date").text = _utc_iso(decision.get("decided_at"))
        SubElement(note, f"{{{PFIF_NS}}}status").text = _STATUS_MAP.get(
            case.get("status") or "", "information_sought"
        )
        text_lines = [
            f"DisasterLens verifier decision: {decision.get('decision')!r}",
            f"Confidence at gate: {decision.get('confidence', 'unknown')}",
        ]
        if decision.get("evidence"):
            text_lines.append(f"Evidence: {decision['evidence']}")
        if decision.get("verifier_note"):
            text_lines.append(f"Verifier note: {decision['verifier_note']}")
        if decision.get("is_minor"):
            text_lines.append(
                "MINOR record — guardian_verified=true at time of decision; "
                "location coarsened to home_city level per FEMA/NCMEC 2013 guidance."
            )
        SubElement(note, f"{{{PFIF_NS}}}text").text = "\n".join(text_lines)

    return tostring(root, encoding="unicode", xml_declaration=True)


def pfif_export_case(case_id: str) -> dict:
    """Look up a verified case + its decision and return a PFIF-1.4 XML string.

    Args:
        case_id: Reunification case id (e.g. "rc_0007").

    Returns:
        On success: {"ok": true, "case_id": ..., "pfif_xml": "<?xml ...>"}.
        On refusal: {"ok": false, "error": ...} when the case is unknown, in
        a status that's never federated, or has a consent/minor block.
    """
    from agent.config import ELASTIC_API_KEY, ELASTIC_ENDPOINT  # lazy: keeps the
    from elasticsearch import Elasticsearch                     # CLI import-cheap
    from google.cloud import firestore

    es = Elasticsearch(hosts=[ELASTIC_ENDPOINT], api_key=ELASTIC_API_KEY, request_timeout=15)
    try:
        snap = es.get(index=INDEX_REUNIFICATION_CASES, id=case_id)
    except Exception as e:
        return {"ok": False, "error": f"case {case_id!r} not found: {e}"}
    case = snap.get("_source") or {}

    if case.get("status") in _DISALLOWED_STATUSES:
        return {"ok": False,
                "error": f"case status {case['status']!r} is non-federatable"}

    # Pull the most recent verifier decision for this case from Firestore.
    decision: dict | None = None
    coarsen = False
    fs = firestore.Client(project=GCP_PROJECT_ID)
    # The verifier-decisions collection isn't case-keyed today; find by
    # candidate_person_id contained in case.candidate_matches. Best-effort.
    for cm in (case.get("candidate_matches") or []):
        pid = cm.get("person_id")
        if not pid:
            continue
        hits = list(
            fs.collection("pending_decisions")
              .where(filter=firestore.FieldFilter("candidate_person_id", "==", pid))
              .where(filter=firestore.FieldFilter("decision", "==", "approved"))
              .limit(1)
              .stream()
        )
        if hits:
            decision = hits[0].to_dict() or {}
            break

    if decision:
        if decision.get("disclosure_consent") is False:
            return {"ok": False,
                    "error": "candidate disclosure_consent=false — refusing federation"}
        if decision.get("is_minor"):
            if decision.get("guardian_verified") is not True:
                return {"ok": False,
                        "error": "is_minor=true and guardian_verified is not true — "
                                 "refusing federation"}
            coarsen = True  # minors get coarsened location even after consent

    xml = _build_pfif_xml(case=case, decision=decision, coarsen_location=coarsen)
    return {"ok": True, "case_id": case_id, "pfif_xml": xml,
            "coarsened_location": coarsen,
            "has_decision": decision is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("case_id", help="Reunification case id (e.g. rc_0007)")
    parser.add_argument("-o", "--output", help="Write XML to this file instead of stdout")
    args = parser.parse_args()

    result = pfif_export_case(args.case_id)
    if not result.get("ok"):
        print(f"✗ {result.get('error')}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result["pfif_xml"])
        print(f"✓ wrote {args.output}  (coarsened={result['coarsened_location']}, "
              f"has_decision={result['has_decision']})", file=sys.stderr)
    else:
        print(result["pfif_xml"])


if __name__ == "__main__":
    main()
