"""
GStreamer Camera Implementation - Solução robusta e otimizada para câmeras IP
"""

import cv2
import numpy as np
import asyncio
import time
import threading
import platform
import os
from typing import Optional, Callable, Dict, Any
from loguru import logger
import queue
import weakref
import sys
import json
import logging
# Importação compatível do GStreamer (MSYS2 + Conda)
try:
    # Tentar módulo centralizado primeiro (Conda)
    from app.core.gstreamer_init import initialize_gstreamer, safe_import_gstreamer
    
    initialize_gstreamer()
    Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error = safe_import_gstreamer()
    
    if not GSTREAMER_AVAILABLE:
        logger.warning(f"GStreamer módulo centralizado falhou: {gstreamer_error}")
    else:
        logger.info("GStreamer importado via módulo centralizado")
        
except ImportError:
    # Fallback para módulo simplificado (MSYS2)
    try:
        from app.camera_worker.simple_gstreamer_init import (
            initialize_gstreamer, safe_import_gstreamer, 
            Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error
        )
        logger.info("GStreamer importado via módulo simplificado (MSYS2)")
        
    except ImportError as e:
        logger.error(f"Erro ao importar GStreamer (ambos os módulos falharam): {e}")
        GSTREAMER_AVAILABLE = False
        Gst = None
        GstApp = None
        GLib = None
        gstreamer_error = str(e)

class GStreamerService:
    """Serviço singleton para gerenciar inicialização do GStreamer"""
    _instance = None
    _initialized = False
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.gstreamer_available = GSTREAMER_AVAILABLE  # Usar uma cópia local
        if not self._initialized and self.gstreamer_available:
            with self._lock:
                if not self._initialized:
                    try:
                        # Verificar se o GStreamer já está inicializado
                        if not Gst.is_initialized():
                            Gst.init(None)
                            
                        if Gst.is_initialized():
                            logger.info(f"GStreamer inicializado com sucesso no serviço: {Gst.version_string()}")
                            self._initialized = True
                        else:
                            logger.error("GStreamer não foi inicializado corretamente no serviço")
                            self._initialized = False
                            self.gstreamer_available = False
                    except Exception as e:
                        logger.error(f"Erro ao inicializar GStreamer no serviço: {e}")
                        self._initialized = False
                        self.gstreamer_available = False
        elif not self.gstreamer_available:
            logger.warning("GStreamer não disponível - usando fallback")
            self._initialized = False
    
    def is_initialized(self) -> bool:
        """Verificar se o GStreamer está inicializado"""
        if not self.gstreamer_available:
            return False
            
        try:
            return self._initialized and Gst.is_initialized()
        except Exception:
            return False
            
    def get_version(self) -> str:
        """Obter versão do GStreamer"""
        if not self.is_initialized():
            return "N/A"
            
        try:
            return Gst.version_string()
        except Exception:
            return "Desconhecida"
            
    def check_plugin(self, element_name: str) -> bool:
        """Verificar se um elemento específico está disponível"""
        if not self.is_initialized():
            return False
            
        try:
            registry = Gst.Registry.get()
            element = registry.find_feature(element_name, Gst.ElementFactory.__gtype__)
            return element is not None
        except Exception as e:
            logger.error(f"Erro ao verificar elemento {element_name}: {e}")
            return False

# Instância global do serviço GStreamer
gstreamer_service = GStreamerService()

