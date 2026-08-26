from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class KeywordContributionDTO:
    keyword: str
    contribution: float