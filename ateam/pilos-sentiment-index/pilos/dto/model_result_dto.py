from dataclasses import dataclass
from datetime import date
from pilos.dto.keyword_contribution_dto import KeywordContributionDTO

@dataclass(frozen=True, slots=True)
class ModelResultDTO:
    artifact_id: int
    model_variant: str
    
    supply_demand_association_score: float # 수급 연관 점수
    intercept: float
    text_score: float
    comment_count_contribution: float # 댓글 수 기여도
    recognized_feature_count: int
    unique_token_count: int | None
    vocabulary_coverage: float | None
    inference_status: str | None

    # 긍/부정 주요 키워드
    positive_keywords: tuple[KeywordContributionDTO, ...] #list도 가능지만 튜플로만들어 수정 불가능상태
    negative_keywords: tuple[KeywordContributionDTO, ...]
