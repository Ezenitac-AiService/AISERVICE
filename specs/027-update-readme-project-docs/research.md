# Research Document: 027-update-readme-project-docs

## 1. Documentation Modularity & Architecture Separation

### Decision
메인 `README.md`는 고수준 총괄 대시보드(Overview, Architecture, Service Map, Quickstart, TOC, MIT License)로 슬림화하고, 상세 기술 문서는 `docs/` 디렉토리 하위의 5개 전용 마크다운 파일로 분리한다:
1. `docs/architecture.md`: 전체 네트워크 및 K8s Ingress / Traefik / Nginx 프록시 토폴로지
2. `docs/model_gateway.md`: LLM GPU 서빙 게이트웨이, 2B 상주 체제, 16K ctx, SINGLE_MODEL_MODE
3. `docs/bteam_oliview.md`: Oliview 뷰티 리뷰 분석 플랫폼 & 챗봇 A/B 아키텍처
4. `docs/ateam_pilos.md`: Pilos 주식 수급 감정지수 플랫폼 & 7단계 배치 데몬
5. `docs/security_guardrails.md`: 4단계 CPU 가드레일 & 3단계 하이브리드 토큰 정책

### Rationale
- 단일 `README.md`에 모든 세부 코드를 담을 경우 문서가 수백 줄로 비대해져 첫인상과 탐색성이 저하됨.
- 도메인별 분리를 통해 각 팀 및 담당자가 관심 있는 기술 문서를 독립적으로 열람하고 업데이트할 수 있음.

---

## 2. Licensing Policy

### Decision
프로젝트 라이센스로 **MIT License**를 채택하고, 루트에 `LICENSE` 파일을 생성하며 `README.md` 하단에 라이센스 고지 문구를 명시한다.

### Rationale
- 오픈소스 표준 라이센스로서 자유로운 사용, 수정, 배포를 보장하며 저작권 고지를 명확히 함.

---

## 3. Technical Accuracy Verification

### Decision
문서에 기재되는 모든 시스템 사양, 포트 번호, GPU VRAM 실측치, 토큰 수치 등은 최신 실측 상태와 100% 일치하도록 작성한다:
- GPU: NVIDIA GeForce GTX 1070 (8GB VRAM)
- Resident Models: `bge-m3` (8090, ~1.2GB) + `bge-reranker-v2-m3` (8091, ~1.2GB) + `qwen3.5-2b` (8089, ~2.7GB with 16K ctx)
- Total Measured VRAM: ~4.1 GB / 8.0 GB (여유 VRAM 4.1GB 확보)
- Token Budgets: Fast Intent (512) / Interactive RAG (2048) / Deep Report (4096)
- Public HTTPS Domain: `https://ezenitac.duckdns.org`
