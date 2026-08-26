# Research: Audit, Zero-Hardcoding, and Hardware-Tiered Dynamic Context OOM Hardening

**Feature**: `034-audit-config-oom-guards`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. 하드웨어 VRAM 기반 동적 컨텍스트 윈도우 사이징 엔진 (Dynamic Context Sizing Formula)

### 1.1 배경 및 동기
과거에는 `n_ctx`가 `4096` 또는 `16384`로 고정 기재되어, 11GB/12GB/24GB와 같이 더 큰 VRAM을 가진 GPU로 이전하더라도 컨텍스트 크기를 확장하지 못하거나 수동 수정이 필요했습니다.  
2026년 LLM 서빙 프레임워크 표준에 따라, 물리 GPU VRAM을 실측하고 가용 메모리 예산 수식에 따라 컨텍스트 크기를 자율 결정합니다.

### 1.2 물리 VRAM 예산 수식
$$\begin{aligned}
V_{\text{Total}} &= \text{NVML Physical GPU VRAM (MB)} \\
V_{\text{Reserved}} &= V_{\text{OS\_UI}}(3,700\text{MB}) + V_{\text{BGE\_Aux}}(1,412\text{MB}) + V_{\text{Margin}}(600\sim1,500\text{MB}) \\
V_{\text{KV\_Budget}} &= V_{\text{Total}} - V_{\text{Reserved}} - W_{\text{Model}} \\
n_{\text{ctx\_dynamic}} &= \min\left(n_{\text{Native\_Max}}, \left\lfloor \frac{V_{\text{KV\_Budget}}}{\text{Bytes\_per\_token\_KV(Q8\_0)}} \right\rfloor \right)
\end{aligned}$$

### 1.3 하드웨어 티어별 자율 결정 매트릭스
* **Tier 1 (8GB, GTX 1070)**: $V_{\text{KV}} \approx 980\text{MB} \rightarrow \mathbf{n_{\text{ctx}} = 16,384 \sim 32,768}$ (`Qwen 3.5 2B`)
* **Tier 2 (11GB, GTX 1080Ti)**: $V_{\text{KV}} \approx 2,552\text{MB} \rightarrow \mathbf{n_{\text{ctx}} = 32,768 \sim 48,000}$ (`Qwen 3.5 4B`)
* **Tier 3 (12GB, RTX 3060)**: $V_{\text{KV}} \approx 3,576\text{MB} \rightarrow \mathbf{n_{\text{ctx}} = 65,536\text{ (64K)}}$ (`Qwen 3.5 4B`)
* **Tier 4 (16GB, RTX 4080)**: $V_{\text{KV}} \approx 7,472\text{MB} \rightarrow \mathbf{n_{\text{ctx}} = 131,072\text{ (128K)}}$ (`4B`) or $\mathbf{32,768\text{ (32K)}}$ (`9B`)
* **Tier 5 (24GB+, RTX 4090/A100)**: $V_{\text{KV}} \approx 12,464\text{MB} \rightarrow \mathbf{n_{\text{ctx}} = 131,072\text{ (128K)}}$ (`Qwen 3.5 9B`)

---

## 2. 하드웨어 감지 기반 FlashAttention 조건부 활성화 및 Pascal SM 6.1 최적화

### 2.1 결정 (Decision)
* GPU Compute Capability를 실시간 조회:
  * **SM < 8.0 (NVIDIA GTX 1070 Pascal SM 6.1 등)**: `--flash_attn` 옵션을 안전하게 생략하고, **Q8_0 KV Cache 양자화 (`--cache-type-k q8_0 --cache-type-v q8_0`)**를 기본 적용하여 VRAM 50% 절감.
  * **SM >= 8.0 (RTX 3060, RTX 40xx, A100 등 Ampere/Ada/Hopper)**: `--flash_attn True`를 자동 활성화하여 O(N) 어텐션 가속 적용.

### 2.2 기술적 근거 (Rationale)
* Pascal 아키텍처는 Tensor Core 하드웨어가 없어 FlashAttention 커널이 지원되지 않거나 비정상 지연/경고를 유발합니다.
* Q8_0 KV Cache는 SM 6.1에서도 완전 지원되어 VRAM을 50% 압축하므로, 8GB GPU에서 32K 컨텍스트를 안정 상주시키는 핵심 메커니즘으로 동작합니다.

---

## 3. 전사 레거시 하드코딩 전수 점검 및 단일 진실 소스화 (SSOT)

### 3.1 점검 대상 및 교체 규칙
1. **Model Gateway (`model_gateway/`)**:
   - `inference_api.py:L361`: `body_json.get("model") or llama_manager.config_manager.get_config().get("current_model", "qwen3.5-4b")` $\rightarrow$ `ConfigManager.get_default_model()`로 동적 일원화.
   - `health_api.py:L23`: 하드코딩된 `device_name = "NVIDIA GeForce GTX 1070"` $\rightarrow$ `get_nvml_vram_info().device_name` 동적 반영.
2. **A-Team & Pilos (`ateam/`)**:
   - `ateam/scripts/test_llm_connection.py`: `CHAT_LLM_MODEL, "qwen3.5-4b"` $\rightarrow$ `FAST_LLM_MODEL` / `SYNTHESIS_LLM_MODEL` 환경변수 동기화.
   - `tests/test_tiered_routing_contract.py` 등 레거시 계약 테스트 파일: 2B 단일 상주 및 동적 프로파일링 규격으로 어설션 일원화.
3. **B-Team Oliview Core (`bteam/`)**:
   - `config.py` & `client.py`: `discover_active_model()`을 단일 진실 소스로 바인딩하고 fallback 상수를 `ConfigManager` 규격과 일치.

---

## 4. OOM 유발 요인 및 리소스 누수 원천 방어 (OOM Defense Architecture)

1. **로딩 프로세스 Cascade Kill 차단**:
   - `LlamaManager`의 `LOADING` 상태 가드를 강화하여, 서브프로세스 기동 중 새로운 요청이 인입되더라도 기존 프로세스를 죽이지 않고 `_wait_for_ready`로 대기 후 안전 서빙.
2. **소켓 바인딩 검증 및 좀비 서브프로세스 강제 회수**:
   - 서브프로세스 종료 시 `SIGTERM` $\rightarrow$ 3초 대기 $\rightarrow$ 미종료 시 `SIGKILL (kill -9)` 강제 회수.
   - 소켓(포트 8089, 8090, 8091)이 완전히 반환되었는지 `socket.connect_ex`로 확인 후 새 프로세스 스폰.
3. **Redis & 인메모리 L1~L5 캐시 상한 관리**:
   - Redis 컨테이너에 `maxmemory 512mb` 및 `maxmemory-policy allkeys-lru` 적용.
