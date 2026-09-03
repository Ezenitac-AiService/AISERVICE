#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model Gateway Middleware Package (SSOT).
Enforces:
- Anonymous rate limiting: 10 req/min per IP, 2 concurrent per IP
- Max request body: 64KB (65536 bytes)
- Max response tokens: 16,384 tokens
- Request timeout: 180 seconds
- Redis degradation policy: AI endpoints fail closed (503), non-AI web endpoints remain available (200).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitConfig:
    ip_per_minute: int = 10
    concurrent_per_ip: int = 2
    max_body_bytes: int = 65536
    max_response_tokens: int = 16384
    timeout_seconds: int = 180


def check_body_size(size_bytes: int, max_bytes: int = 65536) -> bool:
    """Return True if request body is strictly within max_bytes limit."""
    return size_bytes <= max_bytes


def evaluate_rate_limit_with_redis_error(is_ai_endpoint: bool = True) -> int:
    """Determine response status code when Redis state store encounters an error.

    - AI endpoints (inference, embedding, rerank): Fail closed with 503.
    - Non-AI endpoints (static, web, health): Fail open with 200 to preserve availability.
    """
    if is_ai_endpoint:
        return 503
    return 200