class GStreamerCamera:
    """Implementação otimizada de câmera usando GStreamer"""
    
    def __init__(self, camera_id: str, camera_config: dict):
        self.camera_id = camera_id
        self.camera_config = camera_config.copy()  # Fazer cópia para não modificar o original
        self.is_running = False
        self.is_initialized = False
        self.gstreamer_available = GSTREAMER_AVAILABLE  # Usar uma cópia local
        
        # Definir configurações padrão para câmeras de alta resolução
        if 'buffer_size' not in self.camera_config:
            self.camera_config['buffer_size'] = 5  # 5MB de buffer UDP por padrão
        if 'max_buffers' not in self.camera_config:
            self.camera_config['max_buffers'] = 3  # 3 buffers para o appsink
        if 'latency' not in self.camera_config:
            self.camera_config['latency'] = 100  # 100ms de latência por padrão
        
        # Thread safety
        self.frame_lock = threading.Lock()
        self.state_lock = threading.Lock()
        
        # Frame management
        self.frame_queue = queue.Queue(maxsize=5)  # Buffer reduzido
        self.latest_frame = None
        self.frame_callback = None
        
        # GStreamer components
        self.pipeline = None
        self.appsink = None
        self.main_loop = None
        self.gst_thread = None
        self.bus_watch_id = None
        
        # Connection management
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 2
        self.connection_timeout = 60  # Timeout aumentado para 60 segundos
        
        # Statistics
        self.stats = {
            'frames_received': 0,
            'frames_processed': 0,
            'errors': 0,
            'reconnections': 0,
            'last_frame_time': None,
            'pipeline_state': 'NULL'
        }
        
        # Ensure GStreamer is initialized
        if not self.gstreamer_available:
            logger.error("GStreamer não disponível - câmera não pode ser inicializada")
            return
        
        gstreamer_service.is_initialized()
    
    def _fix_rtsp_url(self, url: str) -> str:
        """Corrigir URLs RTSP com caracteres especiais na senha"""
        if url.startswith('rtsp://'):
            # Procurar por @ dentro da senha e codificar
            import urllib.parse
            
            # Buscar padrão rtsp://user:pass@host
            parts = url.split('://', 1)
            if len(parts) == 2:
                protocol, remainder = parts
                if '@' in remainder:
                    # Separar auth@host
                    auth_host = remainder.split('@', 1)
                    if len(auth_host) == 2:
                        auth, host = auth_host
                        # Se há mais @ em auth, significa que há @ na senha
                        if '@' in auth:
                            user_pass = auth.split(':', 1)
                            if len(user_pass) == 2:
                                user, password = user_pass
                                # Codificar @ na senha
                                password_encoded = password.replace('@', '%40')
                                fixed_url = f"{protocol}://{user}:{password_encoded}@{host}"
                                logger.info(f"URL RTSP corrigida: {url} -> {fixed_url}")
                                return fixed_url
        return url

    def _detect_gpu_decoder(self) -> str:
        """Detectar melhor decoder GPU disponível (NVIDIA NVDEC)"""
        try:
            # Ordem de preferência: NVDEC > outros GPU > CPU fallback
            gpu_decoders = [
                'nvdec',          # NVIDIA Video Codec SDK (melhor para NVIDIA)
                'nvh264dec',      # NVIDIA GPUs fallback
                'vaapih264dec',   # Intel/AMD GPUs
                'avdec_h264'      # FFmpeg CPU fallback
            ]
            
            for decoder in gpu_decoders:
                if gstreamer_service.check_plugin(decoder):
                    logger.info(f"🎯 GPU Decoder detectado: {decoder}")
                    return decoder
            
            logger.warning("🔄 Nenhum decoder encontrado, usando OpenCV fallback")
            return 'opencv_fallback'
            
        except Exception as e:
            logger.error(f"Erro ao detectar GPU decoder: {e}")
            return 'opencv_fallback'

    def _build_pipeline(self, camera_url: str) -> str:
        """Construir pipeline GStreamer otimizado com GPU decoding"""
        # Corrigir URL se necessário
        camera_url = self._fix_rtsp_url(camera_url)
        
        fps = self.camera_config.get('fps_limit', 10)
        camera_type = self.camera_config.get('type', 'rtsp')
        
        # Detectar melhor decoder GPU
        decoder = self._detect_gpu_decoder()
        
        # Configurações otimizadas baseadas nos logs de erro
        # Reduzir buffer UDP para evitar problemas de permissão
        buffer_size = min(self.camera_config.get('buffer_size', 2), 2)  # Máximo 2MB
        max_buffers = self.camera_config.get('max_buffers', 3)
        latency = self.camera_config.get('latency', 200)  # Aumentar latência para estabilidade
        
        # Usar método de escala mais simples e robusto
        scale_method = "bilinear"
        
        # Verificar se devemos usar o pipeline alternativo (mais estável para câmeras problemáticas)
        use_alt_pipeline = self.camera_config.get('use_alt_pipeline', False)
        
        # Configurações adicionais para robustez
        max_size_buffers = 15  # Reduzir para evitar sobrecarga
        leaky_mode = "downstream"
        
        if camera_type == 'webcam':
            # Pipeline otimizado para webcam local
            pipeline_str = f'''
            v4l2src device=/dev/video{camera_url} 
                ! video/x-raw,width=640,height=480,framerate=15/1
                ! videoconvert 
                ! videoscale method={scale_method}
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={fps}/1
                ! appsink name=appsink sync=false max-buffers={max_buffers} drop=true emit-signals=true
            '''
        elif use_alt_pipeline:
            # Pipeline ALTERNATIVO otimizado - forçar TCP e reduzir buffers
            pipeline_str = f'''
            rtspsrc location={camera_url} 
                buffer-mode=auto
                latency={latency} 
                drop-on-latency=true 
                retry=5 
                timeout=15
                udp-buffer-size={buffer_size * 512 * 1024}
                udp-reconnect=true
                protocols=tcp
                ! queue max-size-buffers={max_size_buffers} max-size-bytes=0 max-size-time=0 leaky={leaky_mode}
                ! rtph264depay 
                ! h264parse
                ! queue max-size-buffers=8 max-size-bytes=0 max-size-time=0 leaky={leaky_mode}
                ! decodebin
                ! queue max-size-buffers=8 max-size-bytes=0 max-size-time=0 leaky={leaky_mode}
                ! videoconvert
                ! videoscale method=nearest add-borders=false
                ! video/x-raw,format=BGR,width=640,height=480
                ! videorate
                ! video/x-raw,framerate={fps}/1
                ! appsink name=appsink sync=false max-buffers={max_buffers} drop=true emit-signals=true
            '''
        else:
            # Pipeline HIGH-PERFORMANCE com NVDEC (aceleração total NVIDIA)
            if decoder == 'nvdec':
                # Pipeline OTIMIZADO com NVDEC - Melhorias avançadas
                pipeline_str = f'''
                rtspsrc location={camera_url} protocols=tcp latency=100
                    ! rtph264depay
                    ! h264parse config-interval=-1
                    ! nvdec
                    ! queue leaky=2 max-size-buffers=10
                    ! videoconvert
                    ! video/x-raw,format=NV12
                    ! queue leaky=2 max-size-buffers=10
                    ! appsink name=appsink emit-signals=true max-buffers=5 drop=true sync=false
                '''
            elif decoder.startswith('nv'):
                # Outros decodificadores NVIDIA (nvh264dec) - PIPELINE OTIMIZADO
                pipeline_str = f'''
                rtspsrc location={camera_url} protocols=tcp latency=100
                    ! rtph264depay
                    ! h264parse config-interval=-1
                    ! {decoder}
                    ! queue leaky=2 max-size-buffers=10
                    ! videoconvert
                    ! video/x-raw,format=NV12
                    ! queue leaky=2 max-size-buffers=10
                    ! appsink name=appsink emit-signals=true max-buffers=5 drop=true sync=false
                '''
            else:
                # CPU Fallback (avdec_h264 ou outros) - PIPELINE OTIMIZADO
                pipeline_str = f'''
                rtspsrc location={camera_url} protocols=tcp latency=100
                    ! rtph264depay
                    ! h264parse config-interval=-1
                    ! {decoder}
                    ! queue leaky=2 max-size-buffers=10
                    ! videoconvert
                    ! video/x-raw,format=I420
                    ! queue leaky=2 max-size-buffers=10
                    ! appsink name=appsink emit-signals=true max-buffers=5 drop=true sync=false
                '''
        
        pipeline_type = "alternativo (robusto)" if use_alt_pipeline else "otimizado"
        optimizations = "TCP+latency=100+config-interval=-1+queue-leaky=2+drop=true+sync=false"
        logger.info(f"🚀 Pipeline {pipeline_type} construído com decoder: {decoder}, otimizações: {optimizations}")
        return pipeline_str.strip()
    
    def _build_snapshot_pipeline(self, camera_url: str) -> str:
        """Construir pipeline para captura de snapshot otimizado"""
        # Corrigir URL se necessário
        camera_url = self._fix_rtsp_url(camera_url)
        
        camera_type = self.camera_config.get('type', 'rtsp')
        
        if camera_type == 'webcam':
            pipeline_str = f'''
            v4l2src device=/dev/video{camera_url} 
                ! video/x-raw,width=1280,height=720,framerate=30/1
                ! videoconvert 
                ! videoscale
                ! video/x-raw,format=BGR,width=1280,height=720
                ! jpegenc quality=85
                ! appsink name=appsink sync=false max-buffers=1 drop=true
            '''
        else:
            pipeline_str = f'''
            rtspsrc location={camera_url} 
                latency=100 
                drop-on-latency=true 
                retry=3 
                timeout=10
                protocols=tcp
                ! rtph264depay 
                ! h264parse 
                ! avdec_h264 
                ! videoconvert 
                ! videoscale
                ! video/x-raw,format=BGR,width=1280,height=720
                ! jpegenc quality=85
                ! appsink name=appsink sync=false max-buffers=1 drop=true
            '''
        
        return pipeline_str.strip()
    
    def _build_stream_pipeline(self, camera_url: str) -> str:
        """Construir pipeline para streaming otimizado"""
        # Corrigir URL se necessário
        camera_url = self._fix_rtsp_url(camera_url)
        
        fps = min(self.camera_config.get('fps_limit', 10), 15)  # Limitar FPS para stream
        camera_type = self.camera_config.get('type', 'rtsp')
        
        if camera_type == 'webcam':
            pipeline_str = f'''
            v4l2src device=/dev/video{camera_url} 
                ! video/x-raw,width=640,height=480,framerate=30/1
                ! videoconvert 
                ! videoscale
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={fps}/1
                ! jpegenc quality=70
                ! appsink name=appsink sync=false max-buffers=1 drop=true
            '''
        else:
            pipeline_str = f'''
            rtspsrc location={camera_url} 
                latency=100 
                drop-on-latency=true 
                retry=3 
                timeout=10
                protocols=tcp
                ! rtph264depay 
                ! h264parse 
                ! avdec_h264 
                ! videoconvert 
                ! videoscale
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={fps}/1
                ! jpegenc quality=70
                ! appsink name=appsink sync=false max-buffers=1 drop=true
            '''
        
        return pipeline_str.strip()
    
    def _on_new_sample(self, appsink):
        """Callback otimizado para novos frames"""
        if not self.gstreamer_available:
            # Se GStreamer não estiver disponível, retornar um valor seguro
            return None
            
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.ERROR if self.gstreamer_available else None
                
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            
            if not buffer or not caps:
                return Gst.FlowReturn.ERROR if self.gstreamer_available else None
                
            # Obter informações do frame
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR if self.gstreamer_available else None
                
            # Obter dimensões do frame
            structure = caps.get_structure(0)
            width = structure.get_value("width")
            height = structure.get_value("height")
            format_str = structure.get_value("format")
            
            # Debug: mostrar informações do buffer
            buffer_size = len(map_info.data)
            
            # Calcular tamanho esperado baseado no formato
            if format_str == 'NV12':
                # NV12: Y plane (height*width) + UV plane (height*width/2)
                expected_size = height * width * 3 // 2
                channels = 1  # Será convertido para BGR depois
            elif format_str == 'I420':
                # I420: Y plane + U plane + V plane = height*width*1.5
                expected_size = height * width * 3 // 2
                channels = 1  # Será convertido para BGR depois
            else:
                # RGB/BGR = 3 canais
                expected_size = height * width * 3
                channels = 3
            
            logger.debug(f"🎥 Frame info - Width: {width}, Height: {height}, Format: {format_str}")
            logger.debug(f"📊 Buffer - Size: {buffer_size}, Expected: {expected_size}")
            
            # Verificar se o tamanho está correto
            if buffer_size < expected_size:
                logger.error(f"❌ Buffer muito pequeno: {buffer_size} < {expected_size}")
                buffer.unmap(map_info)
                return Gst.FlowReturn.ERROR
            
            # Criar array NumPy de forma segura
            try:
                # Usar frombuffer e reshape para maior segurança
                data_array = np.frombuffer(map_info.data, dtype=np.uint8)
                
                if format_str in ['NV12', 'I420']:
                    # Para formatos YUV, converter para BGR usando OpenCV
                    yuv_frame = data_array[:expected_size].reshape((height * 3 // 2, width))
                    if format_str == 'NV12':
                        frame = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2BGR_NV12)
                    else:  # I420
                        frame = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2BGR_I420)
                else:
                    # RGB/BGR direto
                    frame = data_array[:expected_size].reshape((height, width, channels))
                    
            except Exception as reshape_error:
                logger.error(f"❌ Erro ao processar frame {format_str}: {reshape_error}")
                buffer.unmap(map_info)
                return Gst.FlowReturn.ERROR
            
            # Liberar o buffer
            buffer.unmap(map_info)
            
            # Atualizar estatísticas
            with self.frame_lock:
                self.latest_frame = frame.copy()
                self.stats['frames_received'] += 1
                self.stats['last_frame_time'] = time.time()
                
                # Adicionar à fila se tiver espaço
                try:
                    if not self.frame_queue.full():
                        self.frame_queue.put_nowait(frame)
                except queue.Full:
                    pass
                    
                # Chamar callback se existir
                if self.frame_callback:
                    threading.Thread(
                        target=self._call_frame_callback_sync,
                        args=(frame.copy(),),
                        daemon=True
                    ).start()
            
            return Gst.FlowReturn.OK if self.gstreamer_available else None
            
        except Exception as e:
            logger.error(f"Erro ao processar frame: {e}")
            self.stats['errors'] += 1
            return Gst.FlowReturn.ERROR if self.gstreamer_available else None
    
    def _call_frame_callback_sync(self, frame: np.ndarray):
        """Chamar callback de frame de forma síncrona (corrigido)"""
        try:
            if self.frame_callback:
                # Se é uma corrotina, usar abordagem thread-safe
                if asyncio.iscoroutinefunction(self.frame_callback):
                    # Executar callback assíncrono em thread separada para não bloquear GStreamer
                    def run_async_callback():
                        try:
                            # Criar novo event loop para esta thread
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                loop.run_until_complete(self.frame_callback(self.camera_id, frame))
                            finally:
                                loop.close()
                        except Exception as e:
                            # Log silencioso para não spammar
                            if not hasattr(self, '_callback_error_logged'):
                                logger.warning(f"Callback assíncrono da câmera {self.camera_id} falhou, usando modo síncrono")
                                self._callback_error_logged = True
                    
                    # Executar em thread daemon para não bloquear
                    import threading
                    threading.Thread(target=run_async_callback, daemon=True).start()
                else:
                    # Callback síncrono
                    self.frame_callback(self.camera_id, frame)
        except Exception as e:
            # Log silencioso para evitar spam
            if not hasattr(self, '_callback_error_count'):
                self._callback_error_count = 0
            
            self._callback_error_count += 1
            if self._callback_error_count <= 3:  # Log apenas as primeiras 3 vezes
                logger.error(f"Erro no callback de frame da câmera {self.camera_id}: {e}")
            elif self._callback_error_count == 4:
                logger.error(f"Suprimindo logs de erro de callback para câmera {self.camera_id} (muitos erros)")
    
    def _on_eos(self, appsink):
        """Callback para fim do stream"""
        logger.warning(f"Stream da câmera {self.camera_id} terminou (EOS)")
        with self.state_lock:
            self.is_running = False
    
    def _on_error(self, bus, message):
        """Callback para erros do pipeline"""
        err, debug = message.parse_error()
        
        # Log detalhado do erro
        logger.error(f"=== ERRO GSTREAMER Câmera {self.camera_id} ===")
        logger.error(f"Erro: {err}")
        logger.error(f"Debug: {debug}")
        logger.error(f"Fonte: {message.src.get_name() if message.src else 'Unknown'}")
        logger.error(f"Codigo: {err.code if hasattr(err, 'code') else 'N/A'}")
        logger.error(f"Domnio: {err.domain if hasattr(err, 'domain') else 'N/A'}")
        logger.error("===========================================")
        
        with self.state_lock:
            self.is_running = False
        self.stats['errors'] += 1
    
    def _on_warning(self, bus, message):
        """Callback para warnings do pipeline"""
        warn, debug = message.parse_warning()
        logger.warning(f"Warning no pipeline da câmera {self.camera_id}: {warn}, {debug}")
    
    def _on_state_change(self, bus, message):
        """Callback para mudanças de estado do pipeline"""
        old_state, new_state, pending = message.parse_state_changed()
        if message.src == self.pipeline:
            self.stats['pipeline_state'] = new_state.value_name
            logger.debug(f"Câmera {self.camera_id}: Estado {old_state.value_name} -> {new_state.value_name}")
    
    def _bus_callback(self, bus, message):
        """Callback para mensagens do bus GStreamer"""
        if not self.gstreamer_available:
            return True
            
        t = message.type
        
        # Log TODAS as mensagens importantes para debug
        if t == Gst.MessageType.ERROR:
            logger.error(f"🔴 Câmera {self.camera_id}: ERROR message received")
        elif t == Gst.MessageType.WARNING:
            logger.warning(f"🟡 Câmera {self.camera_id}: WARNING message received")
        elif t == Gst.MessageType.STATE_CHANGED:
            old, new, pending = message.parse_state_changed()
            if message.src == self.pipeline:
                logger.info(f"🔄 Câmera {self.camera_id}: Pipeline state {old.value_name} -> {new.value_name}")
        elif t == Gst.MessageType.STREAM_STATUS:
            logger.debug(f"🌊 Câmera {self.camera_id}: Stream status message")
        elif t == Gst.MessageType.NEW_CLOCK:
            logger.debug(f"⏰ Câmera {self.camera_id}: New clock message")
        elif t == Gst.MessageType.ASYNC_DONE:
            logger.info(f"✅ Câmera {self.camera_id}: Async done - pipeline ready")
        
        if t == Gst.MessageType.EOS:
            # End of stream
            logger.warning(f"🔄 Câmera {self.camera_id}: End of Stream recebido")
            self._on_eos(self.appsink)
            
        elif t == Gst.MessageType.ERROR:
            # Erro
            self._on_error(bus, message)
            
            # Verificar se é um erro de decodificação e tentar recuperar
            err, debug = message.parse_error()
            error_msg = str(err).lower()
            
            if any(x in error_msg for x in ['decode', 'decoding', 'codec', 'buffer', 'no frame']):
                logger.warning(f"🔄 Câmera {self.camera_id}: Erro de decodificação detectado, tentando recuperar")
                
                # Tentar reiniciar o pipeline sem reiniciar todo o processo
                try:
                    if self.pipeline:
                        # Pausar o pipeline
                        self.pipeline.set_state(Gst.State.PAUSED)
                        # Aguardar um momento
                        time.sleep(0.5)
                        # Retomar o pipeline
                        self.pipeline.set_state(Gst.State.PLAYING)
                        logger.info(f"🔄 Câmera {self.camera_id}: Pipeline reiniciado após erro de decodificação")
                except Exception as e:
                    logger.error(f"❌ Câmera {self.camera_id}: Falha ao tentar recuperar de erro: {e}")
            
        elif t == Gst.MessageType.WARNING:
            # Aviso
            self._on_warning(bus, message)
            
        elif t == Gst.MessageType.STATE_CHANGED:
            # Mudança de estado
            self._on_state_change(bus, message)
            
        return True  # Continue watching
    
    def _gst_thread_func(self):
        """Função da thread GStreamer otimizada"""
        if not self.gstreamer_available:
            logger.error("GStreamer não disponível - thread não pode ser executada")
            return
            
        try:
            # Construir pipeline
            camera_url = self.camera_config.get('url')
            pipeline_str = self._build_pipeline(camera_url)
            
            logger.info(f"📹 Iniciando pipeline GStreamer para câmera {self.camera_id}")
            logger.debug(f"Pipeline string: {pipeline_str}")
            
            # Teste rápido de conectividade RTSP
            logger.debug(f"🔍 Testando conectividade RTSP para câmera {self.camera_id}")
            try:
                import socket
                import urllib.parse
                
                # Extrair host e porta da URL RTSP
                parsed = urllib.parse.urlparse(camera_url)
                host = parsed.hostname
                port = parsed.port or 554
                
                # Teste de socket TCP simples
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result != 0:
                    logger.error(f"❌ Câmera {self.camera_id}: RTSP {host}:{port} não alcançável (erro: {result})")
                else:
                    logger.info(f"✅ Câmera {self.camera_id}: RTSP {host}:{port} alcançável")
                    
            except Exception as e:
                logger.warning(f"⚠️ Câmera {self.camera_id}: Teste de conectividade falhou: {e}")
            
            # Criar pipeline
            logger.debug(f"🔧 Criando pipeline para câmera {self.camera_id}")
            self.pipeline = Gst.parse_launch(pipeline_str)
            if not self.pipeline:
                raise RuntimeError("Falha ao criar pipeline GStreamer")
            
            # Obter appsink
            logger.debug(f"🔍 Obtendo appsink para câmera {self.camera_id}")
            self.appsink = self.pipeline.get_by_name('appsink')
            if not self.appsink:
                raise RuntimeError("Falha ao obter appsink")
            
            # Configurar callbacks
            logger.debug(f"⚙️ Configurando callbacks para câmera {self.camera_id}")
            self.appsink.connect('new-sample', self._on_new_sample)
            self.appsink.connect('eos', self._on_eos)
            
            # Configurar bus
            logger.debug(f"🚌 Configurando bus para câmera {self.camera_id}")
            bus = self.pipeline.get_bus()
            self.bus_watch_id = bus.add_watch(GLib.PRIORITY_DEFAULT, self._bus_callback)
            
            # Definir estado do pipeline
            logger.debug(f"▶️ Iniciando pipeline para câmera {self.camera_id}")
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Falha ao iniciar pipeline")
            
            # Aguardar estado PLAYING com timeout menor
            logger.debug(f"⏱️ Aguardando estado PLAYING para câmera {self.camera_id}")
            timeout_ns = 30 * Gst.SECOND  # 30 segundos em nanosegundos
            ret = self.pipeline.get_state(timeout=timeout_ns)
            if ret[0] != Gst.StateChangeReturn.SUCCESS:
                if ret[0] == Gst.StateChangeReturn.ASYNC:
                    logger.warning(f"⏰ Pipeline ainda em transição para câmera {self.camera_id}")
                elif ret[0] == Gst.StateChangeReturn.FAILURE:
                    logger.error(f"❌ Pipeline falhou para câmera {self.camera_id}")
                    raise RuntimeError("Pipeline falhou ao atingir estado PLAYING")
                else:
                    logger.error(f"❌ Estado inesperado do pipeline para câmera {self.camera_id}: {ret[0]}")
                    raise RuntimeError(f"Pipeline não conseguiu atingir estado PLAYING: {ret[0]}")
            
            with self.state_lock:
                self.is_running = True
                self.is_initialized = True
            
            logger.info(f"✅ Pipeline da câmera {self.camera_id} iniciado com sucesso")
            
            # Criar main loop
            logger.debug(f"🔄 Iniciando main loop para câmera {self.camera_id}")
            self.main_loop = GLib.MainLoop()
            
            # Executar main loop
            self.main_loop.run()
            
        except Exception as e:
            logger.error(f"Erro na thread GStreamer da câmera {self.camera_id}: {e}")
            with self.state_lock:
                self.is_running = False
                self.is_initialized = False
        finally:
            self._cleanup_pipeline()
    
    def _cleanup_pipeline(self):
        """Limpar recursos do pipeline de forma segura"""
        if not self.gstreamer_available:
            return
            
        try:
            # Remover watch do bus
            if self.bus_watch_id and self.pipeline:
                bus = self.pipeline.get_bus()
                bus.remove_watch()
                self.bus_watch_id = None
            
            # Parar pipeline
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
            
            # Parar main loop
            if self.main_loop:
                self.main_loop.quit()
                self.main_loop = None
            
            logger.debug(f"Pipeline da câmera {self.camera_id} limpo")
            
        except Exception as e:
            logger.error(f"Erro ao limpar pipeline da câmera {self.camera_id}: {e}")
    
    async def initialize(self) -> bool:
        """Inicializar a câmera de forma assíncrona"""
        if not self.gstreamer_available:
            logger.error("GStreamer não disponível - não é possível inicializar a câmera")
            return False
            
        try:
            # Validar configuração da câmera
            camera_url = self.camera_config.get('url', '')
            if not camera_url:
                logger.error(f"URL da câmera {self.camera_id} não configurada")
                return False
            
            # Validar se a URL é válida
            camera_type = self.camera_config.get('type', 'rtsp')
            if camera_type == 'webcam':
                # Para webcam, verificar se é um número ou device path
                if camera_url.isdigit() or camera_url.startswith('/dev/video'):
                    logger.info(f"Configurando webcam {self.camera_id} - Device: {camera_url}")
                else:
                    logger.error(f"URL inválida para webcam {self.camera_id}: {camera_url}")
                    return False
            else:
                # Para RTSP, verificar se a URL tem o formato correto
                if not camera_url.startswith(('rtsp://', 'http://', 'https://')):
                    logger.error(f"URL inválida para câmera IP {self.camera_id}: {camera_url}")
                    return False
            
            logger.info(f"Inicializando câmera GStreamer {self.camera_id} ({camera_type}) - URL: {camera_url}")
            
            # Iniciar thread GStreamer
            self.gst_thread = threading.Thread(target=self._gst_thread_func, daemon=True)
            self.gst_thread.start()
            
            # Aguardar inicialização com timeout
            start_time = time.time()
            while not self.is_initialized and (time.time() - start_time) < self.connection_timeout:
                await asyncio.sleep(0.5)  # Verificar a cada 500ms
            
            if self.is_initialized:
                logger.info(f"✅ Câmera GStreamer {self.camera_id} inicializada com sucesso")
                return True
            else:
                logger.error(f"⏰ Timeout ({self.connection_timeout}s) ao inicializar câmera GStreamer {self.camera_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar câmera GStreamer {self.camera_id}: {e}")
            return False
    
    async def reconnect(self) -> bool:
        """Reconectar a câmera de forma assíncrona"""
        if not self.gstreamer_available:
            logger.error("GStreamer não disponível - não é possível reconectar a câmera")
            return False
            
        try:
            logger.info(f"Tentando reconectar câmera GStreamer {self.camera_id}...")
            
            # Parar pipeline atual
            await self.stop()
            
            # Aguardar um pouco
            await asyncio.sleep(self.reconnect_delay)
            
            # Tentar reconectar
            if await self.initialize():
                self.stats['reconnections'] += 1
                self.reconnect_attempts = 0
                logger.info(f"Câmera GStreamer {self.camera_id} reconectada com sucesso")
                return True
            else:
                self.reconnect_attempts += 1
                logger.error(f"Falha ao reconectar câmera GStreamer {self.camera_id}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao reconectar câmera GStreamer {self.camera_id}: {e}")
            return False
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Obter o frame mais recente de forma thread-safe"""
        with self.frame_lock:
            try:
                if not self.frame_queue.empty():
                    return self.frame_queue.get_nowait()
                return self.latest_frame
            except queue.Empty:
                return self.latest_frame
    
    def set_frame_callback(self, callback: Callable):
        """Definir callback para novos frames"""
        self.frame_callback = callback
    
    async def stop(self):
        """Parar a câmera de forma assíncrona"""
        try:
            with self.state_lock:
                self.is_running = False
                self.is_initialized = False
            
            # Parar main loop
            if self.main_loop:
                self.main_loop.quit()
            
            # Aguardar thread terminar
            if self.gst_thread and self.gst_thread.is_alive():
                self.gst_thread.join(timeout=5)
            
            # Cleanup final
            self._cleanup_pipeline()
            
            logger.info(f"Câmera GStreamer {self.camera_id} parada")
            
        except Exception as e:
            logger.error(f"Erro ao parar câmera GStreamer {self.camera_id}: {e}")
    
    def get_stats(self) -> dict:
        """Obter estatísticas da câmera de forma thread-safe"""
        with self.frame_lock:
            return {
                'camera_id': self.camera_id,
                'is_running': self.is_running,
                'is_initialized': self.is_initialized,
                'queue_size': self.frame_queue.qsize(),
                'stats': self.stats.copy()
            }
    
    def is_healthy(self) -> bool:
        """Verificar se a câmera está saudável"""
        with self.state_lock:
            if not self.is_running or not self.is_initialized:
                return False
        
        # Verificar se está recebendo frames
        with self.frame_lock:
            if self.stats['last_frame_time']:
                time_since_last_frame = time.time() - self.stats['last_frame_time']
                if time_since_last_frame > 15:  # Aumentado para 15 segundos
                    return False
        
        return True
    
    def __del__(self):
        """Destrutor para garantir limpeza"""
        try:
            if self.is_running:
                asyncio.create_task(self.stop())
        except Exception:
            pass

    def set_error_callback(self, callback):
        """Definir callback para erros"""
        self.error_callback = callback
        
    def _on_bus_message(self, bus, message):
        """Manipular mensagens do bus GStreamer"""
        t = message.type
        if t == Gst.MessageType.EOS:
            logger.warning(f"Câmera {self.camera_id}: Fim do stream")
            self.pipeline.set_state(Gst.State.NULL)
            self.is_running = False
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            error_msg = f"Erro GStreamer: {err}, {debug}"
            logger.error(f"Câmera {self.camera_id}: {error_msg}")
            
            # Incrementar contador de erros
            self.stats['errors'] += 1
            self.stats['last_error_time'] = time.time()
            
            # Notificar sobre o erro
            if self.error_callback:
                self.error_callback(self.camera_id, error_msg)
                
            # Se muitos erros ocorrerem em um curto período, reiniciar o pipeline
            if self.stats['errors'] > 5 and self.stats['last_error_time'] and time.time() - self.stats['last_error_time'] < 60:
                logger.warning(f"Câmera {self.camera_id}: Muitos erros, reiniciando pipeline")
                self._restart_pipeline()

class GStreamerCameraManager:
    """Gerenciador otimizado de câmeras GStreamer"""
    
    def __init__(self):
        self.cameras: Dict[str, GStreamerCamera] = {}
        self.camera_locks: Dict[str, threading.Lock] = {}
        self.is_running = False
        self.manager_lock = threading.Lock()
    
    async def add_camera(self, camera_id: str, camera_config: dict) -> bool:
        """Adicionar uma câmera de forma thread-safe"""
        with self.manager_lock:
            if camera_id in self.cameras:
                logger.warning(f"Câmera {camera_id} já existe")
                return False
            
            try:
                camera = GStreamerCamera(camera_id, camera_config)
                self.camera_locks[camera_id] = threading.Lock()
                
                if await camera.initialize():
                    self.cameras[camera_id] = camera
                    logger.info(f"Câmera GStreamer {camera_id} adicionada com sucesso")
                    return True
                else:
                    logger.error(f"Falha ao adicionar câmera GStreamer {camera_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"Erro ao adicionar câmera GStreamer {camera_id}: {e}")
                return False
    
    async def remove_camera(self, camera_id: str):
        """Remover uma câmera de forma thread-safe"""
        with self.manager_lock:
            if camera_id in self.cameras:
                camera = self.cameras[camera_id]
                await camera.stop()
                del self.cameras[camera_id]
                del self.camera_locks[camera_id]
                logger.info(f"Câmera GStreamer {camera_id} removida")
    
    def get_camera(self, camera_id: str) -> Optional[GStreamerCamera]:
        """Obter uma câmera de forma thread-safe"""
        with self.manager_lock:
            return self.cameras.get(camera_id)
    
    def get_all_cameras(self) -> dict:
        """Obter todas as câmeras de forma thread-safe"""
        with self.manager_lock:
            return self.cameras.copy()
    
    async def stop_all(self):
        """Parar todas as câmeras de forma thread-safe"""
        with self.manager_lock:
            camera_ids = list(self.cameras.keys())
        
        for camera_id in camera_ids:
            await self.remove_camera(camera_id)
    
    def get_stats(self) -> dict:
        """Obter estatísticas de todas as câmeras de forma thread-safe"""
        with self.manager_lock:
            stats = {}
            for camera_id, camera in self.cameras.items():
                stats[camera_id] = camera.get_stats()
        return stats
    
    def __del__(self):
        """Destrutor para garantir limpeza"""
        try:
            if self.cameras:
                asyncio.create_task(self.stop_all())
        except Exception:
            pass 