# Contract: Oliview Backend API Endpoints

**Component**: B-Team Oliview Backend (`oliview_backend:5050`)  
**Base URL (Public)**: `https://ezenitac.duckdns.org/bteam/oliview/api`  
**Internal Port**: `5050`

---

## 1. Brand Management & Authentication

### `GET /api/brands`
- **Description**: 등록된 3,062개 브랜드 목록 조회 및 키워드 검색
- **Query Parameters**:
  - `keyword` (string, optional): 브랜드명 또는 브랜드코드 검색어. 생략 시 전체 3,062개 반환.
- **Response**: `200 OK`
  ```json
  {
    "success": true,
    "brands": [
      {
        "brand_id": 1,
        "brand_name": "구달",
        "brand_code": "goodal"
      }
    ]
  }
  ```

### `GET /api/search-brands` (Alias for Backward Compatibility)
- **Description**: 기존 프론트엔드 호환용 별칭. `/api/brands?keyword=...`와 동일 동작 수행.
- **Response**: `200 OK` (동일 스키마)

### `POST /api/check-email`
- **Description**: 담당자 이메일 중복 여부 사전 검증
- **Request Body**:
  ```json
  {
    "email": "manager@goodal.com",
    "currentBrandId": null
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "success": true,
    "isDuplicate": false
  }
  ```

### `POST /api/send-auth-code`
- **Description**: 이메일 인증번호 6자리 생성 및 Gmail SMTP 발송
- **Request Body**:
  ```json
  {
    "email": "manager@goodal.com"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "success": true,
    "message": "인증번호가 발송되었습니다."
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: 이메일 누락 또는 SMTP 발송 실패 (JSON 메시지: `"이메일 발송에 실패했습니다. 메일 주소를 확인하거나 잠시 후 다시 시도해주세요."`)

### `POST /api/verify-auth-code`
- **Description**: 6자리 인증코드 일치 여부 및 만료 시간(TTL 5분) 검증
- **Request Body**:
  ```json
  {
    "email": "manager@goodal.com",
    "code": "123456"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "success": true,
    "message": "인증이 완료되었습니다."
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: 인증번호 불일치, 만료 또는 5회 이상 실패
