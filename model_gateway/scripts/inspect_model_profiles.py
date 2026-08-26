import json
import os
from pathlib import Path
from src.core.config_manager import ConfigManager
from src.core.process_manager import ProcessManager
from src.core.gpu_detector import estimate_kv_cache_vram, calculate_max_allocatable_n_ctx

def evaluate_all_models_for_gtx1070():
    cm = ConfigManager()
    catalog = cm.get_model_catalog()
    
    # GTX 1070 Total VRAM = 8192 MB
    total_vram_mb = 8192
    safety_reserve_mb = 600  # Reserved for OS/Display/WSL2
    max_usable_vram_mb = total_vram_mb - safety_reserve_mb  # ~7592 MB
    
    # Embedding (605MB) + Reranker (606MB) background reserve if enabled = ~1211 MB
    # Usable for LLM main process = ~6380 MB
    llm_usable_vram_mb = max_usable_vram_mb - 1211
    
    evaluated = []
    
    for model_id, entry in catalog.items():
        task_type = str(entry.get("task_type", "llm")).lower()
        model_name = entry.get("name", model_id)
        size_gb = entry.get("size_gb", 0.0)
        quant_type = entry.get("quant_type", "q4_k_m")
        vram_est_mb = entry.get("vram_est_mb", 0)
        default_n_ctx = entry.get("default_n_ctx", 4096)
        max_n_ctx = entry.get("max_n_ctx", 131072)
        requires_mmproj = entry.get("requires_mmproj", False)
        
        # Base model VRAM
        base_vram_mb = int(size_gb * 1024 * 1.15) if size_gb else vram_est_mb
        
        n_layers = entry.get("n_layers", 36)
        n_heads = entry.get("n_heads", 32)
        n_head_kv = entry.get("n_head_kv", 8)
        head_dim = entry.get("head_dim", 128)
        
        if task_type in ("embedding", "rerank", "tasktypeenum.embedding", "tasktypeenum.rerank"):
            is_supported = True
            rec_ctx = default_n_ctx
            max_ctx = default_n_ctx
            reason = "보조 백엔드 서비스 (전용 포트 8090/8091 상주 구동)"
        else:
            # Check if base weight fits in VRAM
            if base_vram_mb > max_usable_vram_mb:
                is_supported = False
                rec_ctx = 0
                max_ctx = 0
                reason = f"VRAM 용량 초과 (기본 가중치 {base_vram_mb}MB > 최대 가용 {max_usable_vram_mb}MB)"
            else:
                remaining_kv_budget = max_usable_vram_mb - base_vram_mb
                
                # Calculate max context window allocatable within remaining VRAM budget
                max_ctx = calculate_max_allocatable_n_ctx(
                    usable_kv_budget_mb=remaining_kv_budget,
                    n_layers=n_layers,
                    n_heads=n_heads,
                    head_dim=head_dim,
                    max_cap=max_n_ctx
                )
                
                # Align to 512 boundary
                max_ctx = (max_ctx // 512) * 512
                
                if max_ctx < 1024:
                    is_supported = False
                    rec_ctx = 0
                    reason = f"KV 캐시 VRAM 부족 (최대 컨텍스트 {max_ctx} < 최소 1024)"
                else:
                    is_supported = True
                    # Recommended context window is balanced between 4096 ~ max_ctx
                    rec_ctx = min(max_ctx, default_n_ctx if default_n_ctx <= max_ctx else max_ctx)
                    reason = f"GPU 100% 가속 서빙 가능 (KV Cache 여유: {remaining_kv_budget}MB)"
                    
        evaluated.append({
            "model_id": model_id,
            "model_name": model_name,
            "task_type": task_type,
            "size_gb": size_gb,
            "quant_type": quant_type,
            "base_vram_mb": base_vram_mb,
            "is_supported": is_supported,
            "recommended_context": rec_ctx,
            "max_context": max_ctx,
            "requires_mmproj": requires_mmproj,
            "reason": reason
        })
        
    return evaluated

if __name__ == "__main__":
    results = evaluate_all_models_for_gtx1070()
    
    profiles = {}
    for r in results:
        profiles[r["model_id"]] = {
            "model_name": r["model_name"],
            "task_type": r["task_type"],
            "is_supported": r["is_supported"],
            "recommended_context_length": r["recommended_context"],
            "max_context_length": r["max_context"],
            "base_vram_mb": r["base_vram_mb"],
            "quant_type": r["quant_type"],
            "status_reason": r["reason"]
        }
        
    output_path = "config/model_context_profiles.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=4, ensure_ascii=False)
        
    print(f"✅ Generated {output_path}")
    print(json.dumps(profiles, indent=2, ensure_ascii=False))
