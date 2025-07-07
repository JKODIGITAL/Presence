"""
Serviço de Validação Robusta para Câmeras
Implementa validação completa de conectividade, performance e capacidades
"""

import asyncio
import time
import json
import re
import socket
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import cv2
import numpy as np
from loguru import logger

# Importar dependências condicionais
try:
    import aiortc
    from aiortc.contrib.media import MediaPlayer
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False
    logger.warning("aiortc não disponível - funcionalidades WebRTC limitadas")

# GStreamer functionality moved to external worker - no internal dependencies
GST_AVAILABLE = False
Gst = None
logger.info("[PROCESSING] Camera validation em modo distribuído - funcionalidade GStreamer externa")


class CameraValidationResult:
    """Resultado da validação de câmera"""
    
    def __init__(self):
        self.success = False
        self.connection_quality = 0.0
        self.errors = []
        self.warnings = []
        self.metrics = {}
        self.capabilities = {}
        self.suggested_settings = {}
        self.test_duration = 0.0
        
    def add_error(self, error: str, error_type: str = "unknown"):
        """Adicionar erro"""
        self.errors.append({
            "message": error,
            "type": error_type,
            "timestamp": datetime.now()
        })
        
    def add_warning(self, warning: str):
        """Adicionar aviso"""
        self.warnings.append({
            "message": warning,
            "timestamp": datetime.now()
        })
        
    def set_metric(self, key: str, value: Any):
        """Definir métrica"""
        self.metrics[key] = value
        
    def set_capability(self, key: str, value: Any):
        """Definir capacidade"""
        self.capabilities[key] = value
        
    def to_dict(self) -> Dict:
        """Converter para dicionário"""
        return {
            "success": self.success,
            "connection_quality": self.connection_quality,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
            "capabilities": self.capabilities,
            "suggested_settings": self.suggested_settings,
            "test_duration": self.test_duration
        }


