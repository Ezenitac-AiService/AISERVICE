"""
UTF-8 byte length & protocol encoding utility module for vllm_serv (T004).
Ensures exact Content-Length calculation and safe payload byte encoding.
"""

import json
from typing import Any, Union


def get_utf8_byte_length(data: Union[str, bytes]) -> int:
    """Calculate exact UTF-8 byte length of string or byte payload.
    
    Prevents h11.LocalProtocolError caused by string length vs byte count mismatch
    (e.g., multi-byte Korean characters).
    """
    if isinstance(data, bytes):
        return len(data)
    elif isinstance(data, str):
        return len(data.encode("utf-8"))
    raise TypeError(f"Expected str or bytes, got {type(data)}")


def encode_json_payload(data: Any) -> bytes:
    """Serialize data into UTF-8 encoded JSON bytes with exact byte length guaranteed."""
    json_str = json.dumps(data, ensure_ascii=False)
    return json_str.encode("utf-8")
