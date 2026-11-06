"""Manifest validation (spec §4.2, §5, §6). Recoverable problems must degrade to
UNKNOWN / not declared with a recorded issue; only unusable manifests are fatal."""

import hashlib
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


def test_contracted_scope_parsed_with_duplicates_collapsed(make_project):
    m, _ = load_manifest(make_project(contracted_scope={
        "declared_by": "user",
        "disciplines": ["Piping", "E&I", "Piping"],
        "basis": [{"file": "contract.pdf", "page": 3}]}))
    assert m.contracted_scope.disciplines == (Discipline.PIPING, Discipline.EI)
    assert not any(i.field.startswith("contracted_scope") for i in m.issues)


@pytest.mark.parametrize("disciplines,invalid", [
    (["Piping", "Civil", "Piping", "E&I"], ["Civil"]),
    (["Piping", "Mechanicl"], ["Mechanicl"]),
    (["Mechanical", "piping", 5, None], ["piping", 5, None]),
])
def test_partially_valid_discipline_list_is_not_declared(make_project, disciplines, invalid):
    """Rule C: a valid subset is never silently accepted; the issue names every invalid entry."""
    m, _ = load_manifest(make_project(contracted_scope={"declared_by": "user", "disciplines": disciplines}))
    assert m.contracted_scope is None
    [issue] = [i for i in m.issues if i.field == "contracted_scope.disciplines"]
    assert "not declared" in issue.effect
    assert repr(invalid) in issue.problem


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
    # Escaping paths are dropped. The invalid label and the conflicting duplicate both
    # resolve fail-safe to confidential (FR-SEC-001; F5).
    assert [(e.path, e.classification) for e in m.files] == [
        ("docs/a.pdf", Classification.CONFIDENTIAL), ("docs/c.pdf", Classification.CONFIDENTIAL)]
    assert len([i for i in m.issues if i.field.startswith("files[")]) == 4


# ---- F5: fail-safe classification

@pytest.mark.parametrize("bad_label", ["Confidential", "secret", None, "", 3, ["confidential"], {}])
def test_explicit_invalid_label_is_confidential_not_the_less_restrictive_default(make_project, bad_label):
    m, _ = load_manifest(make_project(default_classification="synthetic",
                                      files=[{"path": "a.pdf", "classification": bad_label}]))
    [entry] = m.files
    assert entry.classification is Classification.CONFIDENTIAL
    assert entry.classification_source is ClassificationSource.FAIL_SAFE_INVALID_LABEL
    assert sum("invalid classification" in i.problem for i in m.issues) == 1


@pytest.mark.parametrize("default,expected_cls,expected_src", [
    ("synthetic", Classification.SYNTHETIC, ClassificationSource.MANIFEST_DEFAULT),
    (None, Classification.CONFIDENTIAL, ClassificationSource.BUILT_IN_DEFAULT),
])
def test_missing_classification_key_uses_default(make_project, default, expected_cls, expected_src):
    """Rule B / spec §4.2: an entry without a 'classification' key is unlabelled -> default applies."""
    fields = {"files": [{"path": "b.pdf"}]}
    if default is not None:
        fields["default_classification"] = default
    m, _ = load_manifest(make_project(**fields))
    [entry] = m.files
    assert (entry.classification, entry.classification_source) == (expected_cls, expected_src)
    assert not any("classification" in i.problem for i in m.issues)


def test_unlabelled_entry_still_counts_for_listed_file_not_found(make_project):
    from wall_e.project import scan_project
    scan = scan_project(make_project(files=[{"path": "ghost.pdf"}]))
    assert any(i.field == "files:ghost.pdf" and "not found" in i.problem for i in scan.manifest.issues)


@pytest.mark.parametrize("labels,expected", [
    (["synthetic", "confidential"], Classification.CONFIDENTIAL),
    (["confidential", "synthetic"], Classification.CONFIDENTIAL),
    (["synthetic", "public-licensed"], Classification.PUBLIC_LICENSED),
    (["public-licensed", "synthetic", "bogus"], Classification.CONFIDENTIAL),
])
def test_duplicate_declarations_take_most_restrictive(make_project, labels, expected):
    m, _ = load_manifest(make_project(files=[{"path": "a.pdf", "classification": c} for c in labels]))
    assert [(e.path, e.classification) for e in m.files] == [("a.pdf", expected)]
    assert any("conflicting duplicate" in i.problem for i in m.issues)


@pytest.mark.parametrize("default,decls,expected_src", [
    ("synthetic", [{"path": "a.pdf"}, {"path": "./a.pdf", "classification": "synthetic"}],
     ClassificationSource.MANIFEST_FILE_ENTRY),
    (None, [{"path": "a.pdf", "classification": "bogus"}, {"path": "a.pdf", "classification": "confidential"}],
     ClassificationSource.MANIFEST_FILE_ENTRY),
    (None, [{"path": "a.pdf", "classification": "bogus"}, {"path": "a.pdf"}],
     ClassificationSource.FAIL_SAFE_INVALID_LABEL),
])
@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_same_classification_source_does_not_depend_on_manifest_order(
        make_project, default, decls, expected_src, reverse):
    """F-C: equal-classification duplicates for one path keep a source chosen by fixed rank."""
    fields = {"files": decls[::-1] if reverse else decls}
    if default is not None:
        fields["default_classification"] = default
    m, _ = load_manifest(make_project(**fields))
    [entry] = m.files
    assert entry.classification_source is expected_src
    assert any("duplicate entry" in i.problem for i in m.issues)


# ---- F6: UTF-8 BOM