class CameraValidationService:
    """Serviço de validação robusta de câmeras"""
    
    def __init__(self):
        self.timeout = 30  # Timeout padrão em segundos
        
    async def validate_camera_comprehensive(
        self, 
        url: str, 
        username: str = None, 
        password: str = None,
        test_type: str = "full"
    ) -> CameraValidationResult:
        """
        Validação completa da câmera
        
        Args:
            url: URL da câmera (RTSP, HTTP, ou device path)
            username: Usuário para autenticação
            password: Senha para autenticação
            test_type: Tipo de teste (basic, full, performance, stress)
        """
        start_time = time.time()
        result = CameraValidationResult()
        
        try:
            logger.info(f"Iniciando validação {test_type} para câmera: {url}")
            
            # 1. Validação básica de formato
            await self._validate_url_format(url, result)
            
            # 2. Teste de conectividade básica
            if result.success or not result.errors:
                await self._test_basic_connectivity(url, username, password, result)
            
            # 3. Testes avançados se básico passou
            if test_type in ["full", "performance", "stress"] and result.success:
                
                # Teste de autenticação
                await self._test_authentication(url, username, password, result)
                
                # Teste de qualidade de stream
                await self._test_stream_quality(url, username, password, result)
                
                # Detecção de capacidades
                await self._detect_capabilities(url, username, password, result)
                
                # Testes de performance específicos
                if test_type in ["performance", "stress"]:
                    await self._test_performance_metrics(url, username, password, result)
                
                # Teste de stress se solicitado
                if test_type == "stress":
                    await self._test_connection_stability(url, username, password, result)
            
            # 4. Calcular qualidade geral da conexão
            self._calculate_connection_quality(result)
            
            # 5. Gerar sugestões de melhoria
            self._generate_suggestions(result)
            
            result.test_duration = time.time() - start_time
            
            logger.info(f"Validação concluída em {result.test_duration:.2f}s - Sucesso: {result.success} - Qualidade: {result.connection_quality:.2f}")
            
        except Exception as e:
            result.add_error(f"Erro inesperado durante validação: {str(e)}", "unexpected_error")
            logger.error(f"Erro na validação: {e}")
            
        return result
    
    async def _validate_url_format(self, url: str, result: CameraValidationResult):
        """Validar formato da URL"""
        try:
            # URLs RTSP
            if url.startswith('rtsp://'):
                parsed = urlparse(url)
                if not parsed.hostname:
                    result.add_error("URL RTSP inválida: hostname não encontrado", "invalid_url")
                    return
                    
                result.set_capability("protocol", "rtsp")
                result.set_capability("hostname", parsed.hostname)
                result.set_capability("port", parsed.port or 554)
                
            # URLs HTTP (para câmeras IP com stream HTTP)
            elif url.startswith('http://') or url.startswith('https://'):
                parsed = urlparse(url)
                if not parsed.hostname:
                    result.add_error("URL HTTP inválida: hostname não encontrado", "invalid_url")
                    return
                    
                result.set_capability("protocol", "http")
                result.set_capability("hostname", parsed.hostname)
                result.set_capability("port", parsed.port or 80)
                
            # Device paths (/dev/video0, etc.)
            elif url.startswith('/dev/video'):
                try:
                    device_num = int(url.split('video')[1])
                    result.set_capability("protocol", "v4l2")
                    result.set_capability("device_number", device_num)
                except:
                    result.add_error("Device path inválido", "invalid_device_path")
                    return
                    
            # Índices numéricos (0, 1, 2, etc.)
            elif url.isdigit():
                result.set_capability("protocol", "index")
                result.set_capability("device_index", int(url))
                
            else:
                result.add_error(f"Formato de URL não suportado: {url}", "unsupported_url_format")
                return
                
            result.success = True
            logger.debug(f"Formato de URL válido: {url}")
            
        except Exception as e:
            result.add_error(f"Erro ao validar formato da URL: {str(e)}", "url_validation_error")
    
    async def _test_basic_connectivity(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste básico de conectividade"""
        try:
            logger.debug(f"Testando conectividade básica para: {url}")
            
            if url.startswith('rtsp://'):
                await self._test_rtsp_connectivity(url, username, password, result)
            elif url.startswith('http'):
                await self._test_http_connectivity(url, username, password, result)
            elif url.startswith('/dev/video') or url.isdigit():
                await self._test_v4l2_connectivity(url, result)
            else:
                result.add_error("Protocolo não suportado para teste de conectividade", "unsupported_protocol")
                
        except Exception as e:
            result.add_error(f"Erro no teste de conectividade: {str(e)}", "connectivity_error")
    
    async def _test_rtsp_connectivity(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste específico para conectividade RTSP"""
        try:
            # Construir URL com credenciais se fornecidas
            test_url = url
            if username and password:
                parsed = urlparse(url)
                auth_url = f"{parsed.scheme}://{username}:{password}@{parsed.netloc}{parsed.path}"
                if parsed.query:
                    auth_url += f"?{parsed.query}"
                test_url = auth_url
            
            start_time = time.time()
            
            # Teste usando OpenCV (mais compatível)
            cap = cv2.VideoCapture(test_url)
            
            if not cap.isOpened():
                result.add_error("Não foi possível abrir stream RTSP", "rtsp_connection_failed")
                return
            
            # Tentar ler um frame
            ret, frame = cap.read()
            connection_time = (time.time() - start_time) * 1000
            
            if ret and frame is not None:
                result.success = True
                result.set_metric("connection_time_ms", connection_time)
                result.set_metric("first_frame_received", True)
                result.set_metric("frame_shape", frame.shape)
                
                # Detectar resolução real
                height, width = frame.shape[:2]
                result.set_capability("actual_resolution", {"width": width, "height": height})
                
                logger.debug(f"RTSP conectado com sucesso: {width}x{height}")
            else:
                result.add_error("Stream RTSP aberto mas nenhum frame recebido", "no_frames_received")
            
            cap.release()
            
        except Exception as e:
            result.add_error(f"Erro ao testar RTSP: {str(e)}", "rtsp_test_error")
    
    async def _test_http_connectivity(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste específico para conectividade HTTP"""
        try:
            import requests
            from requests.auth import HTTPBasicAuth
            
            start_time = time.time()
            
            # Configurar autenticação se fornecida
            auth = None
            if username and password:
                auth = HTTPBasicAuth(username, password)
            
            # Fazer requisição HEAD primeiro para verificar se o endpoint existe
            response = requests.head(url, auth=auth, timeout=self.timeout)
            
            if response.status_code == 200:
                # Tentar obter alguns bytes do stream
                response = requests.get(url, auth=auth, timeout=self.timeout, stream=True)
                
                # Ler primeiros bytes para verificar se é um stream válido
                chunk = next(response.iter_content(chunk_size=1024))
                connection_time = (time.time() - start_time) * 1000
                
                if chunk:
                    result.success = True
                    result.set_metric("connection_time_ms", connection_time)
                    result.set_metric("http_status_code", response.status_code)
                    result.set_metric("content_type", response.headers.get('content-type'))
                    
                    logger.debug(f"HTTP stream conectado com sucesso")
                else:
                    result.add_error("Stream HTTP sem conteúdo", "empty_http_stream")
            else:
                result.add_error(f"Erro HTTP: {response.status_code}", "http_error")
                
        except Exception as e:
            result.add_error(f"Erro ao testar HTTP: {str(e)}", "http_test_error")
    
    async def _test_v4l2_connectivity(self, url: str, result: CameraValidationResult):
        """Teste específico para dispositivos V4L2 (Linux)"""
        try:
            # Converter para índice se necessário
            if url.startswith('/dev/video'):
                device_index = int(url.split('video')[1])
            else:
                device_index = int(url)
            
            start_time = time.time()
            
            # Testar com OpenCV
            cap = cv2.VideoCapture(device_index)
            
            if not cap.isOpened():
                result.add_error(f"Dispositivo de vídeo {device_index} não encontrado", "device_not_found")
                return
            
            # Tentar ler um frame
            ret, frame = cap.read()
            connection_time = (time.time() - start_time) * 1000
            
            if ret and frame is not None:
                result.success = True
                result.set_metric("connection_time_ms", connection_time)
                result.set_metric("device_index", device_index)
                
                # Detectar resolução
                height, width = frame.shape[:2]
                result.set_capability("actual_resolution", {"width": width, "height": height})
                
                # Detectar FPS
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps > 0:
                    result.set_capability("fps", fps)
                
                logger.debug(f"Dispositivo V4L2 conectado: {width}x{height}@{fps}fps")
            else:
                result.add_error("Dispositivo aberto mas nenhum frame recebido", "no_frames_received")
            
            cap.release()
            
        except Exception as e:
            result.add_error(f"Erro ao testar V4L2: {str(e)}", "v4l2_test_error")
    
    async def _test_authentication(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste específico de autenticação"""
        try:
            if not username or not password:
                result.add_warning("Credenciais não fornecidas - teste de autenticação pulado")
                return
                
            logger.debug("Testando autenticação...")
            
            # Testar com credenciais corretas
            correct_result = await self._test_credentials(url, username, password)
            
            # Testar com credenciais incorretas para verificar se a autenticação está funcionando
            wrong_result = await self._test_credentials(url, "wrong_user", "wrong_pass")
            
            if correct_result and not wrong_result:
                result.set_capability("authentication_working", True)
                logger.debug("Autenticação funcionando corretamente")
            elif correct_result and wrong_result:
                result.add_warning("Câmera não parece exigir autenticação")
                result.set_capability("authentication_required", False)
            else:
                result.add_error("Falha na autenticação com credenciais fornecidas", "auth_failed")
                
        except Exception as e:
            result.add_error(f"Erro ao testar autenticação: {str(e)}", "auth_test_error")
    
    async def _test_credentials(self, url: str, username: str, password: str) -> bool:
        """Teste rápido de credenciais"""
        try:
            if url.startswith('rtsp://'):
                parsed = urlparse(url)
                test_url = f"{parsed.scheme}://{username}:{password}@{parsed.netloc}{parsed.path}"
                if parsed.query:
                    test_url += f"?{parsed.query}"
                
                cap = cv2.VideoCapture(test_url)
                if cap.isOpened():
                    ret, _ = cap.read()
                    cap.release()
                    return ret
                    
            return False
            
        except:
            return False
    
    async def _test_stream_quality(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste de qualidade do stream"""
        try:
            logger.debug("Testando qualidade do stream...")
            
            # Construir URL com autenticação
            test_url = self._build_authenticated_url(url, username, password)
            
            cap = cv2.VideoCapture(test_url)
            if not cap.isOpened():
                result.add_error("Não foi possível abrir stream para teste de qualidade", "stream_quality_test_failed")
                return
            
            frames_to_test = 30  # Testar 30 frames
            frames_received = 0
            start_time = time.time()
            
            frame_qualities = []
            
            for i in range(frames_to_test):
                ret, frame = cap.read()
                if ret and frame is not None:
                    frames_received += 1
                    
                    # Calcular qualidade do frame (usando variância - maior variância = mais detalhes)
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    quality = np.var(gray)
                    frame_qualities.append(quality)
                
                # Pequena pausa para simular FPS real
                await asyncio.sleep(0.033)  # ~30 FPS
            
            test_duration = time.time() - start_time
            cap.release()
            
            if frames_received > 0:
                # Calcular métricas
                fps_measured = frames_received / test_duration
                avg_quality = np.mean(frame_qualities) if frame_qualities else 0
                quality_std = np.std(frame_qualities) if frame_qualities else 0
                
                result.set_metric("frames_received", frames_received)
                result.set_metric("frames_expected", frames_to_test)
                result.set_metric("fps_measured", fps_measured)
                result.set_metric("avg_frame_quality", avg_quality)
                result.set_metric("quality_stability", 1.0 - (quality_std / avg_quality) if avg_quality > 0 else 0)
                result.set_metric("frame_drop_rate", (frames_to_test - frames_received) / frames_to_test)
                
                logger.debug(f"Qualidade do stream: {frames_received}/{frames_to_test} frames, {fps_measured:.1f} FPS")
            else:
                result.add_error("Nenhum frame recebido durante teste de qualidade", "no_quality_frames")
                
        except Exception as e:
            result.add_error(f"Erro ao testar qualidade do stream: {str(e)}", "stream_quality_error")
    
    async def _detect_capabilities(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Detectar capacidades da câmera"""
        try:
            logger.debug("Detectando capacidades da câmera...")
            
            # Construir URL com autenticação
            test_url = self._build_authenticated_url(url, username, password)
            
            cap = cv2.VideoCapture(test_url)
            if not cap.isOpened():
                result.add_warning("Não foi possível detectar capacidades - stream não acessível")
                return
            
            # Detectar capacidades do OpenCV
            capabilities = {}
            
            # Propriedades de vídeo
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            if width > 0 and height > 0:
                capabilities["max_resolution"] = {"width": int(width), "height": int(height)}
            
            if fps > 0:
                capabilities["max_fps"] = fps
            
            # Tentar detectar se suporta diferentes resoluções
            original_width = width
            original_height = height
            
            # Testar algumas resoluções comuns
            test_resolutions = [
                (1920, 1080), (1280, 720), (640, 480), (320, 240)
            ]
            
            supported_resolutions = []
            for test_w, test_h in test_resolutions:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, test_w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, test_h)
                
                actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                
                if abs(actual_w - test_w) < 10 and abs(actual_h - test_h) < 10:
                    supported_resolutions.append({"width": int(actual_w), "height": int(actual_h)})
            
            if supported_resolutions:
                capabilities["supported_resolutions"] = supported_resolutions
            
            # Restaurar resolução original
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, original_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, original_height)
            
            # Detectar se tem controles (se disponível)
            try:
                brightness = cap.get(cv2.CAP_PROP_BRIGHTNESS)
                contrast = cap.get(cv2.CAP_PROP_CONTRAST)
                saturation = cap.get(cv2.CAP_PROP_SATURATION)
                
                controls = {}
                if brightness >= 0:
                    controls["brightness"] = True
                if contrast >= 0:
                    controls["contrast"] = True
                if saturation >= 0:
                    controls["saturation"] = True
                
                if controls:
                    capabilities["image_controls"] = controls
                    
            except:
                pass  # Controles não disponíveis
            
            result.capabilities.update(capabilities)
            cap.release()
            
            logger.debug(f"Capacidades detectadas: {len(capabilities)} propriedades")
            
        except Exception as e:
            result.add_error(f"Erro ao detectar capacidades: {str(e)}", "capability_detection_error")
    
    async def _test_performance_metrics(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste de métricas de performance"""
        try:
            logger.debug("Testando métricas de performance...")
            
            test_url = self._build_authenticated_url(url, username, password)
            
            cap = cv2.VideoCapture(test_url)
            if not cap.isOpened():
                result.add_error("Não foi possível realizar teste de performance", "performance_test_failed")
                return
            
            # Teste de latência (tempo entre requisição e frame)
            latencies = []
            frame_times = []
            
            for i in range(10):  # 10 medições de latência
                start = time.time()
                ret, frame = cap.read()
                end = time.time()
                
                if ret:
                    latency = (end - start) * 1000  # em millisegundos
                    latencies.append(latency)
                    frame_times.append(end - start)
                
                await asyncio.sleep(0.1)  # Pausa entre medições
            
            cap.release()
            
            if latencies:
                avg_latency = np.mean(latencies)
                max_latency = np.max(latencies)
                min_latency = np.min(latencies)
                jitter = np.std(latencies)
                
                result.set_metric("avg_latency_ms", avg_latency)
                result.set_metric("max_latency_ms", max_latency)
                result.set_metric("min_latency_ms", min_latency)
                result.set_metric("jitter_ms", jitter)
                
                # Calcular qualidade baseada na latência
                if avg_latency < 100:
                    latency_quality = 1.0
                elif avg_latency < 500:
                    latency_quality = 0.8
                elif avg_latency < 1000:
                    latency_quality = 0.6
                else:
                    latency_quality = 0.3
                
                result.set_metric("latency_quality", latency_quality)
                
                logger.debug(f"Performance: latência média {avg_latency:.1f}ms, jitter {jitter:.1f}ms")
            else:
                result.add_error("Não foi possível medir latência", "latency_measurement_failed")
                
        except Exception as e:
            result.add_error(f"Erro ao testar performance: {str(e)}", "performance_test_error")
    
    async def _test_connection_stability(self, url: str, username: str, password: str, result: CameraValidationResult):
        """Teste de estabilidade da conexão (stress test)"""
        try:
            logger.debug("Testando estabilidade da conexão...")
            
            test_url = self._build_authenticated_url(url, username, password)
            test_duration = 60  # 1 minuto de teste
            
            connections_successful = 0
            connections_failed = 0
            total_frames = 0
            
            start_time = time.time()
            
            while (time.time() - start_time) < test_duration:
                try:
                    cap = cv2.VideoCapture(test_url)
                    
                    if cap.isOpened():
                        connections_successful += 1
                        
                        # Ler alguns frames
                        frames_in_session = 0
                        session_start = time.time()
                        
                        while (time.time() - session_start) < 5 and (time.time() - start_time) < test_duration:
                            ret, frame = cap.read()
                            if ret:
                                frames_in_session += 1
                                total_frames += 1
                            await asyncio.sleep(0.033)  # ~30 FPS
                    else:
                        connections_failed += 1
                    
                    cap.release()
                    
                    # Pausa entre reconexões
                    await asyncio.sleep(2)
                    
                except Exception as session_error:
                    connections_failed += 1
                    logger.debug(f"Falha na sessão de estabilidade: {session_error}")
            
            total_connections = connections_successful + connections_failed
            stability_rate = connections_successful / total_connections if total_connections > 0 else 0
            
            result.set_metric("stability_test_duration", test_duration)
            result.set_metric("connections_attempted", total_connections)
            result.set_metric("connections_successful", connections_successful)
            result.set_metric("connections_failed", connections_failed)
            result.set_metric("stability_rate", stability_rate)
            result.set_metric("total_frames_stability_test", total_frames)
            
            if stability_rate >= 0.9:
                result.set_metric("stability_quality", "excellent")
            elif stability_rate >= 0.7:
                result.set_metric("stability_quality", "good")
            elif stability_rate >= 0.5:
                result.set_metric("stability_quality", "fair")
            else:
                result.set_metric("stability_quality", "poor")
                result.add_warning(f"Estabilidade baixa: {stability_rate:.1%} de conexões bem-sucedidas")
            
            logger.debug(f"Estabilidade: {connections_successful}/{total_connections} conexões bem-sucedidas")
            
        except Exception as e:
            result.add_error(f"Erro ao testar estabilidade: {str(e)}", "stability_test_error")
    
    def _build_authenticated_url(self, url: str, username: str, password: str) -> str:
        """Construir URL com autenticação"""
        if not username or not password:
            return url
            
        if url.startswith('rtsp://'):
            parsed = urlparse(url)
            auth_url = f"{parsed.scheme}://{username}:{password}@{parsed.netloc}{parsed.path}"
            if parsed.query:
                auth_url += f"?{parsed.query}"
            return auth_url
            
        return url
    
    def _calculate_connection_quality(self, result: CameraValidationResult):
        """Calcular qualidade geral da conexão"""
        try:
            if not result.success:
                result.connection_quality = 0.0
                return
            
            quality_factors = []
            
            # Fator de conectividade básica
            if result.success:
                quality_factors.append(0.4)  # 40% por conectar
            
            # Fator de latência
            if "latency_quality" in result.metrics:
                quality_factors.append(result.metrics["latency_quality"] * 0.2)  # 20%
            
            # Fator de estabilidade de frame
            if "quality_stability" in result.metrics:
                quality_factors.append(result.metrics["quality_stability"] * 0.2)  # 20%
            
            # Fator de taxa de perda de frames
            if "frame_drop_rate" in result.metrics:
                drop_quality = 1.0 - result.metrics["frame_drop_rate"]
                quality_factors.append(drop_quality * 0.1)  # 10%
            
            # Fator de estabilidade de conexão
            if "stability_rate" in result.metrics:
                quality_factors.append(result.metrics["stability_rate"] * 0.1)  # 10%
            
            # Calcular qualidade final
            if quality_factors:
                result.connection_quality = sum(quality_factors)
            else:
                result.connection_quality = 0.5  # Qualidade média se não temos métricas
            
            # Ajustar baseado em erros e avisos
            error_penalty = len(result.errors) * 0.1
            warning_penalty = len(result.warnings) * 0.05
            
            result.connection_quality = max(0.0, result.connection_quality - error_penalty - warning_penalty)
            result.connection_quality = min(1.0, result.connection_quality)
            
        except Exception as e:
            logger.error(f"Erro ao calcular qualidade da conexão: {e}")
            result.connection_quality = 0.5
    
    def _generate_suggestions(self, result: CameraValidationResult):
        """Gerar sugestões de melhoria"""
        try:
            suggestions = {}
            
            # Sugestões baseadas em latência
            if "avg_latency_ms" in result.metrics:
                latency = result.metrics["avg_latency_ms"]
                if latency > 500:
                    suggestions["network"] = [
                        "Considere usar conexão TCP em vez de UDP para RTSP",
                        "Verifique a qualidade da rede entre o servidor e a câmera",
                        "Considere reduzir a resolução ou FPS para melhorar a latência"
                    ]
            
            # Sugestões baseadas em taxa de perda de frames
            if "frame_drop_rate" in result.metrics:
                drop_rate = result.metrics["frame_drop_rate"]
                if drop_rate > 0.1:  # Mais de 10% de perda
                    suggestions["performance"] = [
                        "Taxa alta de perda de frames detectada",
                        "Considere reduzir o FPS configurado",
                        "Verifique se o hardware do servidor suporta a carga",
                        "Considere usar um buffer maior para o stream"
                    ]
            
            # Sugestões baseadas em estabilidade
            if "stability_rate" in result.metrics:
                stability = result.metrics["stability_rate"]
                if stability < 0.8:
                    suggestions["stability"] = [
                        "Conexão instável detectada",
                        "Habilite reconexão automática",
                        "Verifique a alimentação da câmera",
                        "Considere usar configuração de timeout mais alta"
                    ]
            
            # Sugestões baseadas em erros
            for error in result.errors:
                error_type = error.get("type", "unknown")
                
                if error_type == "auth_failed":
                    suggestions["authentication"] = [
                        "Verifique se as credenciais estão corretas",
                        "Confirme se a câmera requer autenticação",
                        "Teste as credenciais diretamente na interface da câmera"
                    ]
                elif error_type == "rtsp_connection_failed":
                    suggestions["rtsp"] = [
                        "Verifique se a porta RTSP (554) está acessível",
                        "Confirme se o protocolo RTSP está habilitado na câmera",
                        "Teste a conectividade de rede com ping",
                        "Verifique configurações de firewall"
                    ]
                elif error_type == "no_frames_received":
                    suggestions["streaming"] = [
                        "Câmera conecta mas não envia frames",
                        "Verifique se o codec é suportado",
                        "Confirme se o caminho do stream está correto",
                        "Teste com software cliente RTSP externo"
                    ]
            
            # Sugestões para otimização
            if result.connection_quality > 0.8:
                suggestions["optimization"] = [
                    "Ótima qualidade de conexão!",
                    "Considere habilitar gravação ou análise avançada",
                    "A câmera está pronta para uso em produção"
                ]
            elif result.connection_quality > 0.6:
                suggestions["optimization"] = [
                    "Boa qualidade de conexão",
                    "Considere ajustes finos para melhorar performance",
                    "Monitor regularmente para manter a qualidade"
                ]
            else:
                suggestions["optimization"] = [
                    "Qualidade de conexão pode ser melhorada",
                    "Revise configurações de rede e câmera",
                    "Considere trocar equipamento se problemas persistirem"
                ]
            
            result.suggested_settings = suggestions
            
        except Exception as e:
            logger.error(f"Erro ao gerar sugestões: {e}")


# Instância global do serviço
camera_validation_service = CameraValidationService()