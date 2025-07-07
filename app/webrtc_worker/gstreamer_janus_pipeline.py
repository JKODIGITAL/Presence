#!/usr/bin/env python3
"""
Pipeline GStreamer + IA + NVENC → Janus WebRTC
Integração completa com reconhecimento facial inline
"""

import asyncio
import logging
import numpy as np
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib
import aiohttp
import json
from typing import Optional, Dict, Any
import cv2
from dataclasses import dataclass
import time

# Importar engine de reconhecimento
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.recognition_engine import RecognitionEngine

logger = logging.getLogger(__name__)

@dataclass
class StreamConfig:
    camera_id: str
    camera_name: str
    rtsp_url: str
    janus_video_port: int
    janus_audio_port: int
    enable_recognition: bool = True
    enable_nvenc: bool = True
    bitrate: int = 2000000  # 2 Mbps
    framerate: int = 15
    width: int = 1280
    height: int = 720

class GStreamerJanusPipeline:
    """
    Pipeline completo: Captura → IA → NVENC → Janus
    """
    
    def __init__(self, config: StreamConfig):
        self.config = config
        self.pipeline = None
        self.recognition_engine = None
        self.last_recognition_time = 0
        self.recognition_interval = 0.5  # 500ms entre reconhecimentos
        self.frame_count = 0
        
        # Inicializar GStreamer
        Gst.init(None)
        
        # Inicializar IA se habilitado
        if config.enable_recognition:
            self.init_recognition_engine()
    
    def init_recognition_engine(self):
        """Inicializa engine de reconhecimento facial"""
        try:
            self.recognition_engine = RecognitionEngine()
            logger.info(f"✅ IA inicializada para {self.config.camera_name}")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar IA: {e}")
            self.config.enable_recognition = False
    
    def build_pipeline(self) -> str:
        """Constrói pipeline GStreamer com IA inline"""
        
        # Fonte (RTSP ou arquivo)
        if self.config.rtsp_url.startswith('rtsp://'):
            source = f'rtspsrc location="{self.config.rtsp_url}" latency=100 ! rtph264depay'
        elif self.config.rtsp_url.endswith('.mp4'):
            source = f'filesrc location="{self.config.rtsp_url}" ! qtdemux'
        else:
            source = 'videotestsrc'
        
        # Decoder
        decoder = 'nvh264dec' if self.config.enable_nvenc else 'avdec_h264'
        
        # Processamento com IA (via appsink/appsrc)
        if self.config.enable_recognition:
            # Pipeline com IA inline
            ia_process = f'''
                ! videoscale ! video/x-raw,width={self.config.width},height={self.config.height}
                ! videoconvert
                ! appsink name=ia_sink emit-signals=true sync=false max-buffers=1 drop=true
                appsrc name=ia_src caps=video/x-raw,format=I420,width={self.config.width},height={self.config.height},framerate={self.config.framerate}/1
                ! queue max-size-buffers=10
            '''
        else:
            # Pipeline direto sem IA
            ia_process = f'''
                ! videoscale ! video/x-raw,width={self.config.width},height={self.config.height}
                ! videoconvert ! video/x-raw,format=I420
            '''
        
        # Encoder
        if self.config.enable_nvenc:
            encoder = f'''
                nvh264enc 
                    preset=low-latency-hq 
                    bitrate={self.config.bitrate // 1000}
                    gop-size=30
                    rc-mode=cbr
            '''
        else:
            encoder = f'''
                x264enc 
                    tune=zerolatency 
                    bitrate={self.config.bitrate // 1000}
                    key-int-max=30
            '''
        
        # Pipeline completo
        pipeline = f'''
            {source}
            ! {decoder}
            {ia_process}
            ! {encoder}
            ! h264parse config-interval=-1
            ! rtph264pay pt=96
            ! udpsink host=127.0.0.1 port={self.config.janus_video_port}
        '''
        
        # Limpar espaços extras
        pipeline = ' '.join(pipeline.split())
        
        logger.info(f"📹 Pipeline para {self.config.camera_name}:")
        logger.info(f"   {pipeline}")
        
        return pipeline
    
    def on_new_sample(self, sink):
        """Callback para processar frames com IA"""
        sample = sink.emit('pull-sample')
        if not sample:
            return Gst.FlowReturn.OK
        
        # Obter buffer
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        
        # Extrair dimensões
        struct = caps.get_structure(0)
        width = struct.get_value('width')
        height = struct.get_value('height')
        
        # Converter para numpy array
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.ERROR
        
        try:
            # Frame como numpy array
            frame_data = np.frombuffer(map_info.data, dtype=np.uint8)
            
            # Assumindo formato I420 (YUV420)
            y_size = width * height
            uv_size = y_size // 4
            
            # Extrair componente Y (luminância)
            y_data = frame_data[:y_size].reshape((height, width))
            
            # Converter para RGB se necessário para IA
            current_time = time.time()
            if (current_time - self.last_recognition_time) >= self.recognition_interval:
                # Processar com IA
                self.process_frame_with_ai(y_data, width, height)
                self.last_recognition_time = current_time
            
            # Reenviar frame para pipeline
            self.push_frame_to_pipeline(frame_data)
            
        finally:
            buffer.unmap(map_info)
        
        return Gst.FlowReturn.OK
    
    def process_frame_with_ai(self, y_frame: np.ndarray, width: int, height: int):
        """Processa frame com reconhecimento facial"""
        if not self.recognition_engine:
            return
        
        try:
            # Converter Y para RGB (aproximação)
            rgb_frame = cv2.cvtColor(y_frame, cv2.COLOR_GRAY2RGB)
            
            # Detectar e reconhecer faces
            faces = self.recognition_engine.detect_faces(rgb_frame)
            
            if faces:
                for face in faces:
                    # Extrair face
                    x1, y1, x2, y2 = face['bbox']
                    face_img = rgb_frame[y1:y2, x1:x2]
                    
                    # Reconhecer
                    result = self.recognition_engine.recognize_face(face_img)
                    
                    if result['person_id']:
                        logger.info(f"🧑 Reconhecido: {result['person_name']} ({result['confidence']:.2f})")
                    else:
                        logger.info(f"❓ Desconhecido (confiança: {result['confidence']:.2f})")
            
            self.frame_count += 1
            if self.frame_count % 100 == 0:
                logger.info(f"📊 Frames processados: {self.frame_count}")
                
        except Exception as e:
            logger.error(f"❌ Erro no reconhecimento: {e}")
    
    def push_frame_to_pipeline(self, frame_data: bytes):
        """Envia frame de volta para o pipeline"""
        # Obter appsrc
        appsrc = self.pipeline.get_by_name('ia_src')
        if not appsrc:
            return
        
        # Criar buffer
        buffer = Gst.Buffer.new_wrapped(frame_data)
        
        # Enviar
        ret = appsrc.emit('push-buffer', buffer)
        if ret != Gst.FlowReturn.OK:
            logger.warning(f"⚠️ Erro ao enviar frame: {ret}")
    
    def start(self):
        """Inicia o pipeline"""
        try:
            # Criar pipeline
            pipeline_str = self.build_pipeline()
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            # Conectar callback se IA habilitada
            if self.config.enable_recognition:
                appsink = self.pipeline.get_by_name('ia_sink')
                if appsink:
                    appsink.connect('new-sample', self.on_new_sample)
                    logger.info("✅ IA conectada ao pipeline")
            
            # Iniciar
            self.pipeline.set_state(Gst.State.PLAYING)
            
            logger.info(f"▶️ Pipeline iniciado para {self.config.camera_name}")
            
            # Loop principal
            loop = GLib.MainLoop()
            
            # Handler de mensagens
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', self.on_bus_message, loop)
            
            loop.run()
            
        except Exception as e:
            logger.error(f"❌ Erro no pipeline: {e}")
        finally:
            self.stop()
    
    def on_bus_message(self, bus, message, loop):
        """Handler de mensagens do GStreamer"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            logger.info("📭 End of stream")
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"❌ Erro: {err}, {debug}")
            loop.quit()
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            logger.warning(f"⚠️ Aviso: {err}, {debug}")
    
    def stop(self):
        """Para o pipeline"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            logger.info(f"⏹️ Pipeline parado para {self.config.camera_name}")


async def main():
    """Exemplo de uso"""
    
    # Configuração da stream
    config = StreamConfig(
        camera_id="test-cam-1",
        camera_name="Camera Teste",
        rtsp_url="rtsp://admin:senha@192.168.1.100/stream",
        janus_video_port=5004,
        janus_audio_port=5005,
        enable_recognition=True,
        enable_nvenc=True
    )
    
    # Criar e iniciar pipeline
    pipeline = GStreamerJanusPipeline(config)
    
    # Rodar em thread separada
    import threading
    thread = threading.Thread(target=pipeline.start)
    thread.start()
    
    # Aguardar
    try:
        await asyncio.sleep(3600)  # 1 hora
    except KeyboardInterrupt:
        logger.info("⏸️ Interrompido pelo usuário")
    finally:
        pipeline.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())