"""Core data models for WALL-E Phase 1.

Spec references: docs/spec/phase-1-document-intelligence.md §4.2 (manifest),
§7.7 (coverage statuses), §11 (evidence and claims).

These models are the contract between pipeline stages. They contain structural
validation only. Semantic rules (class/tier rules, value tracing, resolver
checks) belong to the verifier (M6).
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- enums


class Classification(str, Enum):
    SYNTHETIC = "synthetic"
    PUBLIC_LICENSED = "public-licensed"
    CONFIDENTIAL = "confidential"


class DeliveryModel(str, Enum):
    CLIENT_DESIGNED = "CLIENT_DESIGNED"
    DESIGN_AND_BUILD = "DESIGN_AND_BUILD"
    HYBRID = "HYBRID"


class Discipline(str, Enum):
    MECHANICAL = "Mechanical"
    PIPING = "Piping"
    FABRICATION = "Fabrication"
    INSTALLATION = "Installation"
    EI = "E&I"


class FileType(str, Enum):
    PDF = "pdf"
    XLSX = "xlsx"
    OTHER = "other"


class FileStatus(str, Enum):
    """Coverage status per input file (spec §7.7).

    DISCOVERED is a pre-extraction state set by the loader (M1). It must not
    appear in a final report; the report verifier (M6) enforces this.
    """

    DISCOVERED = "DISCOVERED"
    PROCESSED = "PROCESSED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    ENCRYPTED = "ENCRYPTED"
    UNREADABLE = "UNREADABLE"
    DUPLICATE = "DUPLICATE"
    PARSE_FAILED = "PARSE_FAILED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    REJECTED_PATH = "REJECTED_PATH"


class ClassificationSource(str, Enum):
    MANIFEST_FILE_ENTRY = "manifest_file_entry"
    MANIFEST_DEFAULT = "manifest_default"
    BUILT_IN_DEFAULT = "built_in_default"  # confidential (FR-SEC-001)


class EpistemicClass(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"  # displayed as "Fact as stated in source"
    SUPPORTED_CONCLUSION = "SUPPORTED_CONCLUSION"
    HYPOTHESIS = "HYPOTHESIS"  # reserved; no Phase 1 rule emits it
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"


DISPLAY_LABELS: dict[EpistemicClass, str] = {
    EpistemicClass.VERIFIED_FACT: "Fact as stated in source",
    EpistemicClass.SUPPORTED_CONCLUSION: "Supported conclusion",
    EpistemicClass.HYPOTHESIS: "Hypothesis",
    EpistemicClass.ASSUMPTION: "Assumption",
    EpistemicClass.UNKNOWN: "Unknown",
}


class Tier(str, Enum):
    T1 = "T1"  # structured register fields
    T2 = "T2"  # current controlled document
    T3 = "T3"  # superseded / uncontrolled / user-declared
    T4 = "T4"  # unverified machine-derived (unused in Phase 1)


class QualityFlag(str, Enum):
    TEXT_OK = "TEXT_OK"
    TEXT_UNRELIABLE = "TEXT_UNRELIABLE"
    HIDDEN_IN_SOURCE = "HIDDEN_IN_SOURCE"
    FORMULA_DERIVED = "FORMULA_DERIVED"
    MERGED_ANCHOR = "MERGED_ANCHOR"


class ResolutionStatus(str, Enum):
    """Spec §11.3 statuses for evidence or claims that cannot be used normally."""

    UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
    UNREADABLE = "UNREADABLE"
    PARSE_FAILED = "PARSE_FAILED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    RESOLVER_FAIL = "RESOLVER_FAIL"
    RESOLVER_DISAGREE = "RESOLVER_DISAGREE"


# --------------------------------------------------------------------------- manifest


class ManifestIssue(_Strict):
    """A non-fatal manifest problem and its effect on the analysis."""

    field: str
    problem: str
    effect: str


class ContractedScope(_Strict):
    declared_by: str = "user"
    disciplines: tuple[Discipline, ...] = ()
    basis: tuple[dict[str, Any], ...] = ()
    notes: str | None = None


class BoqColumns(_Strict):
    item: str
    description: str
    unit: str
    quantity: str


class Conventions(_Strict):
    """Project conventions. All optional; absence means "not evaluated" (spec §4.2)."""

    document_number_pattern: str | None = None
    discipline_codes: dict[str, Discipline] | None = None
    tag_pattern: str | None = None
    revision_sequence: tuple[str, ...] | None = None
    execution_issue_statuses: tuple[str, ...] | None = None
    boq_columns: BoqColumns | None = None


class ManifestFileEntry(_Strict):
    path: str
    classification: Classification


class ProjectManifest(_Strict):
    """Validated manifest. Built by wall_e.project.load_manifest, which turns
    recoverable problems into ManifestIssue entries instead of failing."""

    schema_version: str
    project_id: str
    title: str | None = None
    description: str | None = None
    delivery_model: DeliveryModel | None = None  # None => reported as UNKNOWN
    delivery_model_raw: str | None = None
    delivery_model_notes: str | None = None
    contracted_scope: ContractedScope | None = None  # None => "not declared"
    default_classification: Classification = Classification.CONFIDENTIAL
    default_classification_source: ClassificationSource = ClassificationSource.BUILT_IN_DEFAULT
    files: tuple[ManifestFileEntry, ...] = ()
    conventions: Conventions = Field(default_factory=Conventions)
    issues: tuple[ManifestIssue, ...] = ()

    @field_validator("project_id")
    @classmethod
    def _project_id(cls, v: str) -> str:
        if not PROJECT_ID_PATTERN.match(v):
            raise ValueError("project_id must match ^[A-Za-z0-9_-]{1,64}$")
        return v

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, v: str) -> str:
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported schema_version {v!r}")
        return v


# --------------------------------------------------------------------------- coverage


class FileRecord(_Strict):
    rel_path: str  # POSIX, relative to project root
    file_type: FileType
    status: FileStatus
    reason: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    classification: Classification
    classification_source: ClassificationSource
    duplicate_of: str | None = None


# --------------------------------------------------------------------------- evidence


class Locator(_Strict):
    """Exactly one of page (PDF) or sheet (XLSX) is set."""

    page: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    sheet: str | None = None
    cell: str | None = None  # "B7" or range "B7:D7"

    @model_validator(mode="after")
    def _one_kind(self) -> Locator:
        is_pdf = self.page is not None
        is_xlsx = self.sheet is not None
        if is_pdf == is_xlsx:
            raise ValueError("locator must set exactly one of page or sheet")
        if is_pdf and self.cell is not None:
            raise ValueError("PDF locator cannot have a cell")
        if is_xlsx and (self.cell is None or self.bbox is not None):
            raise ValueError("XLSX locator requires a cell and no bbox")
        return self

    def canonical(self) -> str:
        return json.dumps(self.model_dump(exclude_none=True), sort_keys=True, separators=(",", ":"))


def make_evidence_id(project_id: str, file_sha256: str, locator: Locator) -> str:
    """Deterministic, project-namespaced evidence ID (spec §11.1)."""
    if not PROJECT_ID_PATTERN.match(project_id):
        raise ValueError("invalid project_id")
    digest = hashlib.sha256(f"{project_id}|{file_sha256}|{locator.canonical()}".encode()).hexdigest()
    return f"{project_id}:{digest[:16]}"


def project_of(namespaced_id: str) -> str:
    project_id, sep, rest = namespaced_id.partition(":")
    if not sep or not rest:
        raise ValueError(f"not a namespaced id: {namespaced_id!r}")
    return project_id


class Evidence(_Strict):
    id: str
    project_id: str
    file_path: str
    file_sha256: str
    locator: Locator
    raw_text: str
    norm_text: str
    extractor: str  # "name==version"
    quality: tuple[QualityFlag, ...] = (QualityFlag.TEXT_OK,)

    @model_validator(mode="after")
    def _id_matches(self) -> Evidence:
        expected = make_evidence_id(self.project_id, self.file_sha256, self.locator)
        if self.id != expected:
            raise ValueError("evidence id does not match its project, file and locator")
        return self


# --------------------------------------------------------------------------- claims


class EvidenceLink(_Strict):
    evidence_id: str
    tier: Tier


class Claim(_Strict):
    id: str
    project_id: str
    section: int = Field(ge=1, le=8)
    rule_id: str
    epistemic_class: EpistemicClass
    statement: str
    evidence: tuple[EvidenceLink, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    search_scope: str | None = None  # required for absence claims
    is_absence_claim: bool = False
    resolution: ResolutionStatus | None = None

    @model_validator(mode="after")
    def _structure(self) -> Claim:
        if project_of(self.id) != self.project_id:
            raise ValueError("claim id is not in the claim's project namespace")
        for link in self.evidence:
            if project_of(link.evidence_id) != self.project_id:
                raise ValueError("claim cites evidence from another project")
        if self.epistemic_class in (EpistemicClass.VERIFIED_FACT, EpistemicClass.SUPPORTED_CONCLUSION):
            if not self.evidence:
                raise ValueError(f"{self.epistemic_class.value} requires at least one evidence link")
        if self.is_absence_claim and not (self.search_scope and self.search_scope.strip()):
            raise ValueError("absence claims require a search_scope")
        return self
