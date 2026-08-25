# Data Model: 분석 보고서 기반 시스템 최적화 (029-analytics-driven-refactoring)

## 1. 정적 자원 및 메타데이터 엔터티 (Static Assets & Metadata)

### 1.1 Open Graph Service Metadata (`OGMetadata`)

각 서브 서비스의 HTML 헤더에 주입되는 소셜 공유용 메타데이터 엔터티.

| 필드명 | 타입 | 제약사항 | 설명 |
|---|---|---|---|
| `service_id` | `String` | PK (e.g. `portal`, `pilos`, `oliview`, `chata`, `chatb`) | 서비스 고유 식별자 |
| `og_title` | `String` | 필수, <= 60자 | 메신저 링크 공유 시 노출될 대표 제목 |
| `og_description` | `String` | 필수, <= 160자 | 서비스의 핵심 가치 요약 설명 |
| `og_image` | `String` | 필수, 절대 URL (`https://...`) | 1200x630 또는 1:1 비율의 대표 썸네일 이미지 경로 |
| `og_url` | `String` | 필수 | 서비스 진입 정규 URL (Canonical URL) |
| `og_site_name` | `String` | 기본값 `AISERVICE` | 통합 플랫폼 브랜드명 |

---

### 1.2 주식 종목 정적 에셋 및 폴백 모델 (`StockAsset`)

종목 로고 이미지 및 로드 실패 시의 동적 아바타 생성 규칙.

| 필드명 | 타입 | 제약사항 | 설명 |
|---|---|---|---|
| `stock_code` | `String(6)` | 6자리 표준 종목코드 (e.g. `005930`) | 종목 식별 코드 |
| `stock_name` | `String` | 한글 종목명 (e.g. `삼성전자`) | 종목명 |
| `logo_url` | `String` | `/static/images/stock-logos/{stock_code}.png` | 실제 로고 서빙 경로 |
| `fallback_initial` | `String(1)` | 종목명의 첫 글자 (e.g. `'삼'`) | 이미지 실패 시 아바타에 표시할 글자 |
| `fallback_bg_color` | `String` | HSL 또는 HEX 색상 코드 (종목코드 해시 기반) | 아바타의 고유 원형 배경색 |

---

## 2. 포털 실시간 큐레이션 엔터티 (Portal Curation Entities)

### 2.1 주식 감정지수 하이라이트 아이템 (`StockHighlightItem`)

포털 랜딩 화면에 비동기로 렌더링되는 실시간 종목 감정 요약.

```json
{
  "stock_code": "000660",
  "stock_name": "SK하이닉스",
  "sentiment_score": 78.5,
  "sentiment_label": "매우 긍정",
  "sentiment_trend": "up",
  "target_url": "/ateam/pilos/"
}
```

### 2.2 뷰티 리뷰 핫 키워드 아이템 (`BeautyKeywordItem`)

포털 랜딩 화면에 노출되는 화장품 리뷰 인기 카테고리/키워드.

```json
{
  "category_name": "수분/보습 크림",
  "top_brand": "아누아",
  "positive_ratio": 94.2,
  "review_count": 12500,
  "target_url": "/bteam/oliview/"
}
```

---

## 3. 백엔드 에러 복원 응답 모델 (`FallbackApiResponse`)

DB 미존재 또는 일시적 오류 시 반환되는 표준 안전 응답.

```json
{
  "success": true,
  "products": [],
  "categories": [],
  "fallback": true,
  "message": "데이터가 준비 중입니다."
}
```
