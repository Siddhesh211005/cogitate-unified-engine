"""
Pydantic models for rater schemas, inputs, and outputs.
Defines the canonical JSON API schema that bridges Excel raters to the dynamic UI.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    DATE = "date"
    BOOLEAN = "boolean"


class SheetRole(str, Enum):
    INPUT = "input"
    LOOKUP = "lookup"
    CALCULATION = "calculation"
    OUTPUT = "output"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Schema pieces
# ---------------------------------------------------------------------------

class ValidationRule(BaseModel):
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    required: bool = True
    pattern: Optional[str] = None


class FieldOption(BaseModel):
    label: str
    value: Any


class RaterField(BaseModel):
    """One input or output field extracted from a rater workbook."""
    name: str = Field(..., description="Machine-readable key (derived from named range or label)")
    label: str = Field(..., description="Human-readable label shown in UI")
    field_type: FieldType = Field(default=FieldType.TEXT)
    default_value: Any = None
    options: list[FieldOption] = Field(default_factory=list, description="For SELECT fields")
    validation: Optional[ValidationRule] = None
    sheet: str = Field(default="", description="Source sheet name")
    cell_ref: str = Field(default="", description="Cell reference e.g. E6")
    is_output: bool = False
    formula: Optional[str] = None
    group: str = Field(default="General", description="Logical grouping for UI sections")
    order: int = 0
    impacts_output: bool = Field(default=True, description="Whether this input field affects calculation outputs")


class LookupTable(BaseModel):
    """A rate/lookup table extracted from the workbook."""
    name: str
    sheet: str
    columns: list[str]
    rows: list[dict[str, Any]]
    cell_range: str = ""


class SheetInfo(BaseModel):
    sheet_name: str
    role: SheetRole = SheetRole.UNKNOWN
    row_count: int = 0
    col_count: int = 0
    description: str = ""


class FormulaMapping(BaseModel):
    """Maps an output cell to its Excel formula and the input cells it depends on."""
    output_name: str
    cell_ref: str
    formula: str
    depends_on: list[str] = Field(default_factory=list)


class LLMFieldClassification(BaseModel):
    """LLM-generated classification for a single input field."""
    field_name: str
    impacts_premium: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = ""
    suggested_group: str = ""


class LLMAnalysisResult(BaseModel):
    """Stored result of the one-time LLM analysis at upload."""
    field_classifications: list[LLMFieldClassification] = Field(default_factory=list)
    premium_logic_summary: dict[str, Any] = Field(default_factory=dict)
    dependency_graph: dict[str, Any] = Field(default_factory=dict)
    llm_provider: str = ""
    analyzed: bool = False


# ---------------------------------------------------------------------------
# LLM Chain models (upload-time)
# ---------------------------------------------------------------------------

class OutputClassification(BaseModel):
    """Classification of an output field as final, intermediate, or display."""
    name: str
    cell_ref: str = ""
    sheet: str = ""
    category: str = Field(default="final", description="One of: final, intermediate, display")
    reasoning: str = ""


class FormulaTranslation(BaseModel):
    """An LLM-translated Python expression for an unsupported Excel formula."""
    output_name: str
    cell_ref: str = ""
    original_formula: str = ""
    python_expression: str = ""
    dependencies: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validated: bool = False
    validation_error: Optional[str] = None


class DependencyInfo(BaseModel):
    """Dependency information for one output field."""
    direct_dependencies: list[str] = Field(default_factory=list)
    all_input_dependencies: list[str] = Field(default_factory=list)
    formula_chain: list[str] = Field(default_factory=list)


class ChainResult(BaseModel):
    """Bundled result of the 3-step LLM chain executed at upload time."""
    output_classifications: list[OutputClassification] = Field(default_factory=list)
    dependency_graph: dict[str, DependencyInfo] = Field(default_factory=dict)
    formula_translations: list[FormulaTranslation] = Field(default_factory=list)
    chain_executed: bool = False
    chain_errors: list[str] = Field(default_factory=list)


class CalculationMetadata(BaseModel):
    """Per-rater calculation hints saved alongside schema.json."""
    final_output_keys: list[str] = Field(default_factory=list, description="Cell keys for final premium outputs only")
    final_output_names: list[str] = Field(default_factory=list, description="Field names of final premium outputs")
    intermediate_output_names: list[str] = Field(default_factory=list, description="Field names of intermediate outputs")
    display_output_names: list[str] = Field(default_factory=list, description="Field names worth showing as breakdown")
    formula_translations: list[FormulaTranslation] = Field(default_factory=list)
    dependency_graph: dict[str, DependencyInfo] = Field(default_factory=dict)
    default_validation_passed: bool = False
    default_validation_mismatches: list[str] = Field(default_factory=list)


class RaterSchema(BaseModel):
    """
    The canonical JSON API schema for a parsed rater workbook.
    This is the single source of truth that drives both the dynamic UI
    and the premium calculation engine.
    """
    rater_name: str
    file_name: str
    version: str = "1.0.0"
    sheets: list[SheetInfo] = Field(default_factory=list)
    input_fields: list[RaterField] = Field(default_factory=list)
    output_fields: list[RaterField] = Field(default_factory=list)
    lookup_tables: list[LookupTable] = Field(default_factory=list)
    formula_mappings: list[FormulaMapping] = Field(default_factory=list)
    llm_analysis: Optional[LLMAnalysisResult] = Field(default=None, description="One-time LLM analysis result from upload")


class CalculationRequest(BaseModel):
    """Request payload: user inputs to calculate premiums.
    
    ``inputs`` is an array of objects — each object is a set of key-value
    pairs.  Most raters use a single object; raters like Oakbridge may
    supply multiple input sets.
    """
    rater_id: str
    inputs: list[dict[str, Any]]


class OutputFieldMeta(BaseModel):
    """Metadata for one output field returned alongside calculation results."""
    name: str
    label: str
    group: str = "General"
    order: int = 0
    field_type: str = "number"


class CalculationResult(BaseModel):
    """Response payload: computed premium outputs."""
    rater_id: str
    outputs: dict[str, Any]
    output_fields_meta: list[OutputFieldMeta] = Field(default_factory=list, description="Output field metadata for display")
    warnings: list[str] = Field(default_factory=list)
    refer: bool = False


class UploadResponse(BaseModel):
    model_config = {"populate_by_name": True}

    rater_id: str
    rater_name: str
    rater_schema: RaterSchema = Field(alias="schema")
    duplicate: bool = False
