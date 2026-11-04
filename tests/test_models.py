"""Evidence and claim model contracts (spec §11): deterministic, project-namespaced
IDs and structural rules that make cross-project citation impossible to construct."""

import pytest
from pydantic import ValidationError

from wall_e.models import (
    Claim, EpistemicClass, Evidence, EvidenceLink, Locator, Tier, make_evidence_id, project_of,
)

SHA = "a" * 64


def ev(project="P1", page=1):
    loc = Locator(page=page)
    return Evidence(id=make_evidence_id(project, SHA, loc), project_id=project, file_path="s.pdf",
                    file_sha256=SHA, locator=loc, raw_text="Design Pressure 10 barg",
                    norm_text="Design Pressure 10 barg", extractor="pdfplumber==0.11.10")


def test_evidence_id_is_deterministic_and_namespaced():
    a, b = ev(), ev()
    assert a.id == b.id and project_of(a.id) == "P1"
    assert ev(page=2).id != a.id
    assert ev(project="P2").id != a.id


def test_evidence_id_must_match_content():
    e = ev()
    with pytest.raises(ValidationError):
        Evidence(**{**e.model_dump(), "id": "P1:0000000000000000"})


@pytest.mark.parametrize("kwargs", [
    {}, {"page": 1, "sheet": "S", "cell": "A1"}, {"sheet": "S"}, {"page": 1, "cell": "A1"},
    {"sheet": "S", "cell": "A1", "bbox": (0, 0, 1, 1)}, {"page": 0},
])
def test_invalid_locators(kwargs):
    with pytest.raises(ValidationError):
        Locator(**kwargs)


def claim(**kw):
    base = dict(id="P1:c1", project_id="P1", section=4, rule_id="MI-03",
                epistemic_class=EpistemicClass.UNKNOWN, statement="s")
    base.update(kw)
    return Claim(**base)


def test_fact_and_conclusion_require_evidence():
    for cls in (EpistemicClass.VERIFIED_FACT, EpistemicClass.SUPPORTED_CONCLUSION):
        with pytest.raises(ValidationError):
            claim(epistemic_class=cls)
    ok = claim(epistemic_class=EpistemicClass.VERIFIED_FACT,
               evidence=(EvidenceLink(evidence_id=ev().id, tier=Tier.T2),))
    assert ok.evidence


def test_cross_project_citation_cannot_be_constructed():
    with pytest.raises(ValidationError, match="another project"):
        claim(evidence=(EvidenceLink(evidence_id=ev(project="P2").id, tier=Tier.T2),))
    with pytest.raises(ValidationError, match="namespace"):
        claim(id="P2:c1")


def test_absence_claim_requires_search_scope():
    with pytest.raises(ValidationError):
        claim(is_absence_claim=True)
    assert claim(is_absence_claim=True, search_scope="all 9 files; title blocks").search_scope
