import pytest
from fastapi import HTTPException
from src.core.llama_manager import LlamaManager
from src.core.config_manager import ConfigManager
from src.core.process_manager import ProcessStatusEnum

def test_dual_llm_manager_ports_and_routing():
    """T016 / FR-061: LlamaManager coordinates 2 independent ProcessManagers on ports 8089 and 8088."""
    cm = ConfigManager()
    lm = LlamaManager(cm)

    assert lm.synthesis_pm.port == 8089
    assert lm.router_pm.port == 8088

    # Routing resolution
    assert lm.get_pm_for_model("qwen3.5-9b") == lm.synthesis_pm
    assert lm.get_pm_for_model("qwen3.5-4b") == lm.router_pm
    assert lm.get_pm_for_model("fast") == lm.router_pm
    assert lm.get_pm_for_model(None) == lm.synthesis_pm

def test_dual_llm_context_limits():
    """T016: 9B allows 32K native context without 16K/16GB cutoff guards; 4B allows 8K."""
    cm = ConfigManager()
    lm = LlamaManager(cm)

    assert lm.get_max_allowed_n_ctx("qwen3.5-9b") == 32768
    assert lm.get_max_allowed_n_ctx("qwen3.5-4b") == 8192

def test_validate_request_allowed_unready_rfc9110_503():
    """T016 / RFC 9110: Unready state raises HTTPException(503) with Retry-After: 5."""
    cm = ConfigManager()
    lm = LlamaManager(cm)

    assert not lm.is_ready()
    with pytest.raises(HTTPException) as exc_info:
        lm.validate_request_allowed("qwen3.5-9b")

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("Retry-After") == "5"

@pytest.mark.asyncio
async def test_idle_reclamation_eradicated():
    """T016 / FR-070: check_idle_reclamation is a permanent no-op with zero 2B degradation."""
    cm = ConfigManager()
    lm = LlamaManager(cm)
    # Should complete without error or side-effects
    await lm.check_idle_reclamation(idle_threshold_seconds=0)
