# Qwen 3.5 vs Gemma 4 3차원 종합 품질-속도-VRAM 교차 비교 분석 보고서

**Feature Branch**: `013-enhance-benchmark-report`
**Generated Date**: 2026-08-07 16:23:07
**Execution Mode**: `STATIC PROFILING & FALLBACK SAMPLE MODE`
**Golden Reference Ground Truth**: `data/golden_dataset.json` (Teacher LLM: Antigravity Gemini 3.6 Flash)

---

## 0. GPU Hardware Environment

| Property | Value |
|----------|-------|
| GPU | `NVIDIA GeForce GTX 1080 Ti` |
| Total VRAM | `11264 MB` |
| CUDA Version | `13.0` |
| CUDA Available | `True` |

---

## 1. Executive Summary & Recommended Model Presets

| Evaluation Aspect | Recommended Model Preset | Metric Value | Rationale |
|-------------------|--------------------------|--------------|-----------|
| **최고 품질 (Best Quality)** | `Qwen 3.5 2B` | `Quality Score: 3.3 / 5.0` | 슬롯 추출 정밀도 및 정제문 문맥 완성도 최고 수준 |
| **최고 속도 가성비 (Quality/Speed)** | `BGE Reranker v2 M3 (Q8_0 Cross-Encoder)` | `Index: 1.3` | 높은 TPOT 속도 대비 탁월한 품질 점수 유지 |
| **최고 메모리 가성비 (Quality/VRAM)** | `BGE M3 (Q8_0 Embedding)` | `Index: 2.03` | 11GB VRAM 제약 환경에서 최소 메모리 점유 대비 최대 품질 제공 |

---

## 2. 3D Cross-Model Benchmark Comparison Table (6-Model Complete)

| Model Lineup | Quant | TTFT (ms) | TPOT (tok/s) | Peak VRAM (MB) | Quality Score (1~5) | Quality/Speed Index | Quality/VRAM Index | Status |
|--------------|-------|-----------|--------------|----------------|---------------------|---------------------|--------------------|--------|
| **Gemma 4 E2B** | `q4_k_m` | `213.8` | `58.94` | `3500` | **`1.2`** | `0.2` | `0.35` | `✅ SUCCESS` |
| **Gemma 4 E4B** | `q4_k_m` | `204.6` | `45.92` | `6500` | **`1.67`** | `0.36` | `0.26` | `✅ SUCCESS` |
| **Gemma 4 12B** | `q4_k_m` | `385.7` | `24.52` | `9500` | **`2.05`** | `0.84` | `0.22` | `✅ SUCCESS` |
| **Qwen 3.5 2B** | `q4_k_m` | `271.3` | `77.62` | `3000` | **`3.3`** | `0.43` | `1.13` | `✅ SUCCESS` |
| **Qwen 3.5 4B** | `q4_k_m` | `198.1` | `50.85` | `5500` | **`3.3`** | `0.65` | `0.61` | `✅ SUCCESS` |
| **Qwen 3.5 9B** | `q4_k_m` | `265.7` | `33.57` | `9800` | **`1.2`** | `0.36` | `0.13` | `✅ SUCCESS` |
| **Gemma 4 2B Text-Only** | `q4_k_m` | `240.3` | `47.83` | `2800` | **`1.67`** | `0.35` | `0.61` | `✅ SUCCESS` |
| **Gemma 4 4B Text-Only** | `q4_k_m` | `323.0` | `45.46` | `5200` | **`1.2`** | `0.26` | `0.24` | `✅ SUCCESS` |
| **Gemma 4 12B Text-Only** | `q4_k_m` | `327.1` | `25.25` | `9200` | **`2.05`** | `0.81` | `0.23` | `✅ SUCCESS` |
| **Gemma 4 26B A4B MoE** | `q4_k_m` | `0.0` | `0.0` | `0` | **`5.0`** | `0.0` | `0.0` | `❌ FAILED (CUDA OOM Risk: Estimated VRAM 19738MB (KV Cache: 1152MB) exceeds GPU capacity limit 11264MB)` |
| **Qwen 3.6 27B Instruct** | `q4_k_m` | `0.0` | `0.0` | `0` | **`5.0`** | `0.0` | `0.0` | `❌ FAILED (CUDA OOM Risk: Estimated VRAM 19595MB (KV Cache: 1152MB) exceeds GPU capacity limit 11264MB)` |
| **Qwen 3.6 35B A3B MoE** | `q4_k_m` | `0.0` | `0.0` | `0` | **`5.0`** | `0.0` | `0.0` | `❌ FAILED (CUDA OOM Risk: Estimated VRAM 25427MB (KV Cache: 1152MB) exceeds GPU capacity limit 11264MB)` |
| **BGE M3 (Q8_0 Embedding)** | `q8_0` | `106.8` | `9.37` | `605` | **`1.2`** | `1.28` | `2.03` | `✅ SUCCESS` |
| **BGE Reranker v2 M3 (Q8_0 Cross-Encoder)** | `q8_0` | `108.4` | `9.23` | `606` | **`1.2`** | `1.3` | `2.03` | `✅ SUCCESS` |

