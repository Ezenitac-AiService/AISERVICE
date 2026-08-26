# Data Model & Schema Specifications: Dynamic Model Discovery

**Feature**: `033-dynamic-model-discovery-sync`  
**Date**: 2026-08-26  
**Status**: Completed

---

## 1. Entities & Pydantic Schema Definitions

### 1.1 Gateway Profile & Model Catalog Entity (`GatewayProfileResponse`)
게이트웨이가 현재 하드웨어 VRAM 및 상주 모델 상태를 클라이언트에 동적으로 노출하는 프로파일 스키마입니다.

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ModelCatalogItem(BaseModel):
    id: str = Field(..., description="모델 고유 식별자 (예: qwen3.5-2b, qwen3.5-4b)")
    object: str = Field(default="model")
    owned_by: str = Field(default="me")
    is_active: bool = Field(default=False, description="현재 VRAM 상주 서빙 여부")
    is_resident: bool = Field(default=False, description="기본 상주 모델 여부")
    max_context_window: int = Field(default=16384, description="지원 최대 컨텍스트 윈도우")
    vram_footprint_mb: int = Field(default=0, description="예상 VRAM 점유량 (MB)")

class GatewayProfileResponse(BaseModel):
    status: str = Field(default="healthy", description="게이트웨이 가동 상태")
    active_model: str = Field(..., description="현재 상주 중인 기본 LLM 모델명")
    current_n_ctx: int = Field(default=16384, description="현재 활성화된 컨텍스트 크기")
    vram_total_mb: int = Field(..., description="GPU 총 VRAM 용량 (MB)")
    vram_used_mb: int = Field(..., description="현재 GPU VRAM 사용량 (MB)")
    single_model_mode: bool = Field(default=True, description="단일 모델 상주 모드 활성화 여부")
    models: List[ModelCatalogItem] = Field(default_factory=list, description="가용 모델 목록")
```

---

### 1.2 Client Discovery Cache Entity (`ModelDiscoveryCache`)
클라이언트(`AiGatewayClient`)가 게이트웨이 질의 결과를 메모리에 저장하여 추론 지연을 0ms로 유지하는 캐시 엔티티입니다.

```python
import time
from dataclasses import dataclass

@dataclass
class ModelDiscoveryCache:
    discovered_model: str = "qwen3.5-2b"
    discovered_n_ctx: int = 16384
    last_synced_at: float = 0.0
    ttl_seconds: float = 60.0

    def is_valid(self) -> bool:
        """캐시가 유효한지 확인 (TTL 60초)."""
        return (time.time() - self.last_synced_at) < self.ttl_seconds

    def update(self, model: str, n_ctx: int):
        """캐시 갱신."""
        self.discovered_model = model
        self.discovered_n_ctx = n_ctx
        self.last_synced_at = time.time()
```

---

### 1.3 Client Core Settings (`CoreSettings`)
클라이언트 환경 설정 Pydantic 모델에 동적 모델 탐색 필드를 통합합니다.

```python
class CoreSettings(BaseModel):
    # Model Gateway Configuration
    server_host: str = Field(default_factory=_detect_default_server_host)
    main_port: int = Field(default_factory=lambda: int(os.getenv("MAIN_PORT", "8081")))
    
    # Model Names (Dynamic Discovery Enabled)
    fast_llm_model: str = Field(default_factory=lambda: os.getenv("FAST_LLM_MODEL", "qwen3.5-2b"))
    synthesis_llm_model: str = Field(default_factory=lambda: os.getenv("SYNTHESIS_LLM_MODEL", "qwen3.5-2b"))
    auto_discover_model: bool = Field(default=True, description="게이트웨이 활성 모델 자동 탐색 활성화 여부")
    discovery_ttl_seconds: float = Field(default=60.0, description="동적 모델 탐색 캐시 주기")
    
    # VRAM & Context Safety
    min_required_n_ctx: int = Field(default=16384, description="최소 보장 컨텍스트 크기 (16K)")
```
