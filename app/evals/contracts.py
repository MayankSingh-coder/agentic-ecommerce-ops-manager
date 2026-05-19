from typing import Any

from pydantic import BaseModel, Field


class EvalAssertions(BaseModel):
    required_substrings: list[str] = Field(default_factory=list)
    forbidden_substrings: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    case_id: str
    input: dict[str, Any]
    assertions: EvalAssertions


class EvalSuite(BaseModel):
    suite_id: str
    prompt_id: str
    agent: str
    min_score: float = Field(ge=0, le=1)
    cases: list[EvalCase]


class EvalCaseResult(BaseModel):
    suite_id: str
    case_id: str
    prompt_id: str
    passed: bool
    score: float
    missing_required: list[str] = Field(default_factory=list)
    found_forbidden: list[str] = Field(default_factory=list)
    output: str


class EvalSuiteResult(BaseModel):
    suite_id: str
    prompt_id: str
    passed: bool
    score: float
    min_score: float
    case_results: list[EvalCaseResult]
