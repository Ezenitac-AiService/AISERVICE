# Contract: Markdown Normalization Contract

## Interface Signatures

### Python Sanitizer Function (`bteam/oliview_core/sanitizer.py`)

```python
def normalize_korean_markdown(text: str) -> str:
    """
    Scans for CommonMark right-flanking collision patterns in Korean text:
      1. **"텍스트"**조사 -> <strong>"텍스트"</strong>조사
      2. **텍스트**조사   -> <strong>텍스트</strong>조사
    Returns clean, parser-safe string.
    """
    ...
```

### JavaScript Sanitizer Function (`chat.js` / Web UI)

```javascript
function sanitizeKoreanMarkdown(markdown: string): string {
    // Replaces Korean delimiter collisions before marked / markdown parsing
}
```

## Test Vectors

| Input String | Expected Output | Rationale |
| :--- | :--- | :--- |
| `**"자극 느껴져요"**라는 피드백` | `<strong>"자극 느껴져요"</strong>라는 피드백` | Right-flanking collision fixed |
| `**"효과는 일반 토너랑 비슷함"**이라고` | `<strong>"효과는 일반 토너랑 비슷함"</strong>이라고` | Double quote + Korean postposition fixed |
| `- **수분감:** 아주 촉촉합니다.` | `- **수분감:** 아주 촉촉합니다.` | Standard format preserved as-is |
| `일반 텍스트 문장입니다.` | `일반 텍스트 문장입니다.` | Unchanged |
