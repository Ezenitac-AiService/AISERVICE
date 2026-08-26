from pydantic import BaseModel, Field

class BinaryChecklist(BaseModel):
    """LLM 에이전트가 코드를 스캔하여 내놓는 이진 판정 항목 스키마"""
    has_meaningless_assertions: bool = Field(
        description="True if trivial constant assertions like assert True or assert 1 == 1 exist"
    )
    has_trivial_assert_fallback: bool = Field(
        description="True if assertions are shallow, e.g., only checking assert result is not None"
    )
    is_mocking_abused: bool = Field(
        description="True if business logic is fully stubbed out with mock.patch, disabling actual logic checks"
    )
    contains_exception_eater: bool = Field(
        description="True if empty try-except pass blocks absorb runtime exceptions to force tests to pass"
    )
    virtual_mutant_killed: bool = Field(
        description="True if the test suite would catch and fail when operator/logic mutations are simulated"
    )
    detected_cheat_details: list[str] = Field(
        default_factory=list,
        description="Details of cheat/bypass patterns with file and line numbers"
    )
    feedback_guide: str = Field(
        description="Actionable guide and suggestions to improve the TDD test suite"
    )
