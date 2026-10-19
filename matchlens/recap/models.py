"""Request, output and report models for recaps and moment explanations."""
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Audience = Literal["analyst", "broadcaster", "fan"]
Length = Literal["short", "medium"]
Language = Literal["en", "hi", "ta"]


class RecapRequest(BaseModel):
    audience: Audience = "analyst"
    length: Length = "medium"
    language: Language = "en"
    refresh: bool = False  # ignore the cache


class RecapParagraph(BaseModel):
    text: str
    cites: list[str]
    language: str | None = None  # set on translated recaps: the language this paragraph is actually in ("en" = fallback)
    note: str | None = None  # why a paragraph is shown in English instead of the requested language


class Recap(BaseModel):
    title: str
    paragraphs: list[RecapParagraph]


class MomentExplanation(BaseModel):
    moment_id: str
    why_it_mattered: str
    context: str
    cites: list[str]
    language: str | None = None
    notes: list[str] = Field(default_factory=list)  # set when a field was left in English


class DroppedItem(BaseModel):
    index: int
    text: str
    cites: list[str]
    errors: list[str]


class AttemptReport(BaseModel):
    attempt: int
    items_total: int = 0
    items_valid: int = 0
    errors: list[str] = Field(default_factory=list)  # every error found, prefixed with the paragraph number
    llm_error: str | None = None  # provider or JSON failure instead of an answer


class UnitTranslation(BaseModel):
    """What happened to one translated unit (the title, a paragraph, or an explanation field)."""

    unit: str  # "title", "paragraph 3", "why_it_mattered", ...
    status: Literal["translated", "english_fallback"]
    attempts: int = 1
    errors: list[str] = Field(default_factory=list)  # every error found, across attempts
    notes: list[str] = Field(default_factory=list)


class TranslationReport(BaseModel):
    language: str
    units: list[UnitTranslation] = Field(default_factory=list)
    names_added: list[str] = Field(default_factory=list)  # entries newly written to data/names/{lang}.json
    names_missing: list[str] = Field(default_factory=list)
    seconds: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fallbacks(self) -> int:
        return sum(1 for u in self.units if u.status == "english_fallback")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def retries(self) -> int:
        return sum(1 for u in self.units if u.attempts > 1)


class ValidationReport(BaseModel):
    method: Literal["llm", "fallback"]
    attempts: list[AttemptReport] = Field(default_factory=list)
    retried: bool = False
    dropped: list[DroppedItem] = Field(default_factory=list)  # items removed from the final output
    title_replaced: bool = False
    fallback_reason: str | None = None
    notes: list[str] = Field(default_factory=list)
    translation: TranslationReport | None = None  # present when language != "en"; the rest describes the English source


class RecapResult(BaseModel):
    match_id: int
    audience: Audience
    length: Length
    language: Language
    model: str
    recap: Recap
    report: ValidationReport
    generation_seconds: float
    cached: bool = False
    source_recap: Recap | None = None  # the validated English recap a translation was made from


class ExplainResult(BaseModel):
    match_id: int
    moment_id: str
    audience: Audience
    language: Language
    model: str
    explanation: MomentExplanation
    report: ValidationReport
    generation_seconds: float
    cached: bool = False
    source_explanation: MomentExplanation | None = None


def translation_schema() -> dict:
    return {"type": "object", "properties": {"translation": {"type": "string"}}, "required": ["translation"]}


def names_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"english": {"type": "string"}, "native": {"type": "string"}},
                    "required": ["english", "native"],
                },
            }
        },
        "required": ["names"],
    }


def recap_schema(ids: list[str], length: str, paragraphs: tuple[int, int]) -> dict:
    """JSON schema for the model. Cited ids are an enum of the moments shown, so unknown ids cannot be emitted."""
    lo, hi = paragraphs
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "paragraphs": {
                "type": "array",
                "minItems": lo,
                "maxItems": hi,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "cites": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": ids}},
                    },
                    "required": ["text", "cites"],
                },
            },
        },
        "required": ["title", "paragraphs"],
    }


def explain_schema(ids: list[str], moment_id: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "moment_id": {"type": "string", "enum": [moment_id]},
            "why_it_mattered": {"type": "string"},
            "context": {"type": "string"},
            "cites": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": ids}},
        },
        "required": ["moment_id", "why_it_mattered", "context", "cites"],
    }
