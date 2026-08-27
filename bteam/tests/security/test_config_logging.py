import pytest
from oliview_core.logging import redact_mapping


@pytest.mark.security
def test_secret_values_are_redacted():
    redacted = redact_mapping(
        {"DB_PASSWORD": "secret", "Authorization": "Bearer token", "product_id": 7}
    )
    assert redacted["DB_PASSWORD"] == "[REDACTED]"
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["product_id"] == 7