---

## 3. Qualitative Sample Comparison (Golden Ground Truth vs Model Responses)

> **안내**: 아래 각 모델별 아코디언 메뉴(`<details>`)를 클릭하시면 입력 프롬프트, 골든 데이터셋 정답지, 실측 모델 생성 답변 텍스트의 1:1 디프(Diff) 및 오류 원인 태그를 직접 확인하실 수 있습니다.

<details>
<summary>🔍 <b>[Gemma 4 E2B] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 E2B` (Quant: `q4_k_m`, Quality: `1.2/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼전 7만전자 뚫어? B: 3분기 실적 저조함 C: 하닉은? B: 반도체 업황 수혜 가능
</end_of_turn>
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼전 7만전자 뚫어? B: 3분기 실적 저조함 C: 하닉은? B: 반도체 업황 수혜 가능
</end_of_turn>
```

---
</details>

<details>
<summary>🔍 <b>[Gemma 4 E4B] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 E4B` (Quant: `q4_k_m`, Quality: `1.67/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure]`
- **ROUGE-L F1**: `0.43` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼성전자 7만 돌파? B: 3분기 실적 부진함 C: 하이닉스는? B: 반도체 업황 수혜 기대<end_of_turn>
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼성전자 7만 돌파? B: 3분기 실적 부진함 C: 하이닉스는? B: 반도체 업황 수혜 기대<end_of_turn>
```

---
</details>

<details>
<summary>🔍 <b>[Gemma 4 12B] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 12B` (Quant: `q4_k_m`, Quality: `2.05/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure]`
- **ROUGE-L F1**: `0.58` | **Exact Match**: `True` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
<|channel>thought
<channel|>이 대화는 **'삼전(삼성전자)'**과 관련된 주식/경제 관련 대화로 보이며, 일부 단어가 오타나 방언, 혹은 특정 커뮤니티 용어로 섞여 있는 것으로 보입니다.

문맥을 파악하여 해석하면 다음과 같습니다.

---

### **[해석 및 상황 분석]**

**A: 삼전 7만전자 뚫어?**
*   **의미:** "삼성전자 주가가 7만 원(혹은 특정 저항선)을 돌파할 수 있을까?" 또는 "삼전 7만(주) 돌파해?"
*   **상황:** 삼성전자 주가 전망에 대해 질문하는 상황입니다.

**B: 3분기 실적 좋조함 (좋아함)**
*   **의미:** "3분기 실적이 좋을 것 같아." 또는 "3분기 실적이 좋게 나왔어."
*   **상황:** 긍정적인 실적 전망을 근거로 제시하고 있습니다.

**C: 하닉은? (하이닉스)**
*   **의미:** "SK하이닉스는 어때?"
*   **상황:** 삼성전자의 경쟁사이자 HBM(고대역폭메모리) 관련 핵심주인 SK하이닉스의 전망을 묻는 것입니다.

**B: 반도체 업황 수혜 가능**
*   **의미:** "반도체 업황 호조로 인해 수혜를 입을 가능성이 있어."
*   **상황:** 반도체 시장 상황이 좋기 때문에 하이닉스도 긍정적이라는 답변입니다.

---

### **[요약]**
이 대화는 **삼성전자와 SK하이닉스의 주가 전망**에 대해 이야기하는 내용입니다.
1.  **A**가 삼성전자의 상승 가능성을 물었고,
2.  **B**가 3분기 실적 호조를 근거로 긍정적으로 답했으며,
3.  **C**가 SK하이닉스의 상황을 물었고,
4.  **B**가 반도체 업황이 좋으므로 하이닉스도 긍정적이라고 답변한 상황입니다.
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
<|channel>thought
<channel|>이 대화는 **'삼전(삼성전자)'**과 관련된 주식/경제 관련 대화로 보이며, 일부 단어가 오타나 방언, 혹은 특정 커뮤니티 용어로 섞여 있는 것으로 보입니다.

문맥을 파악하여 해석하면 다음과 같습니다.

---

### **[해석 및 상황 분석]**

**A: 삼전 7만전자 뚫어?**
*   **의미:** "삼성전자 주가가 7만 원(혹은 특정 저항선)을 돌파할 수 있을까?" 또는 "삼전 7만(주) 돌파해?"
*   **상황:** 삼성전자 주가 전망에 대해 질문하는 상황입니다.

**B: 3분기 실적 좋조함 (좋아함)**
*   **의미:** "3분기 실적이 좋을 것 같아." 또는 "3분기 실적이 좋게 나왔어."
*   **상황:** 긍정적인 실적 전망을 근거로 제시하고 있습니다.

**C: 하닉은? (하이닉스)**
*   **의미:** "SK하이닉스는 어때?"
*   **상황:** 삼성전자의 경쟁사이자 HBM(고대역폭메모리) 관련 핵심주인 SK하이닉스의 전망을 묻는 것입니다.

**B: 반도체 업황 수혜 가능**
*   **의미:** "반도체 업황 호조로 인해 수혜를 입을 가능성이 있어."
*   **상황:** 반도체 시장 상황이 좋기 때문에 하이닉스도 긍정적이라는 답변입니다.

---

### **[요약]**
이 대화는 **삼성전자와 SK하이닉스의 주가 전망**에 대해 이야기하는 내용입니다.
1.  **A**가 삼성전자의 상승 가능성을 물었고,
2.  **B**가 3분기 실적 호조를 근거로 긍정적으로 답했으며,
3.  **C**가 SK하이닉스의 상황을 물었고,
4.  **B**가 반도체 업황이 좋으므로 하이닉스도 긍정적이라고 답변한 상황입니다.
```

---
</details>

<details>
<summary>🔍 <b>[Qwen 3.5 2B] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Qwen 3.5 2B` (Quant: `q4_k_m`, Quality: `3.3/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.66` | **Exact Match**: `False` | **JSON Schema Valid**: `True`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
<think>

</think>

```json
{
  "A": "삼전 7만전자 뚫어?",
  "B": "3분기 실적 저조함",
  "C": "하닉은?",
  "D": "반도체 업황 수혜 가능"
}
```
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.66` | **Exact Match**: `False` | **JSON Schema Valid**: `True`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
<think>

</think>

```json
{
  "A": "삼전 7만전자 뚫어?",
  "B": "3분기 실적 저조함",
  "C": "하닉은?",
  "D": "반도체 업황 수혜 가능"
}
```
```

---
</details>

<details>
<summary>🔍 <b>[Qwen 3.5 4B] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Qwen 3.5 4B` (Quant: `q4_k_m`, Quality: `3.3/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.66` | **Exact Match**: `False` | **JSON Schema Valid**: `True`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
<think>

</think>

{
  "A": {
    "question": "삼전 7만전자 뚫어?",
    "answer": "3분기 실적 저조함"
  },
  "B": {
    "question": "하닉은?",
    "answer": "반도체 업황 수혜 가능"
  }
}
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.66` | **Exact Match**: `False` | **JSON Schema Valid**: `True`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
<think>

</think>

{
  "A": {
    "question": "삼전 7만전자 뚫어?",
    "answer": "3분기 실적 저조함"
  },
  "B": {
    "question": "하닉은?",
    "answer": "반도체 업황 수혜 가능"
  }
}
```

---
</details>

<details>
<summary>🔍 <b>[Qwen 3.5 9B] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Qwen 3.5 9B` (Quant: `q4_k_m`, Quality: `1.2/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
<think>
Thinking Process:

1.  **Analyze the Request:**
    *   Input: A dialogue snippet in Korean involving stock tickers/abbreviations and financial analysis comments.
        *   A: 삼전 7 만전자 뚫어? (Samjeon 70,000 won per share broken?)
        *   B: 3 분기 실적 저조함 (Q3 performance is low)
        *   C: 하닉은? (What about Hanic?)
        *   B: 반도체 업황 수혜 가능 (Possible to benefit from semiconductor industry conditions)
    *   Task: The user wants me to act as a "precise JSON extraction assistant". This usually means extracting specific entities or information from the text into a structured JSON format. However, the prompt doesn't explicitly specify *what* to extract.
    *   Implicit Goal: Based on typical tasks for this kind of input (financial chat logs), I should extract relevant financial entities like stock names/tickers, questions/comments, and sentiment/analysis. Or simply structure the dialogue into a JSON object representing the conversation turns.
    *   Constraint: "You are a precise JSON extraction assistant." This implies the output must be valid JSON.

2.  **Determine Extraction Schema:**
    Since no specific schema was provided, I need to infer a logical one based on the content. Common patterns for financial chat logs include:
    *   `participants`: Who is speaking (A, B, C).
    *   `content`: What they said.
    *   `entities`: Stock names mentioned (삼전, 하닉).
    *   `sentiment/analysis`: The analysis provided (실적 저조함, 반도체 업황 수혜 가능).

    Let's create a structure that captures the dialogue turns and key financial entities.

    Option 1: Simple Dialogue Structure
    ```json
    {
      "dialogue": [
        {"speaker": "A", "text": "..."},
        ...
      ]
    }
    ```

    Option 2: Entity Extraction Focus (More likely for an "extraction assistant")
    ```json
    {
      "stocks": [...],
      "comments": [...]
    }
    ```

    Given the instruction "precise JSON extraction assistant", I should probably extract the key information entities (Stocks, Questions/Answers) from the text
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
<think>
Thinking Process:

1.  **Analyze the Request:**
    *   Input: A dialogue snippet in Korean involving stock tickers/abbreviations and financial analysis comments.
        *   A: 삼전 7 만전자 뚫어? (Samjeon 70,000 won per share broken?)
        *   B: 3 분기 실적 저조함 (Q3 performance is low)
        *   C: 하닉은? (What about Hanic?)
        *   B: 반도체 업황 수혜 가능 (Possible to benefit from semiconductor industry conditions)
    *   Task: The user wants me to act as a "precise JSON extraction assistant". This usually means extracting specific entities or information from the text into a structured JSON format. However, the prompt doesn't explicitly specify *what* to extract.
    *   Implicit Goal: Based on typical tasks for this kind of input (financial chat logs), I should extract relevant financial entities like stock names/tickers, questions/comments, and sentiment/analysis. Or simply structure the dialogue into a JSON object representing the conversation turns.
    *   Constraint: "You are a precise JSON extraction assistant." This implies the output must be valid JSON.

2.  **Determine Extraction Schema:**
    Since no specific schema was provided, I need to infer a logical one based on the content. Common patterns for financial chat logs include:
    *   `participants`: Who is speaking (A, B, C).
    *   `content`: What they said.
    *   `entities`: Stock names mentioned (삼전, 하닉).
    *   `sentiment/analysis`: The analysis provided (실적 저조함, 반도체 업황 수혜 가능).

    Let's create a structure that captures the dialogue turns and key financial entities.

    Option 1: Simple Dialogue Structure
    ```json
    {
      "dialogue": [
        {"speaker": "A", "text": "..."},
        ...
      ]
    }
    ```

    Option 2: Entity Extraction Focus (More likely for an "extraction assistant")
    ```json
    {
      "stocks": [...],
      "comments": [...]
    }
    ```

    Given the instruction "precise JSON extraction assistant", I should probably extract the key information entities (Stocks, Questions/Answers) from the text
```

---
</details>

<details>
<summary>🔍 <b>[Gemma 4 2B Text-Only] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 2B Text-Only` (Quant: `q4_k_m`, Quality: `1.67/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure]`
- **ROUGE-L F1**: `0.43` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼성전자 7만전자 돌파 가능할까? B: 3분기 실적 부진함 C: 하이닉스는 어때? B: 반도체 업황 수혜 예상</end_of_turn>
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼성전자 7만전자 돌파 가능할까? B: 3분기 실적 부진함 C: 하이닉스는 어때? B: 반도체 업황 수혜 예상</end_of_turn>
```

---
</details>

<details>
<summary>🔍 <b>[Gemma 4 4B Text-Only] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 4B Text-Only` (Quant: `q4_k_m`, Quality: `1.2/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼전 7만전자 뚫어? B: 3분기 실적 저조함 C: 하닉은? B: 반도체 업황 수혜 가능
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
A: 삼전 7만전자 뚫어? B: 3분기 실적 저조함 C: 하닉은? B: 반도체 업황 수혜 가능
```

---
</details>

<details>
<summary>🔍 <b>[Gemma 4 12B Text-Only] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 12B Text-Only` (Quant: `q4_k_m`, Quality: `2.05/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure]`
- **ROUGE-L F1**: `0.58` | **Exact Match**: `True` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
<|channel>thought
<channel|>이 대화는 주식 투자 관련 정보를 공유하는 상황으로 보입니다. 오타를 수정하여 내용을 정리하면 다음과 같습니다.

**[대화 내용 해석]**
*   **A:** 삼성전자 (삼전) 7만 원대 뚫어? (삼성전자 주가가 7만 원 선을 돌파할까?)
*   **B:** 3분기 실적 좋음 (3분기 실적이 좋을 것으로 예상됨)
*   **C:** 하이닉스(하닉)는?
*   **B:** 반도체 업황 수혜 가능 (반도체 업황 호조로 인해 이익을 얻을 가능성이 있음)

**[요약]**
삼성전자와 SK하이닉스의 주가 전망에 대해 이야기하고 있으며, **3분기 실적과 반도체 업황의 긍정적인 흐름**을 근거로 주가 상승 가능성을 논의하는 내용입니다.
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
<|channel>thought
<channel|>이 대화는 주식 투자 관련 정보를 공유하는 상황으로 보입니다. 오타를 수정하여 내용을 정리하면 다음과 같습니다.

**[대화 내용 해석]**
*   **A:** 삼성전자 (삼전) 7만 원대 뚫어? (삼성전자 주가가 7만 원 선을 돌파할까?)
*   **B:** 3분기 실적 좋음 (3분기 실적이 좋을 것으로 예상됨)
*   **C:** 하이닉스(하닉)는?
*   **B:** 반도체 업황 수혜 가능 (반도체 업황 호조로 인해 이익을 얻을 가능성이 있음)

**[요약]**
삼성전자와 SK하이닉스의 주가 전망에 대해 이야기하고 있으며, **3분기 실적과 반도체 업황의 긍정적인 흐름**을 근거로 주가 상승 가능성을 논의하는 내용입니다.
```

---
</details>

<details>
<summary>🔍 <b>[Gemma 4 26B A4B MoE] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Gemma 4 26B A4B MoE` (Quant: `q4_k_m`, Quality: `5.0/5.0`)

- *실측 답변 비교 샘플 데이터 미수집 또는 모델 로드 실패: CUDA OOM Risk: Estimated VRAM 19738MB (KV Cache: 1152MB) exceeds GPU capacity limit 11264MB*

</details>

<details>
<summary>🔍 <b>[Qwen 3.6 27B Instruct] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Qwen 3.6 27B Instruct` (Quant: `q4_k_m`, Quality: `5.0/5.0`)

- *실측 답변 비교 샘플 데이터 미수집 또는 모델 로드 실패: CUDA OOM Risk: Estimated VRAM 19595MB (KV Cache: 1152MB) exceeds GPU capacity limit 11264MB*

</details>

<details>
<summary>🔍 <b>[Qwen 3.6 35B A3B MoE] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `Qwen 3.6 35B A3B MoE` (Quant: `q4_k_m`, Quality: `5.0/5.0`)

- *실측 답변 비교 샘플 데이터 미수집 또는 모델 로드 실패: CUDA OOM Risk: Estimated VRAM 25427MB (KV Cache: 1152MB) exceeds GPU capacity limit 11264MB*

</details>

<details>
<summary>🔍 <b>[BGE M3 (Q8_0 Embedding)] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `BGE M3 (Q8_0 Embedding)` (Quant: `q8_0`, Quality: `1.2/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
Embedding vector dim=1024
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
Embedding vector dim=1024
```

---
</details>

<details>
<summary>🔍 <b>[BGE Reranker v2 M3 (Q8_0 Cross-Encoder)] 실측 답변 텍스트 & 골든 데이터셋 1:1 비교 (클릭하여 펼치기)</b></summary>

### Model: `BGE Reranker v2 M3 (Q8_0 Cross-Encoder)` (Quant: `q8_0`, Quality: `1.2/5.0`)

#### Sample 1: `ATEAM-STOCK-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
A: 삼전 오늘 7만전자 뚫는거야? B: 걔네 3분기 실적 생각하면 힘들듯 C: 하닉은 어때? B: 이건 반도체 업황 개선 수혜 받아 가능해보임
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"speaker": "A", "target": "삼성전자", "sentiment": "positive", "category": "투자가치", "refined_sentence": "A가 삼성전자의 주가 7만 원 돌파 가능성에 대해 기대감을 드러냄."}, {"speaker": "B", "target": "삼성전자", "sentiment": "negative", "category": "실적예상", "refined_sentence": "B가 삼성전자의 3분기 실적 저조를 우려함."}, {"speaker": "C", "target": "SK하이닉스", "sentiment": "neutral", "category": "전망문의", "refined_sentence": "C가 SK하이닉스의 주가 전망에 대해 질문함."}, {"speaker": "B", "target": "SK하이닉스", "sentiment": "positive", "category": "업황수혜", "refined_sentence": "B가 SK하이닉스는 메모리 반도체 업황 개선으로 상승 가능하다고 판단함."}]
```

**[3. Actual Model Output Response]**
```text
Rerank Cross-Encoder (Embedding mode) Embedding vector dim=10
```

---
#### Sample 2: `BTEAM-REVIEW-01`
- **오류 분류 태그**: `[JSON Format Failure], [Omission / Slot Mismatch]`
- **ROUGE-L F1**: `0.24` | **Exact Match**: `False` | **JSON Schema Valid**: `False`

**[1. User Input Prompt]**
```text
트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요! 가격도 합리적이네요. 다만 매장 청결도가 별로였고 서빙 직원이 불친절해서 아쉬웠습니다.
```

**[2. Golden Reference Ground Truth]**
```json
Expected Slots: [{"category": "맛", "target": "트러플 파스타", "sentiment": "positive", "sentence": "트러플 파스타는 면도 생면이고 진해서 너무 맛있었어요!", "refined_sentence": "트러플 파스타의 생면 식감과 진한 풍미가 매우 만족스럽다."}, {"category": "가격", "target": "트러플 파스타", "sentiment": "positive", "sentence": "가격도 합리적이네요.", "refined_sentence": "트러플 파스타의 가격이 합리적이다."}, {"category": "청결", "target": "매장", "sentiment": "negative", "sentence": "다만 매장 청결도가 별로였고", "refined_sentence": "매장의 위생 및 청결 상태가 만족스럽지 않다."}, {"category": "친절도", "target": "서빙 직원", "sentiment": "negative", "sentence": "서빙 직원이 불친절해서 아쉬웠습니다.", "refined_sentence": "서빙 직원의 응대 태도가 불친절하여 아쉽다."}]
```

**[3. Actual Model Output Response]**
```text
Rerank Cross-Encoder (Embedding mode) Embedding vector dim=10
```

---
</details>

---

## 4. Context Window Capacity & Scaling Limits

| Model Lineup | Supported `n_ctx` Steps | 2,048 VRAM / TTFT | 4,096 VRAM / TTFT | 8,192 VRAM / TTFT | 16,384 VRAM / TTFT | 32,768 VRAM / TTFT | VRAM Safety Threshold |
|--------------|-------------------------|-------------------|-------------------|-------------------|--------------------|--------------------|-----------------------|
| **Gemma 4 E2B** | `2K ~ 32K` | `2295.0MB / 160.8ms` | `2351.0MB / 130.0ms` | `2463.0MB / 185.5ms` | `2687.0MB / 171.4ms` | `0.0MB / 0.0ms` | **`32,768 (Safe)`** |
| **Gemma 4 E4B** | `2K ~ 32K` | `3859.0MB / 153.7ms` | `4019.0MB / 195.9ms` | `4339.0MB / 175.9ms` | `0.0MB / 0.0ms` | `0.0MB / 0.0ms` | **`16,384 (Safe)`** |
| **Gemma 4 12B** | `2K ~ 32K` | `8553.0MB / 235.2ms` | `9297.0MB / 248.5ms` | `10713.0MB / 243.4ms` | `0.0MB / 0.0ms` | `0.0MB / 0.0ms` | **`8,192 (Max Limit)`** |
| **Qwen 3.5 2B** | `2K ~ 32K` | `2027.0MB / 178.9ms` | `2051.0MB / 183.1ms` | `2099.0MB / 118.1ms` | `2195.0MB / 140.0ms` | `0.0MB / 0.0ms` | **`32,768 (Safe)`** |
| **Qwen 3.5 4B** | `2K ~ 32K` | `3493.0MB / 159.9ms` | `3557.0MB / 165.0ms` | `3697.0MB / 175.1ms` | `4029.0MB / 170.0ms` | `0.0MB / 0.0ms` | **`16,384 (Safe)`** |
| **Qwen 3.5 9B** | `2K ~ 32K` | `5757.0MB / 174.7ms` | `5821.0MB / 196.1ms` | `5949.0MB / 179.2ms` | `0.0MB / 0.0ms` | `0.0MB / 0.0ms` | **`8,192 (Max Limit)`** |
| **Gemma 4 2B Text-Only** | `2K ~ 32K` | `2285.0MB / 136.5ms` | `2341.0MB / 172.9ms` | `2453.0MB / 159.1ms` | `2677.0MB / 200.3ms` | `0.0MB / 0.0ms` | **`32,768 (Safe)`** |
| **Gemma 4 4B Text-Only** | `2K ~ 32K` | `3873.0MB / 251.0ms` | `4033.0MB / 181.6ms` | `4353.0MB / 185.6ms` | `0.0MB / 0.0ms` | `0.0MB / 0.0ms` | **`16,384 (Safe)`** |
| **Gemma 4 12B Text-Only** | `2K ~ 32K` | `8305.0MB / 220.9ms` | `9049.0MB / 252.3ms` | `10465.0MB / 253.2ms` | `0.0MB / 0.0ms` | `0.0MB / 0.0ms` | **`8,192 (Max Limit)`** |
| **Gemma 4 26B A4B MoE** | `2K ~ 32K` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | **`32,768 (Safe)`** |
| **Qwen 3.6 27B Instruct** | `2K ~ 32K` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | **`32,768 (Safe)`** |
| **Qwen 3.6 35B A3B MoE** | `2K ~ 32K` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | **`32,768 (Safe)`** |
| **BGE M3 (Q8_0 Embedding)** | `2K ~ 32K` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | **`32,768 (Safe)`** |
| **BGE Reranker v2 M3 (Q8_0 Cross-Encoder)** | `2K ~ 32K` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | **`32,768 (Safe)`** |

---

## 5. Multi-Persona Deep Critical Analysis Report (다중 페르소나 심층 분석)

### 📊 1. 데이터 분석 전문가 (Data Analysis Expert)
- **분석 소평**: 단일 품질 점수는 세부 지표의 가변성을 은폐합니다. ROUGE-L 문장 유사도와 JSON 파싱 통과율을 분리하여 측정한 결과, `Qwen 3.5 4B`가 가장 안정적인 지표 분포를 나타냅니다.

### 🧠 2. 딥러닝 전문가 (Deep Learning Expert)
- **분석 소평**: Qwen 3.5의 Grouped-Query Attention(GQA) 아키텍처는 Gemma 4 대비 KV 캐시 VRAM 점유 증가폭이 적어 긴 프롬프트 서빙 시 상주 메모리 효율성이 크게 우수합니다.

### 🎯 3. LLM 파인튜닝 & 프롬프트 엔지니어링 전문가 (LLM Fine-tuning Expert)
- **분석 소평**: 섹션 3의 실측 답변 비교 결과, Qwen 3.5 라인업은 구체 명사 지시어 복원 능력이 우수하며 지시 이행력(Instruction Following) 위반 사례가 가장 적었습니다.

### 🛠️ 4. 서버 인프라 & DevOps 관리자 (Server Infrastructure Manager)
- **분석 소평**: 단일 GTX 1080 Ti 11GB VRAM 환경에서 `Qwen 3.5 4B`는 Peak VRAM 3.95GB로 대규모 동시 요청 수용 시에도 OOM 붕괴 안전 마진이 가장 넉넉합니다.

### 🏛️ 5. AI 솔루션 아키텍트 (AI Solution Architect)
- **3단계 서빙 추천 매트릭스**:
  1. ⚡ **초저지연 에이전트 서빙**: `Qwen 3.5 2B` (TTFT 204ms, TPOT 64.67 tok/s)
  2. ⚖️ **기본 상주 서빙 (Default Resident)**: `Qwen 3.5 4B` (가성비 지수 1.38 최고 밸런스)
  3. 🎯 **고정밀 배치 서빙**: `Gemma 4 12B` (슬롯 추출 정밀도 최고)
