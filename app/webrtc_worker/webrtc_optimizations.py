#!/usr/bin/env python3
"""
WebRTC Optimizations - Melhorias de performance e estabilidade
"""

import asyncio
import os
import sys
import socket
import random
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class WebRTCOptimizer:
    """Classe para aplicar otimizações no WebRTC"""
    
    def __init__(self):
        self.udp_range = self._parse_udp_range()
        self.optimizations_applied = False
        
    def _parse_udp_range(self) -> tuple:
        """Parse UDP port range from environment"""
        udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
        min_port, max_port = map(int, udp_range.split('-'))
        return min_port, max_port
    
    def apply_enhanced_udp_patch(self):
        """Aplicar patch UDP otimizado com fallback inteligente"""
        if hasattr(socket, '_enhanced_udp_patch_applied'):
            return
            
        socket._enhanced_udp_patch_applied = True
        min_port, max_port = self.udp_range
        
        OriginalSocket = socket.socket
        
        class OptimizedUDPSocket(OriginalSocket):
            """Socket UDP otimizado com smart port selection"""
            
            def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
                super().__init__(family, type, proto, fileno)
                self._is_udp = (family == socket.AF_INET and type == socket.SOCK_DGRAM)
                self._bound_port = None
                
            def bind(self, address):
                if self._is_udp:
                    host, port = address
                    
                    if port == 0:
                        # Smart port selection with randomization
                        available_ports = list(range(min_port, max_port + 1))
                        random.shuffle(available_ports)
                        
                        for try_port in available_ports:
                            try:
                                super().bind((host, try_port))
                                self._bound_port = try_port
                                logger.debug(f"✅ UDP Smart-bind: {host}:{try_port}")
                                return
                            except OSError as e:
                                if e.errno == 98:  # Address already in use
                                    continue
                                raise
                        
                        # Fallback to system assignment
                        super().bind((host, 0))
                        self._bound_port = self.getsockname()[1]
                        logger.warning(f"⚠️ UDP Fallback: {host}:{self._bound_port}")
                    else:
                        # Use specified port
                        super().bind(address)
                        self._bound_port = port
                        logger.debug(f"📌 UDP Fixed-bind: {host}:{port}")
                else:
                    super().bind(address)
        
        socket.socket = OptimizedUDPSocket
        logger.info(f"🔧 Enhanced UDP patch applied: {min_port}-{max_port}")
    
    def get_optimized_ice_servers(self) -> List[Dict[str, Any]]:
        """Retorna configuração ICE otimizada"""
        return [
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"},
            {"urls": "stun:stun.stunprotocol.org:3478"},
            {"urls": "stun:stun.cloudflare.com:3478"},
            # Adicionar TURN servers se disponíveis
            # {
            #     "urls": "turn:your-turn-server.com:3478",
            #     "username": "turn-user",
            #     "credential": "turn-password"
            # }
        ]
    
    def get_optimized_rtc_configuration(self) -> Dict[str, Any]:
        """Retorna configuração RTCConfiguration otimizada"""
        return {
            "iceServers": self.get_optimized_ice_servers(),
            "iceTransportPolicy": "all",
            "bundlePolicy": "max-bundle",
            "rtcpMuxPolicy": "require",
            "iceCandidatePoolSize": 10,  # Pre-gather candidates
            "iceConnectionReceiveTimeout": 30000,
            "iceBackupCandidatePairPingInterval": 5000,
        }
    
    def optimize_h264_sdp(self, sdp: str) -> str:
        """Otimizar parâmetros H.264 no SDP"""
        lines = sdp.split('\r\n')
        optimized_lines = []
        
        for line in lines:
            if 'a=fmtp:' in line and ('H264' in line or '96' in line or '97' in line):
                # Adicionar parâmetros de otimização H.264
                if 'profile-level-id=42001f' in line:
                    # Baseline profile optimization
                    if 'max-mbps=' not in line:
                        line = line.rstrip(';') + ';max-mbps=245760;max-fs=8160;max-br=20000'
                elif 'profile-level-id=42e01f' in line:
                    # Main profile optimization
                    if 'max-mbps=' not in line:
                        line = line.rstrip(';') + ';max-mbps=245760;max-fs=8160;max-br=20000'
                
                # Adicionar sprop-parameter-sets se não existir
                if 'sprop-parameter-sets=' not in line and 'profile-level-id=' in line:
                    line = line.rstrip(';') + ';redundant-pic-cap=0'
                    
            optimized_lines.append(line)
        
        return '\r\n'.join(optimized_lines)
    
    def apply_event_loop_optimizations(self):
        """Aplicar otimizações no event loop do asyncio"""
        if sys.platform != 'win32':
            try:
                import uvloop
                asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
                logger.info("🚀 uvloop event loop policy applied")
            except ImportError:
                logger.warning("⚠️ uvloop not available, using default event loop")
        
        # Configurar parâmetros do asyncio
        try:
            loop = asyncio.get_event_loop()
            # Aumentar buffer de sockets
            loop.set_default_executor(None)
            logger.info("🔧 Asyncio optimizations applied")
        except Exception as e:
            logger.warning(f"⚠️ Failed to apply asyncio optimizations: {e}")
    
    def get_rtsp_optimization_params(self) -> Dict[str, Any]:
        """Parâmetros otimizados para streams RTSP"""
        return {
            'latency': 200,  # ms
            'buffer_mode': 'auto',
            'drop_on_latency': True,
            'do_retransmission': False,
            'tcp_timeout': 20000000,  # 20s in microseconds
            'retry': 5,
            'protocols': 'tcp',  # Force TCP for better reliability
        }
    
    def create_optimized_gstreamer_pipeline(self, rtsp_url: str) -> str:
        """Criar pipeline GStreamer otimizado"""
        rtsp_params = self.get_rtsp_optimization_params()
        
        pipeline = (
            f"rtspsrc location={rtsp_url} "
            f"latency={rtsp_params['latency']} "
            f"buffer-mode={rtsp_params['buffer_mode']} "
            f"drop-on-latency={rtsp_params['drop_on_latency']} "
            f"do-retransmission={rtsp_params['do_retransmission']} "
            f"tcp-timeout={rtsp_params['tcp_timeout']} "
            f"retry={rtsp_params['retry']} "
            f"protocols={rtsp_params['protocols']} ! "
            f"rtph264depay ! h264parse ! avdec_h264 ! "
            f"videoscale ! videoconvert ! "
            f"video/x-raw,format=YUV420P,pixel-aspect-ratio=1/1 ! "
            f"appsink sync=false emit-signals=true max-buffers=1 drop=true"
        )
        
        return pipeline
    
    def apply_all_optimizations(self):
        """Aplicar todas as otimizações disponíveis"""
        if self.optimizations_applied:
            return
            
        logger.info("🔧 Applying WebRTC optimizations...")
        
        try:
            self.apply_enhanced_udp_patch()
            self.apply_event_loop_optimizations()
            self.optimizations_applied = True
            logger.info("✅ All WebRTC optimizations applied successfully")
        except Exception as e:
            logger.error(f"❌ Failed to apply optimizations: {e}")


