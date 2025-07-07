"""
WebRTC Proxy endpoints - Proxy para comunicação com WebRTC Server
Resolve problemas de CORS e comunicação entre containers
"""

import os
import aiohttp
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from loguru import logger

router = APIRouter()

# URL do WebRTC Server - usar localhost para bridge network
WEBRTC_SERVER_URL = os.environ.get('WEBRTC_SERVER_URL', 'http://localhost:8080')
print(f"[CONFIG] WebRTC Proxy configurado para: {WEBRTC_SERVER_URL}")  # Debug


@router.post("/offer")
async def proxy_webrtc_offer(request: Request):
    """
    Proxy para WebRTC offer - resolve CORS e comunicação entre containers
    """
    try:
        # Obter dados da requisição
        request_data = await request.json()
        
        logger.info(f"[PROCESSING] Proxying WebRTC offer para {WEBRTC_SERVER_URL}")
        
        # Fazer requisição para WebRTC Server
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{WEBRTC_SERVER_URL}/offer",
                json=request_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    logger.info("[OK] WebRTC offer processado com sucesso")
                    return JSONResponse(content=result)
                else:
                    error_text = await response.text()
                    logger.error(f"[ERROR] Erro no WebRTC Server: {response.status} - {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"WebRTC Server error: {error_text}"
                    )
                    
    except aiohttp.ClientError as e:
        logger.error(f"[ERROR] Erro de conexão com WebRTC Server: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to WebRTC Server: {str(e)}"
        )
    except Exception as e:
        logger.error(f"[ERROR] Erro no proxy WebRTC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def proxy_webrtc_health():
    """
    Proxy para health check do WebRTC Server
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{WEBRTC_SERVER_URL}/health") as response:
                if response.status == 200:
                    result = await response.json()
                    return JSONResponse(content=result)
                else:
                    raise HTTPException(
                        status_code=response.status,
                        detail="WebRTC Server unhealthy"
                    )
                    
    except aiohttp.ClientError as e:
        logger.error(f"[ERROR] WebRTC Server não acessível: {e}")
        raise HTTPException(
            status_code=503,
            detail="WebRTC Server unavailable"
        )
    except Exception as e:
        logger.error(f"[ERROR] Erro no health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def proxy_webrtc_status():
    """
    Proxy para status do WebRTC Server
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{WEBRTC_SERVER_URL}/status") as response:
                if response.status == 200:
                    result = await response.json()
                    return JSONResponse(content=result)
                else:
                    raise HTTPException(
                        status_code=response.status,
                        detail="Cannot get WebRTC status"
                    )
                    
    except aiohttp.ClientError as e:
        logger.error(f"[ERROR] WebRTC Server não acessível: {e}")
        raise HTTPException(
            status_code=503,
            detail="WebRTC Server unavailable"
        )
    except Exception as e:
        logger.error(f"[ERROR] Erro ao obter status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test")
async def proxy_webrtc_test():
    """
    Proxy para teste do WebRTC Server
    """
    try:
        logger.info("[TEST] Testando conectividade com WebRTC Server...")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{WEBRTC_SERVER_URL}/test") as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("[OK] WebRTC Server respondeu ao teste!")
                    return JSONResponse(content=result)
                else:
                    error_text = await response.text()
                    logger.error(f"[ERROR] WebRTC Server test failed: {response.status} - {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"WebRTC test failed: {error_text}"
                    )
                    
    except aiohttp.ClientError as e:
        logger.error(f"[ERROR] WebRTC Server não acessível para teste: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"WebRTC Server unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error(f"[ERROR] Erro no teste do WebRTC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug")
async def debug_webrtc_config():
    """
    Debug da configuração WebRTC
    """
    return JSONResponse(content={
        "webrtc_server_url": WEBRTC_SERVER_URL,
        "env_var": os.environ.get('WEBRTC_SERVER_URL', 'NOT_SET'),
        "forced_url": "http://172.21.15.83:8080",
        "timestamp": "2025-06-27T06:37:00"
    })


@router.api_route("/ice-candidate", methods=["POST"])
async def proxy_ice_candidate(request: Request):
    """
    Proxy para ICE candidates (se necessário)
    """
    try:
        request_data = await request.json()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{WEBRTC_SERVER_URL}/ice-candidate",
                json=request_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return JSONResponse(content=result)
                else:
                    error_text = await response.text()
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"WebRTC Server error: {error_text}"
                    )
                    
    except aiohttp.ClientError as e:
        logger.error(f"[ERROR] Erro de conexão com WebRTC Server: {e}")
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to WebRTC Server"
        )
    except Exception as e:
        logger.error(f"[ERROR] Erro no proxy ICE: {e}")
        raise HTTPException(status_code=500, detail=str(e))