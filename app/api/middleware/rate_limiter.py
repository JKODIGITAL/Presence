"""
Rate limiting middleware para API
"""

import time
from collections import defaultdict, deque
from fastapi import Request, HTTPException
from typing import Dict, Deque


class RateLimiter:
    """Rate limiter simples em memória"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, Deque[float]] = defaultdict(deque)
    
    def is_allowed(self, key: str) -> bool:
        """Verificar se a requisição é permitida"""
        now = time.time()
        
        # Limpar requisições antigas
        while self.requests[key] and now - self.requests[key][0] > self.window_seconds:
            self.requests[key].popleft()
        
        # Verificar limite
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # Adicionar nova requisição
        self.requests[key].append(now)
        return True
    
    def get_remaining_requests(self, key: str) -> int:
        """Obter número de requisições restantes"""
        return max(0, self.max_requests - len(self.requests[key]))


# Instância global do rate limiter (LAN otimizado)
snapshot_rate_limiter = RateLimiter(max_requests=300, window_seconds=60)  # 300 snapshots por minuto (LAN)
general_rate_limiter = RateLimiter(max_requests=5000, window_seconds=60)  # 5000 requisições por minuto (LAN)


async def rate_limit_middleware(request: Request, call_next):
    """Middleware de rate limiting"""
    client_ip = request.client.host
    
    # Rate limiting específico para snapshots
    if "/snapshot" in request.url.path:
        if not snapshot_rate_limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded for snapshots. Max 30 requests per minute."
            )
    else:
        # Rate limiting geral
        if not general_rate_limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Max 1000 requests per minute."
            )
    
    response = await call_next(request)
    return response