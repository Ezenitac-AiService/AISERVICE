# Data Model: 017-korean-markdown-prompt-optimization

## 1. Markdown Rule Config Schema

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Pattern

class MarkdownRuleConfig(BaseModel):
    forbidden_patterns: List[str] = Field(
        default_factory=lambda: [r'\*\*["\'].+?["\']\*\*[가-힣]+'],
        description="파싱 깨짐을 유발하여 프롬프트에서 금지되는 패턴"
    )
    recommended_prefix: str = "- **{label}:** {content}"
    html_strong_tag_fallback: bool = True
```

## 2. Token Normalization State

```python
class NormalizationResult(BaseModel):
    original_text: str
    normalized_text: str
    replacement_count: int = 0
    latency_ms: float = 0.0
```
