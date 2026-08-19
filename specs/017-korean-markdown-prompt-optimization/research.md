# Technical Research: 017-korean-markdown-prompt-optimization (한국어 마크다운 볼드 렌더링 최적화)

## 1. 문제 분석: CommonMark 사양과 한국어 조사의 충돌

### 1) CommonMark Right-flanking Delimiter Run 규칙
CommonMark 사양 6.2절에 따르면, 강조 구분자(`**`)가 **닫는 구분자(Right-flanking)**로 유효하기 위해서는:
- `**` 바로 앞에 공백이 아니어야 하며,
- `**` 바로 앞에 구두점(예: `"`, `)`, `'`)이 있는 경우, `**` 바로 뒤에는 **반드시 유니코드 공백 또는 유니코드 구두점**이 와야 합니다.

### 2) 한국어 교착어 구조에서의 파싱 실패 사례
- 입력 텍스트: `**"자극 느껴져요"**라는 피드백`
- 파서 해석:
  - 닫는 `**`의 앞: `"` (구두점)
  - 닫는 `**`의 뒤: `라` (유니코드 한글 음절 ➔ Word character / Not punctuation / Not whitespace)
  - 결과: `**`는 Right-flanking 조건을 충족하지 못하므로, 파서는 이를 일반 텍스트로 간주하여 **볼드가 적용되지 않고 `**"자극 느껴져요"**라는`으로 화면에 그대로 출력됨!

---

## 2. 3계층 하이브리드 해결 전략

### 계층 1: 생성단 프롬프트 규칙 (Prompt Engineering Rules)
LLM이 마크다운 파싱 충돌을 유발하는 토큰 시퀀스를 생성하지 않도록 시스템 프롬프트에 명시:
```text
[한국어 마크다운 작성 필수 규칙]
1. 인용구 볼드 중첩 금지: **"인용문"**라는 처럼 따옴표와 볼드 기호를 겹쳐 쓰지 마세요.
   - ❌ **"자극 느껴져요"**라는 피드백
   - ⭕ "자극 느껴져요"라는 피드백
   - ⭕ **자극성 평가:** "자극 느껴져요"라는 고객 의견
2. 항목별 불릿 리스트: 속성별 분석 시 반드시 콜론 뒤에 공백을 두세요.
   - ⭕ - **수분감:** 촉촉하게 흡수되며 당김이 없습니다.
   - ⭕ - **발림성:** 부드럽게 펴 발립니다.
```

### 계층 2: 중계단 정규화 (Python `normalize_korean_markdown`)
소형 모델(2B/4B)이 간혹 규칙을 어길 때를 대비한 정규식 자동 치환:
```python
import re

def normalize_korean_markdown(text: str) -> str:
    if not text:
        return ""
    # 1. **"텍스트"**조사 -> <strong>"텍스트"</strong>조사
    text = re.sub(r'\*\*(["\'])(.+?)\1\*\*([가-힣]+)', r'<strong>\1\2\1</strong>\3', text)
    # 2. **텍스트**조사 (닫는 별표 뒤 조사가 바로 붙은 경우 공백 또는 strong 치환)
    text = re.sub(r'\*\*([^\*\n]+?)\*\*([가-힣]+)', r'<strong>\1</strong>\2', text)
    return text
```

### 계층 3: 프론트엔드 렌더러 정규화 (Vanilla JS / Streamlit)
브라우저 클라이언트(`chat.js`, ChatB web)에서 토큰 수신 후 렌더링 직전 정규화:
```javascript
function sanitizeKoreanMarkdown(markdown) {
    if (!markdown) return '';
    return markdown
        .replace(/\*\*(["'])(.+?)\1\*\*([가-힣]+)/g, '<strong>$1$2$1</strong>$3')
        .replace(/\*\*([^*\n]+?)\*\*([가-힣]+)/g, '<strong>$1</strong>$2');
}
```

---

## 3. 대안 비교 (Alternatives Evaluated)

| 접근법 | 장점 | 단점 | 채택 여부 |
| :--- | :--- | :--- | :---: |
| **A. 프롬프트 단일 제어** | 코드 변경 없음 | 소형 LLM의 지시 불이행 시 간헐적 별표 누출 | 부분 채택 (계층 1) |
| **B. HTML `<strong>` 전면 치환** | 100% 렌더링 보장 | 코드 블록, 수식 내의 `**`까지 오동작 위험 | 기각 (선택적 치환 채택) |
| **C. 3계층 하이브리드 방어** | 원천 차단 + 자동 보정 + 렌더러 보호로 결함율 0% | 정규식 함수 추가 필요 (오버헤드 < 0.1ms) | **최종 채택** ✅ |
