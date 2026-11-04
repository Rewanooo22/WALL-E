"""Manifest validation (spec §4.2, §5, §6). Recoverable problems must degrade to
UNKNOWN / not declared with a recorded issue; only unusable manifests are fatal."""

import json

import pytest

from wall_e.models import Classification, ClassificationSource, DeliveryModel, Discipline
from wall_e.project import ManifestError, load_manifest


def issue_fields(m):
    return {i.field for i in m.issues}


def test_minimal_manifest_defaults(make_project):
    m, sha = load_manifest(make_project())
    assert m.project_id == "TEST-1" and len(sha) == 64
    assert m.delivery_model is None and "delivery_model" in issue_fields(m)
    assert m.contracted_scope is None and "contracted_scope" in issue_fields(m)
    # Unlabelled data is confidential by default (FR-SEC-001).
    assert m.default_classification is Classification.CONFIDENTIAL
    assert m.default_classification_source is ClassificationSource.BUILT_IN_DEFAULT
    c = m.conventions
    assert all(getattr(c, f) is None for f in type(c).model_fields)


@pytest.mark.parametrize("value", ["CLIENT_DESIGNED", "DESIGN_AND_BUILD", "HYBRID"])
def test_delivery_model_values(make_project, value):
    m, _ = load_manifest(make_project(delivery_model=value, delivery_model_notes="split described"))
    assert m.delivery_model is DeliveryModel(value)
    assert "delivery_model" not in issue_fields(m)


@pytest.mark.parametrize("value", ["TURNKEY", "client_designed", 3, ""])
def test_invalid_delivery_model_is_unknown_not_fatal(make_project, value):
    m, _ = load_manifest(make_project(delivery_model=value))
    assert m.delivery_model is None
    assert any(i.field == "delivery_model" and "UNKNOWN" in i.effect for i in m.issues)


def test_hybrid_without_notes_flags_split_unknown(make_project):
    m, _ = load_manifest(make_project(delivery_model="HYBRID"))
    assert m.delivery_model is DeliveryModel.HYBRID
    assert any(i.field == "delivery_model_notes" and "UNKNOWN" in i.effect for i in m.issues)


def test_contracted_scope_parsed_and_invalid_disciplines_reported(make_project):
    m, _ = load_manifest(make_project(contracted_scope={
        "disciplines": ["Piping", "Civil", "Piping", "E&I"],
        "basis": [{"file": "contract.pdf", "page": 3}]}))
    assert m.contracted_scope.disciplines == (Discipline.PIPING, Discipline.EI)
    assert any("Civil" in i.problem for i in m.issues)


def test_malformed_contracted_scope_is_not_declared(make_project):
    m, _ = load_manifest(make_project(contracted_scope=["Piping"]))
    assert m.contracted_scope is None
    assert any(i.field == "contracted_scope" for i in m.issues)


def test_invalid_conventions_degrade_to_not_declared(make_project):
    m, _ = load_manifest(make_project(conventions={
        "document_number_pattern": "([unclosed",
        "tag_pattern": r"[A-Z]{1,3}-\d{3}[A-Z]?",
        "discipline_codes": {"PI": "Piping", "XX": "Civil"},
        "revision_sequence": ["A", ""],
        "boq_columns": {"item": "Item"},
        "unexpected": 1}))
    c = m.conventions
    assert c.document_number_pattern is None
    assert c.tag_pattern == r"[A-Z]{1,3}-\d{3}[A-Z]?"
    assert c.discipline_codes == {"PI": Discipline.PIPING}
    assert c.revision_sequence is None and c.boq_columns is None
    fields = issue_fields(m)
    for f in ("conventions.document_number_pattern", "conventions.discipline_codes.XX",
              "conventions.revision_sequence", "conventions.boq_columns", "conventions.unexpected"):
        assert f in fields


def test_unknown_top_level_field_is_reported(make_project):
    m, _ = load_manifest(make_project(delivery_modle="HYBRID"))  # typo
    assert "delivery_modle" in issue_fields(m)


def test_file_entries_reject_escaping_paths_and_bad_classifications(make_project):
    m, _ = load_manifest(make_project(files=[
        {"path": "docs/a.pdf", "classification": "synthetic"},
        {"path": "../other/b.pdf", "classification": "synthetic"},
        {"path": "/etc/passwd", "classification": "synthetic"},
        {"path": "docs/c.pdf", "classification": "secret"},
        {"path": "./docs//a.pdf", "classification": "confidential"}]))
    assert [(e.path, e.classification) for e in m.files] == [("docs/a.pdf", Classification.SYNTHETIC)]
    assert len([i for i in m.issues if i.field.startswith("files[")]) == 4


@pytest.mark.parametrize("content,msg", [
    (b"{not json", "not valid"),
    (b"[]", "JSON object"),
    (json.dumps({"schema_version": "1.0", "project_id": "bad id!"}).encode(), "invalid"),
    (json.dumps({"schema_version": "2.0", "project_id": "OK"}).encode(), "invalid"),
    (json.dumps({"schema_version": "1.0"}).encode(), "invalid"),
])
def test_fatal_manifest_problems(tmp_path, content, msg):
    (tmp_path / "project.json").write_bytes(content)
    with pytest.raises(ManifestError, match=msg):
        load_manifest(tmp_path)


def test_missing_manifest_is_fatal(tmp_path):
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path)