def test_manifest_with_utf8_bom_loads(tmp_path):
    body = json.dumps({"schema_version": "1.0", "project_id": "BOM-1"}).encode("utf-8")
    (tmp_path / "project.json").write_bytes(b"\xef\xbb\xbf" + body)
    m, sha = load_manifest(tmp_path)
    assert m.project_id == "BOM-1"
    assert sha == hashlib.sha256(b"\xef\xbb\xbf" + body).hexdigest()  # hash covers the exact bytes


# ---- F7: contracted scope semantics

@pytest.mark.parametrize("scope", [{}, {"disciplines": None}, {"disciplines": "Piping"},
                                   {"disciplines": ["Civil", "piping"]}])
def test_contracted_scope_not_declared_cases(make_project, scope):
    # declared_by is valid here, so each case exercises the disciplines rule itself.
    m, _ = load_manifest(make_project(contracted_scope={"declared_by": "user", **scope}))
    assert m.contracted_scope is None
    assert any(i.field == "contracted_scope.disciplines" and "not declared" in i.effect for i in m.issues)


def test_explicit_empty_disciplines_is_declared_with_zero(make_project):
    m, _ = load_manifest(make_project(contracted_scope={"declared_by": "user", "disciplines": []}))
    assert m.contracted_scope is not None and m.contracted_scope.disciplines == ()
    assert not any(i.field.startswith("contracted_scope") for i in m.issues)


@pytest.mark.parametrize("declared_by", ["contract", "User", "", None, 5, ["user"]])
def test_declared_by_must_be_exactly_user(make_project, declared_by):
    m, _ = load_manifest(make_project(contracted_scope={"declared_by": declared_by, "disciplines": ["Piping"]}))
    assert m.contracted_scope is None
    assert any(i.field == "contracted_scope.declared_by" for i in m.issues)


def test_declared_by_absent_is_not_declared(make_project):
    m, _ = load_manifest(make_project(contracted_scope={"disciplines": ["Piping"]}))
    assert m.contracted_scope is None
    assert any(i.field == "contracted_scope.declared_by" and "missing" in i.problem
               and "not declared" in i.effect for i in m.issues)


def test_explicit_user_with_valid_disciplines_is_declared(make_project):
    m, _ = load_manifest(make_project(contracted_scope={"declared_by": "user", "disciplines": ["Piping"]}))
    assert m.contracted_scope.declared_by == "user"
    assert m.contracted_scope.disciplines == (Discipline.PIPING,)


# ---- project_id must match the whole pattern (fullmatch; no trailing newline)

_BAD_PROJECT_IDS = ["SYN-001\n", "SYN-001\r\n", "\nSYN-001", "SYN-001 ", " SYN-001", "SYN-001\t",
                    "SYN-001\x00", "SYN-001/x", "SYN-001:x", "SYN-001.", "A" * 65, ""]


@pytest.mark.parametrize("bad", _BAD_PROJECT_IDS)
def test_project_id_with_invalid_suffix_or_prefix_is_fatal(tmp_path, bad):
    (tmp_path / "project.json").write_text(json.dumps({"schema_version": "1.0", "project_id": bad}),
                                           encoding="utf-8")
    with pytest.raises(ManifestError, match="project_id must match"):
        load_manifest(tmp_path)


@pytest.mark.parametrize("bad", _BAD_PROJECT_IDS)
def test_evidence_id_rejects_invalid_project_id(bad):
    from wall_e.models import Locator, make_evidence_id
    with pytest.raises(ValueError, match="invalid project_id"):
        make_evidence_id(bad, "a" * 64, Locator(page=1))


def test_project_id_boundary_values_accepted(make_project):
    for pid in ("A", "a_B-9", "X" * 64):
        root = make_project(name=f"p{len(pid)}{pid[:3]}", project_id=pid)
        assert load_manifest(root)[0].project_id == pid


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


# ---- F4: strict identity types (no coercion)

@pytest.mark.parametrize("field,value", [
    ("project_id", None), ("project_id", True), ("project_id", 123), ("project_id", ["A"]),
    ("project_id", {"id": "A"}), ("project_id", 1.5),
    ("schema_version", 1.0), ("schema_version", None), ("schema_version", True), ("schema_version", ["1.0"]),
])
def test_identity_fields_must_be_strings(tmp_path, field, value):
    data = {"schema_version": "1.0", "project_id": "OK", field: value}
    (tmp_path / "project.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ManifestError, match=f"{field} must be a string"):
        load_manifest(tmp_path)


def test_missing_manifest_is_fatal(tmp_path):
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path)


# ---- L-4: an unreadable project.json is a ManifestError with the error class only

def test_unreadable_manifest_is_manifest_error_without_path(make_project, monkeypatch):
    import pathlib
    root = make_project()

    def failing_read(self):
        raise PermissionError(13, "Permission denied", str(self))
    monkeypatch.setattr(pathlib.Path, "read_bytes", failing_read)
    with pytest.raises(ManifestError, match=r"cannot be read .*PermissionError") as info:
        load_manifest(root)
    assert str(root) not in str(info.value)


def test_windows_acl_denied_manifest_is_manifest_error(make_project):
    from conftest import windows_access_denied
    from wall_e.project import scan_project
    root = make_project()
    with windows_access_denied(root / "project.json"):
        with pytest.raises(ManifestError, match="PermissionError") as info:
            scan_project(root)
    assert str(root) not in str(info.value)


@pytest.mark.parametrize("value", [{}, 1, 2.0, False])
def test_schema_version_other_non_string_types(tmp_path, value):
    (tmp_path / "project.json").write_text(json.dumps({"schema_version": value, "project_id": "OK"}),
                                           encoding="utf-8")
    with pytest.raises(ManifestError, match="schema_version must be a string"):
        load_manifest(tmp_path)
