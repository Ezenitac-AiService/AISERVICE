import json

from deployment.preflight import validate_environment


def _production_values(gateway_key: str) -> dict[str, str]:
    return {
        "APP_RUN_MODE": "PRODUCTION",
        gateway_key: json.dumps(
            [
                {"url": "http://gpu-a", "gpu_instance": "gpu-a", "healthy": True},
                {"url": "http://gpu-b", "gpu_instance": "gpu-b", "healthy": True},
            ]
        ),
        "REDIS_HA_QUORUM": "3",
    }


def test_production_preflight_accepts_canonical_gateway_setting():
    validate_environment(_production_values("MODEL_GATEWAY_ENDPOINTS"))


def test_production_preflight_accepts_legacy_gateway_alias():
    validate_environment(_production_values("GATEWAY_ENDPOINTS"))
