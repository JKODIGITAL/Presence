"""
GStreamer Pipeline Factory - Fábrica de pipelines otimizados para diferentes cenários
"""

from typing import Dict, Any, Optional
from loguru import logger
import platform


class GStreamerPipelineFactory:
    """
    Fábrica de pipelines GStreamer otimizados para diferentes cenários:
    - RTSP com decodificação por hardware (NVDEC)
    - RTSP com decodificação por software (fallback)
    - Webcam local
    - Snapshot de alta qualidade
    - Streaming de baixa latência
    """
    
    @staticmethod
    def create_rtsp_pipeline_hardware(rtsp_url: str, fps: int = 10, width: int = 640, height: int = 480) -> str:
        """
        Pipeline RTSP com decodificação por hardware (NVDEC)
        Máxima performance para GPUs NVIDIA
        """
        pipeline = f"""
        rtspsrc location={rtsp_url}
            latency=200
            drop-on-latency=true
            retry=3
            timeout=10
            udp-reconnect=true
            tcp-timeout=10000000
        ! rtph264depay
        ! h264parse
        ! nvh264dec
        ! nvvideoconvert
        ! video/x-raw(memory:NVMM),format=RGBA,width={width},height={height}
        ! nvvideoconvert
        ! video/x-raw,format=BGR,width={width},height={height}
        ! videorate max-rate={fps}
        ! appsink name=appsink
            emit-signals=true
            max-buffers=2
            drop=true
            sync=false
        """
        return pipeline.strip()
    
    @staticmethod
    def create_rtsp_pipeline_software(rtsp_url: str, fps: int = 10, width: int = 640, height: int = 480) -> str:
        """
        Pipeline RTSP com decodificação por software (fallback)
        Compatibilidade universal
        """
        pipeline = f"""
        rtspsrc location={rtsp_url}
            latency=200
            drop-on-latency=true
            retry=3
            timeout=10
            udp-reconnect=true
            tcp-timeout=10000000
        ! rtph264depay
        ! h264parse
        ! avdec_h264 max-threads=2
        ! videoconvert
        ! videoscale method=nearest-neighbour
        ! videorate max-rate={fps}
        ! video/x-raw,format=BGR,width={width},height={height}
        ! appsink name=appsink
            emit-signals=true
            max-buffers=2
            drop=true
            sync=false
        """
        return pipeline.strip()
    
    @staticmethod
    def create_webcam_pipeline(device: str, fps: int = 30, width: int = 640, height: int = 480) -> str:
        """
        Pipeline para webcam local
        """
        # Converter device para formato correto
        if device.isdigit():
            device_path = f"/dev/video{device}"
        elif device.startswith('/dev/'):
            device_path = device
        else:
            device_path = f"/dev/video{device}"
        
        pipeline = f"""
        v4l2src device={device_path}
        ! video/x-raw,width={width},height={height},framerate={fps}/1
        ! videoconvert
        ! video/x-raw,format=BGR
        ! appsink name=appsink
            emit-signals=true
            max-buffers=2
            drop=true
            sync=false
        """
        return pipeline.strip()
    
    @staticmethod
    def create_snapshot_pipeline_rtsp(rtsp_url: str, width: int = 1920, height: int = 1080) -> str:
        """
        Pipeline para captura de snapshot de alta qualidade (RTSP)
        """
        pipeline = f"""
        rtspsrc location={rtsp_url}
            latency=0
            num-buffers=1
        ! rtph264depay
        ! h264parse
        ! avdec_h264
        ! videoconvert
        ! videoscale
        ! video/x-raw,format=BGR,width={width},height={height}
        ! appsink name=appsink
            emit-signals=true
            max-buffers=1
            drop=false
            sync=false
        """
        return pipeline.strip()
    
    @staticmethod
    def create_snapshot_pipeline_webcam(device: str, width: int = 1920, height: int = 1080) -> str:
        """
        Pipeline para captura de snapshot de alta qualidade (webcam)
        """
        if device.isdigit():
            device_path = f"/dev/video{device}"
        elif device.startswith('/dev/'):
            device_path = device
        else:
            device_path = f"/dev/video{device}"
        
        pipeline = f"""
        v4l2src device={device_path}
            num-buffers=1
        ! video/x-raw,width={width},height={height}
        ! videoconvert
        ! video/x-raw,format=BGR
        ! appsink name=appsink
            emit-signals=true
            max-buffers=1
            drop=false
            sync=false
        """
        return pipeline.strip()
    
    @staticmethod
    def create_streaming_pipeline_rtsp(rtsp_url: str, fps: int = 15, quality: int = 70) -> str:
        """
        Pipeline para streaming de baixa latência (RTSP)
        """
        pipeline = f"""
        rtspsrc location={rtsp_url}
            latency=0
            drop-on-latency=true
        ! rtph264depay
        ! h264parse
        ! avdec_h264
        ! videoconvert
        ! videoscale
        ! videorate max-rate={fps}
        ! video/x-raw,format=I420,width=640,height=480
        ! jpegenc quality={quality}
        ! appsink name=appsink
            emit-signals=true
            max-buffers=1
            drop=true
            sync=false
        """
        return pipeline.strip()
    
    @staticmethod
    def auto_create_pipeline(camera_config: Dict[str, Any], use_case: str = "recognition") -> str:
        """
        Criar pipeline automaticamente baseado na configuração da câmera
        
        Args:
            camera_config: Configuração da câmera
            use_case: Caso de uso ("recognition", "snapshot", "streaming")
        """
        camera_type = camera_config.get('type', 'rtsp')
        url = camera_config.get('url', '')
        fps = camera_config.get('fps_limit', 10)
        width = camera_config.get('width', 640)
        height = camera_config.get('height', 480)
        
        try:
            if use_case == "snapshot":
                # Alta qualidade para snapshots
                width = camera_config.get('snapshot_width', 1920)
                height = camera_config.get('snapshot_height', 1080)
                
                if camera_type == 'webcam':
                    return GStreamerPipelineFactory.create_snapshot_pipeline_webcam(url, width, height)
                else:
                    return GStreamerPipelineFactory.create_snapshot_pipeline_rtsp(url, width, height)
            
            elif use_case == "streaming":
                # Baixa latência para streaming
                fps = min(fps, 15)  # Limitar FPS para streaming
                quality = camera_config.get('streaming_quality', 70)
                
                if camera_type == 'webcam':
                    # Para webcam, usar pipeline normal
                    return GStreamerPipelineFactory.create_webcam_pipeline(url, fps, width, height)
                else:
                    return GStreamerPipelineFactory.create_streaming_pipeline_rtsp(url, fps, quality)
            
            else:  # recognition (default)
                if camera_type == 'webcam':
                    return GStreamerPipelineFactory.create_webcam_pipeline(url, fps, width, height)
                else:
                    # Tentar hardware decode primeiro, depois software
                    try:
                        # Verificar se NVDEC está disponível
                        import gi
                        gi.require_version('Gst', '1.0')
                        from gi.repository import Gst
                        
                        # Verificar se nvh264dec está disponível
                        registry = Gst.Registry.get()
                        nvh264dec = registry.find_feature("nvh264dec", Gst.ElementFactory.__gtype__)
                        
                        if nvh264dec:
                            logger.info(f"Usando decodificação por hardware para câmera {camera_config.get('id', 'unknown')}")
                            return GStreamerPipelineFactory.create_rtsp_pipeline_hardware(url, fps, width, height)
                        else:
                            logger.info(f"NVDEC não disponível, usando software decode para câmera {camera_config.get('id', 'unknown')}")
                            return GStreamerPipelineFactory.create_rtsp_pipeline_software(url, fps, width, height)
                    
                    except Exception as e:
                        logger.warning(f"Erro ao verificar NVDEC: {e}, usando software decode")
                        return GStreamerPipelineFactory.create_rtsp_pipeline_software(url, fps, width, height)
        
        except Exception as e:
            logger.error(f"Erro ao criar pipeline: {e}")
            # Fallback para pipeline básico
            if camera_type == 'webcam':
                return GStreamerPipelineFactory.create_webcam_pipeline(url, 10, 640, 480)
            else:
                return GStreamerPipelineFactory.create_rtsp_pipeline_software(url, 10, 640, 480)
    
    @staticmethod
    def validate_pipeline(pipeline_str: str) -> bool:
        """
        Validar se um pipeline GStreamer é válido
        """
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            
            # Tentar criar pipeline
            pipeline = Gst.parse_launch(pipeline_str)
            if pipeline:
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Pipeline inválido: {e}")
            return False
    
    @staticmethod
    def get_optimal_settings(camera_type: str, use_case: str = "recognition") -> Dict[str, Any]:
        """
        Obter configurações otimizadas para diferentes tipos de câmera
        """
        base_settings = {
            'fps_limit': 10,
            'width': 640,
            'height': 480,
            'max_buffers': 2,
            'latency': 200
        }
        
        if camera_type == 'webcam':
            base_settings.update({
                'fps_limit': 15,
                'latency': 0
            })
        
        elif camera_type == 'rtsp':
            if use_case == "recognition":
                base_settings.update({
                    'fps_limit': 10,
                    'latency': 200,
                    'max_buffers': 2
                })
            elif use_case == "streaming":
                base_settings.update({
                    'fps_limit': 15,
                    'latency': 0,
                    'max_buffers': 1,
                    'streaming_quality': 70
                })
            elif use_case == "snapshot":
                base_settings.update({
                    'snapshot_width': 1920,
                    'snapshot_height': 1080,
                    'max_buffers': 1
                })
        
        return base_settings