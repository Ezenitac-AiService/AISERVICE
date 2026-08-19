# Data Model: 018-llm-server-refactoring-optimization

## 1. Engine Configuration & Runtime State Entities

### `EngineConfig`
```typescript
interface EngineConfig {
  engine_type: "llama_cpp" | "vllm" | "mock";
  model_id: string;
  n_ctx: number;
  max_tokens: number;
  flash_attn: boolean;
  ctk: "f16" | "q8_0" | "q4_0";
  ctv: "f16" | "q8_0" | "q4_0";
  batch_size: number;
  ubatch_size: number;
  cache_prompt: boolean;
  idle_timeout_seconds: number;
}
```

### `ModelProfile`
```typescript
interface ModelProfile {
  model_id: string;
  model_name: string;
  task_type: "llm" | "embedding" | "rerank";
  base_vram_mb: number;
  recommended_n_ctx: number;
  max_n_ctx: number;
  quant_type: string;
  is_supported: boolean;
  requires_mmproj: boolean;
}
```

### `InferenceMetrics`
```typescript
interface InferenceMetrics {
  timestamp: number;
  model_id: string;
  ttft_seconds: number;
  tokens_per_second: number;
  prompt_tokens: number;
  completion_tokens: number;
  cache_hit: boolean;
  thinking_tokens?: number;
}
```
