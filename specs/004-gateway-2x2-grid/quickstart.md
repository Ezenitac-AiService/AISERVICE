# Quickstart: 게이트웨이 2x2 대칭 그리드 검증 가이드 (004-gateway-2x2-grid)

**Feature**: `004-gateway-2x2-grid`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/004-gateway-2x2-grid/plan.md)

---

## 1. 개요 및 사전 조건

게이트웨이 포털의 HTML/CSS(`gateway/html/index.html`)가 2x2 대칭 그리드로 정상 렌더링되는지 로컬 및 공인 도메인에서 신속하게 검증합니다.

---

## 2. 정적 파일 핫 리로드 (Hot Reload)

`gateway/html/index.html`은 Nginx 컨테이너에 볼륨 마운트(`gateway/html:/usr/share/nginx/html:ro`)되어 있으므로, 파일 저장 즉시 브라우저 새로고침(F5 / Ctrl+F5)으로 반영됩니다.

```powershell
# 필요한 경우 Nginx 게이트웨이 릴로드
docker compose exec gateway nginx -s reload
```

---

## 3. 검증 시나리오

### 시나리오 1: 데스크톱 2x2 대칭 배치 확인
1. 브라우저에서 `https://ezenitac.duckdns.org/` 또는 `http://localhost:8080/` 접속
2. 화면에 4개의 서비스 카드가 상단 2개 (Pilos, Oliview), 하단 2개 (올리챗, 올원챗)로 2x2 대칭 배치되는지 확인
3. 우측에 비어있는 3번째 열 슬롯이 없고 중앙에 균형 있게 배치되는지 확인

### 시나리오 2: 모바일 1열 반응형 전환 확인
1. 브라우저 개발자 도구(F12) 활성화 후 화면 폭을 768px 이하로 축소
2. 2열 카드가 1열 세로 스택으로 매끄럽게 전환되는지 확인

### 시나리오 3: 4개 서비스 카드 링크 동작 확인
1. `Pilos 감정지수 서비스` 클릭 → `/ateam/pilos` 이동 확인
2. `Oliview 메인 서비스` 클릭 → `/bteam/oliview` 이동 확인
3. `올리챗 (Oliview Chat A)` 클릭 → `/bteam/chata` 이동 확인
4. `올원챗 (Oliview Chat B)` 클릭 → `/bteam/chatb` 이동 확인