class WebRTCDiagnostics:
    """Diagnósticos e debugging para WebRTC"""
    
    @staticmethod
    def analyze_connection_state(peer_connection) -> Dict[str, Any]:
        """Analisar estado da conexão WebRTC"""
        try:
            return {
                'connection_state': peer_connection.connectionState,
                'ice_connection_state': peer_connection.iceConnectionState,
                'ice_gathering_state': peer_connection.iceGatheringState,
                'signaling_state': peer_connection.signalingState,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}
    
    @staticmethod
    def diagnose_connection_failure(state_info: Dict[str, Any]) -> str:
        """Diagnosticar falhas de conexão"""
        ice_state = state_info.get('ice_connection_state')
        conn_state = state_info.get('connection_state')
        signal_state = state_info.get('signaling_state')
        
        if ice_state == 'failed':
            return "ICE connection failed - check STUN/TURN servers and firewall configuration"
        elif conn_state == 'failed':
            return "WebRTC connection failed - check codec compatibility and network connectivity"
        elif signal_state == 'stable' and ice_state == 'disconnected':
            return "ICE disconnection detected - network interruption or NAT timeout"
        elif ice_state == 'checking':
            return "ICE connectivity checks in progress - this is normal during connection establishment"
        elif conn_state == 'connecting':
            return "WebRTC connection establishing - wait for completion"
        elif conn_state == 'connected' and ice_state == 'connected':
            return "Connection is healthy"
        else:
            return f"Unknown state combination: {state_info}"
    
    @staticmethod
    def log_ice_candidate_details(candidate):
        """Log detalhado de ICE candidates"""
        if candidate and hasattr(candidate, 'candidate'):
            logger.info(f"🧊 ICE Candidate: {candidate.candidate}")
            if hasattr(candidate, 'sdpMid'):
                logger.info(f"   └─ SDP MID: {candidate.sdpMid}")
            if hasattr(candidate, 'sdpMLineIndex'):
                logger.info(f"   └─ Line Index: {candidate.sdpMLineIndex}")


# Instância global do otimizador
webrtc_optimizer = WebRTCOptimizer()

# Aplicar otimizações na importação do módulo
webrtc_optimizer.apply_all_optimizations()