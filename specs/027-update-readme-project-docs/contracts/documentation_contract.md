# Contract: Documentation Links & Markdown Standards (027-update-readme-project-docs)

## 1. Internal Markdown Link Contract

| 링크 대상 | 링크 텍스트 | 상대 경로 | 대상 파일 실존 여부 |
| :--- | :--- | :--- | :---: |
| **시스템 아키텍처** | `[전체 시스템 아키텍처 상세](docs/architecture.md)` | `docs/architecture.md` | 필수 작성 |
| **Model Gateway** | `[Model Gateway & GPU 서빙 상세](docs/model_gateway.md)` | `docs/model_gateway.md` | 필수 작성 |
| **B-Team Oliview** | `[B-Team Oliview & 챗봇 A/B 상세](docs/bteam_oliview.md)` | `docs/bteam_oliview.md` | 필수 작성 |
| **A-Team Pilos** | `[A-Team Pilos & 배치 워커 상세](docs/ateam_pilos.md)` | `docs/ateam_pilos.md` | 필수 작성 |
| **보안 가드레일** | `[4단계 보안 가드레일 & 토큰 정책](docs/security_guardrails.md)` | `docs/security_guardrails.md` | 필수 작성 |
| **라이센스** | `[MIT License](LICENSE)` | `LICENSE` | 필수 작성 |

---

## 2. Formatting & Quality Rules

1. **GitHub Flavored Markdown (GFM)**: 표, 인용구, 코드 블록 문법 준수.
2. **상대 링크(Relative Link)**: 외부 웹이 아닌 레포지토리 내 상대 경로(`docs/*.md`, `LICENSE`) 사용.
3. **깨진 링크 0건(Zero Broken Links)**: 모든 링크가 실제 유효한 파일로 연결되어야 함.
