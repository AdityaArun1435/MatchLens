"""Request, output and report models for recaps and moment explanations."""
from typing import Literal

from pydantic import BaseModel, Field

Audience = Literal["analyst", "broadcaster", "fan"]
Length = Literal["short", "medium"]
Language = Literal["en"]  # Phase 3: add "hi", "ta"


class RecapRequest(BaseModel):
    audience: Audience = "analyst"
    length: Length = "medium"
    language: Language = "en"
    refresh: bool = False  # ignore the cache


class RecapParagraph(BaseModel):
    text: str
    cites: list[str]


class Recap(BaseModel):
    title: str
    paragraphs: list[RecapParagraph]


class MomentExplanation(BaseModel):
    moment_id: str
    why_it_mattered: str
    context: str
    cites: list[str]


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


class ValidationReport(BaseModel):
    method: Literal["llm", "fallback"]
    attempts: list[AttemptReport] = Field(default_factory=list)
    retried: bool = False
    dropped: list[DroppedItem] = Field(default_factory=list)  # items removed from the final output
    title_replaced: bool = False
    fallback_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


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
