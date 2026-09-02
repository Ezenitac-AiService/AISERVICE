# Research Report: 모델 게이트웨이 LLM/임베딩/리랭커 온로드 및 GPU VRAM 가속 정상화

**Feature**: `044-fix-model-gateway-onload`
**Date**: 2026-09-02
**Status**: Completed

## 1. 런타임 백엔드 프로브 및 외장 vLLM 격리 방안

### Decision
`src/config.py`와 `src/core/process_manager.py`의 런타임 프로브 로직에서 게이트웨이 자체 포트(`8081`)에 대한 셀프 루프백 조회를 완전 제거하고, `ENABLE_EXTERNAL_VLLM=true` 환경 변수가 명시적으로 켜져 있을 때만 분리된 외장 포트(`EXTERNAL_VLLM_PORT` 또는 `VLLM_HEALTH_URL`, 기본 `http://127.0.0.1:8000/health`)로 프로브를 수행한다. 기본 상태(`ENABLE_EXTERNAL_VLLM=false`)에서는 1순위로 즉시 로컬 임베디드 `llama.cpp-cuda`를 선택한다.

### Rationale
- 헌법 v1.2.0 원칙 VII(포괄적 무하드코딩 및 인프라 SSOT)에 부합하여, 자기 자신의 포트를 외장 엔진으로 오판하는 셀프 루프백 버그를 원천 차단함.
- 기본 컨테이너 환경에서 불필요한 네트워크 지연 없이 즉시 로컬 GPU 가속 서브프로세스 기동으로 직결됨.

### Alternatives Considered
- *대안 1: vLLM 지원을 코드에서 영구 삭제* -> 향후 고용량 VRAM 클러스터 마이그레이션 시 외장 vLLM 연동 확장성을 유지하기 위해 환경 변수 제어 방식으로 보존 결정.
- *대안 2: vLLM 헬스체크 URL만 8000으로 변경* -> 외장 vLLM이 없는 환경에서 매번 1초간 타임아웃 대기 후 Fallback되는 지연(Latency)이 발생하므로, `ENABLE_EXTERNAL_VLLM` 명시 플래그가 꺼져 있으면 프로브 자체를 스킵하도록 최적화.

---

## 2. Python 모듈 Fallback 시 CUDA VRAM 가속 복구

### Decision
`process_manager.py`의 `verify_and_build_llama_server()`에서 `PYTHON_MODULE_FALLBACK` (독립 C++ 바이너리가 없어 `python3 -m llama_cpp.server`를 사용하는 경우) 시 `is_cuda_enabled`를 `False`로 고정하지 않고, `llama_cpp.llama_supports_gpu_offload()`가 `True`이거나 `torch/CUDA` 가속이 가능할 때 `is_cuda_enabled=True`로 동적 판정한다.

### Rationale
- GTX 1070 (8GB VRAM) 환경에서 컨테이너 내부 `llama_cpp` 모듈은 CUDA 12.x 기반 GPU 가속(`llama_supports_gpu_offload() == True`)을 완벽히 지원함.
- `is_cuda_enabled=True`가 되어야 `ngl_value = "999"`로 설정되어 모델 레이어가 GPU VRAM으로 100% 온로드됨.

### Alternatives Considered
- *대안 1: 무조건 C++ CMake 컴파일 강제* -> 컨테이너 빌드 시점의 의존성 및 시간 소모가 크고, 이미 wheel로 설치된 `llama_cpp_python` 모듈이 최적화되어 있으므로 Python 모듈의 GPU 가속 활성화가 가장 안전하고 빠름.

---

## 3. 프로세스 생존성 및 실시간 PID 바인딩 검증

### Decision
`spawn_process()` 실행 시:
1. `ProcessState`의 초기 상태를 `LOADING`으로 전이.
2. `asyncio.create_subprocess_exec`로 실제 서브프로세스를 생성하고 유효한 OS `PID`를 획득.
3. 대상 포트(8089 / 8090 / 8091)에 대해 `poll_server_health`로 실제 HTTP 200 OK를 확인.
4. 헬스체크가 성공했을 때만 `pid=self.process.pid`가 포함된 `READY` 상태로 전이.
5. 헬스체크 실패 또는 프로세스 조기 종료 시 `ERROR` 상태 및 종료 코드/출력 덤프를 정확히 기록.

### Rationale
- `pid: None` 상태에서 가짜 `READY`를 반환하던 취약점을 제거하여, 프록시 포워딩 시 503 에러가 발생하는 것을 방지하고 장애 시 자동 복구(Auto Recovery)가 정상 발동되도록 보장함.

---

## 4. 보조 모델(임베딩 8090, 리랭커 8091) 동시 기동 및 장애 격리

### Decision
- `AuxiliaryModelManager`의 `start_auto_startup_and_recovery()` 루틴이 게이트웨이 시작 시(FastAPI `lifespan`) 백그라운드로 안전하게 `ensure_embedding_resident("bge-m3")` 및 `ensure_rerank_resident("bge-reranker-v2-m3")`를 스폰하도록 보장.
- 보조 모델의 로딩 상태는 `/health` 종합 엔드포인트에 실시간 반영되며, 기본 LLM 서빙과는 포트 및 장애 도메인이 완벽히 격리(Fault Isolation)됨.

### Rationale
- RAG 챗봇 B 및 필로스의 문서 검색/재순위화 파이프라인이 503 에러 없이 안정적으로 구동됨.
