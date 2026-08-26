import ipaddress
from typing import List, Optional
from starlette.middleware.base import BaseHTTPMiddleware

from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import status

class IpSubnetGuard:
    """FR-008: IP CIDR 대역 접근 제어 헬퍼 클래스."""

    def __init__(self, allowed_subnets: List[str]):
        self.networks = []
        for cidr in allowed_subnets:
            try:
                # 단일 IP("127.0.0.1") 또는 CIDR 대역("192.168.0.0/24") 파싱
                net = ipaddress.ip_network(cidr, strict=False)
                self.networks.append(net)
            except ValueError:
                pass

    def is_allowed(self, client_host: Optional[str]) -> bool:
        if not client_host:
            return False

        # localhost 및 루프백 예외 처리
        if client_host in ("testclient", "localhost"):
            client_host = "127.0.0.1"

        try:
            client_ip = ipaddress.ip_address(client_host)
            return any(client_ip in net for net in self.networks)
        except ValueError:
            return False


class SubnetFilterMiddleware(BaseHTTPMiddleware):
    """FR-008: 허용된 사설망 및 로컬 IP 대역(127.0.0.1, 192.168.0.0/24) 외 차단 미들웨어."""

    def __init__(self, app, allowed_subnets: List[str]):
        super().__init__(app)
        self.guard = IpSubnetGuard(allowed_subnets)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Allow public access to dashboard UI and health check endpoints
        if path.startswith("/dashboard") or path.startswith("/health") or path == "/":
            return await call_next(request)

        client_host = request.client.host if request.client else "127.0.0.1"

        if not self.guard.is_allowed(client_host):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": f"Access forbidden: Client IP '{client_host}' is not in allowed subnets."
                }
            )

        return await call_next(request)

