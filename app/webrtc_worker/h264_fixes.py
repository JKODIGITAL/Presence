#!/usr/bin/env python3
"""
H.264 Decoder Fixes - Correções para problemas de decodificação
"""

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class H264DecodingFixes:
    """Correções para problemas de decodificação H.264"""
    
    def __init__(self):
        self.applied_fixes = set()
    
    def apply_ffmpeg_environment_fixes(self):
        """Aplicar correções de ambiente para FFmpeg"""
        if 'ffmpeg_env' in self.applied_fixes:
            return
            
        # Configurações FFmpeg para melhor compatibilidade
        env_vars = {
            'FFREPORT': 'file=ffmpeg_report.log:level=32',  # Relatórios detalhados
            'FFMPEG_FORCE_NOAUDIO': '1',  # Forçar sem áudio se necessário
            'AV_LOG_FORCE_NOCOLOR': '1',  # Logs sem cor para melhor parsing
        }
        
        for key, value in env_vars.items():
            os.environ[key] = value
            
        self.applied_fixes.add('ffmpeg_env')
        logger.info("🔧 FFmpeg environment fixes applied")
    
    def get_optimized_h264_decoder_params(self) -> Dict[str, str]:
        """Parâmetros otimizados para decodificação H.264"""
        return {
            # Decodificador principal
            'decoder': 'avdec_h264',
            
            # Parser H.264 com correções
            'parser': 'h264parse',
            'parser_params': 'config-interval=-1',  # Inserir SPS/PPS conforme necessário
            
            # Caps de vídeo otimizadas
            'video_caps': 'video/x-raw,format=YUV420P,pixel-aspect-ratio=1/1',
            
            # Configurações de buffer
            'max_buffers': '3',
            'drop': 'true',
            'sync': 'false',
            
            # Configurações de erro recovery
            'skip_frame': 'default',  # Não pular frames por padrão
            'error_concealment': 'guess_mvs',  # Tentar corrigir erros
        }
    
    def create_robust_h264_pipeline(self, rtsp_url: str) -> str:
        """Criar pipeline H.264 robusto contra erros"""
        params = self.get_optimized_h264_decoder_params()
        
        # Pipeline com tratamento de erro robusto
        pipeline = (
            f"rtspsrc location={rtsp_url} "
            f"latency=200 buffer-mode=auto drop-on-latency=true "
            f"do-retransmission=false tcp-timeout=20000000 "
            f"protocols=tcp retry=5 ! "
            
            f"rtph264depay ! "
            f"{params['parser']} {params['parser_params']} ! "
            
            # Adicionar queue para absorver irregularidades
            f"queue max-size-buffers=10 max-size-time=1000000000 "
            f"leaky=downstream ! "
            
            f"{params['decoder']} "
            f"skip-frame={params['skip_frame']} ! "
            
            # Conversão com fallback
            f"videoconvert ! videoscale ! "
            f"{params['video_caps']} ! "
            
            f"appsink emit-signals=true "
            f"max-buffers={params['max_buffers']} "
            f"drop={params['drop']} sync={params['sync']}"
        )
        
        return pipeline
    
    def apply_gstreamer_debug_fixes(self):
        """Aplicar correções de debug do GStreamer"""
        if 'gst_debug' in self.applied_fixes:
            return
            
        # Configurar debug levels específicos para H.264
        debug_vars = {
            'GST_DEBUG': 'h264parse:5,avdec_h264:5,rtph264depay:5,rtspsrc:3',
            'GST_DEBUG_FILE': 'gstreamer_h264_debug.log',
            'GST_DEBUG_NO_COLOR': '1',
        }
        
        for key, value in debug_vars.items():
            os.environ[key] = value
            
        self.applied_fixes.add('gst_debug')
        logger.info("🔧 GStreamer H.264 debug fixes applied")
    
    def get_h264_profile_fixes(self) -> Dict[str, str]:
        """Correções específicas por perfil H.264"""
        return {
            # Baseline Profile (42001f)
            'baseline': {
                'profile_idc': '66',
                'level_idc': '31',
                'constraints': 'C0',
                'max_mbps': '245760',
                'max_fs': '8160',
                'max_br': '20000'
            },
            
            # Main Profile (42e01f) 
            'main': {
                'profile_idc': '77',
                'level_idc': '31',
                'constraints': 'E0',
                'max_mbps': '245760',
                'max_fs': '8160', 
                'max_br': '20000'
            },
            
            # High Profile (640032)
            'high': {
                'profile_idc': '100',
                'level_idc': '50',
                'constraints': '00',
                'max_mbps': '983040',
                'max_fs': '32400',
                'max_br': '50000'
            }
        }
    
    def fix_nal_unit_errors(self, pipeline_desc: str) -> str:
        """Adicionar correções para erros NAL unit"""
        
        # Adicionar parsebin para análise automática
        if 'parsebin' not in pipeline_desc:
            pipeline_desc = pipeline_desc.replace(
                'rtph264depay !',
                'rtph264depay ! parsebin !'
            )
        
        # Adicionar queue antes do parser para estabilizar stream
        if 'queue' not in pipeline_desc:
            pipeline_desc = pipeline_desc.replace(
                'rtph264depay !',
                'rtph264depay ! queue max-size-time=1000000000 !'
            )
            
        return pipeline_desc
    
    def apply_rtsp_stream_fixes(self):
        """Aplicar correções específicas para streams RTSP"""
        if 'rtsp_fixes' in self.applied_fixes:
            return
            
        # Configurações para melhor handling de RTSP
        rtsp_vars = {
            'RTSP_PROTOCOLS': 'tcp',  # Forçar TCP para estabilidade
            'RTSP_LATENCY': '200',    # Latência baixa
            'RTSP_TIMEOUT': '30',     # Timeout de 30 segundos
        }
        
        for key, value in rtsp_vars.items():
            os.environ[key] = value
            
        self.applied_fixes.add('rtsp_fixes')
        logger.info("🔧 RTSP stream fixes applied")
    
    def get_error_recovery_pipeline(self, rtsp_url: str) -> str:
        """Pipeline com recuperação automática de erros"""
        
        return (
            # Fonte RTSP com configurações robustas
            f"rtspsrc location={rtsp_url} "
            f"latency=200 buffer-mode=auto "
            f"drop-on-latency=true do-retransmission=false "
            f"tcp-timeout=30000000 protocols=tcp "
            f"retry=10 message-forward=true ! "
            
            # Depayloader com handling de erros
            f"rtph264depay aggregate-mode=zero-latency ! "
            
            # Queue para absorver problemas de rede
            f"queue max-size-buffers=30 max-size-time=3000000000 "
            f"leaky=downstream silent=false ! "
            
            # Parser H.264 com configuração robusta
            f"h264parse config-interval=-1 "
            f"disable-passthrough=true ! "
            
            # Capabilidades específicas para forçar formato
            f"video/x-h264,stream-format=avc,alignment=au ! "
            
            # Decodificador com fallback
            f"avdec_h264 skip-frame=default "
            f"lowres=0 fast=false ! "
            
            # Conversão com verificação de formato
            f"videoconvert ! videoscale ! "
            f"video/x-raw,format=YUV420P,pixel-aspect-ratio=1/1 ! "
            
            # Sink otimizado
            f"appsink emit-signals=true max-buffers=3 "
            f"drop=true sync=false"
        )
    
    def diagnose_h264_errors(self, error_log: str) -> List[str]:
        """Diagnosticar erros específicos de H.264"""
        recommendations = []
        
        if "error while decoding MB" in error_log:
            recommendations.append(
                "Macroblock decoding errors detected. "
                "Try reducing stream quality or check network stability."
            )
        
        if "bytestream" in error_log and ("0m" in error_log or "negative" in error_log):
            recommendations.append(
                "Bytestream corruption detected. "
                "Enable error concealment or switch to TCP transport."
            )
        
        if "sps_id" in error_log and "out of range" in error_log:
            recommendations.append(
                "SPS parameter set errors. "
                "Add h264parse with config-interval=-1 to fix."
            )
        
        if "NAL unit type" in error_log and "not implemented" in error_log:
            recommendations.append(
                "Unsupported NAL unit type. "
                "Update FFmpeg or add parsebin for automatic handling."
            )
        
        if "SEI type" in error_log and "truncated" in error_log:
            recommendations.append(
                "SEI message truncation. "
                "This is usually non-critical and can be ignored."
            )
        
        if "Increasing reorder buffer" in error_log:
            recommendations.append(
                "Frame reordering detected. "
                "This is normal for B-frames but may increase latency."
            )
        
        return recommendations
    
    def apply_all_fixes(self):
        """Aplicar todas as correções H.264"""
        logger.info("🔧 Applying H.264 decoding fixes...")
        
        self.apply_ffmpeg_environment_fixes()
        self.apply_gstreamer_debug_fixes()
        self.apply_rtsp_stream_fixes()
        
        logger.info("✅ All H.264 fixes applied")


# Instância global das correções
h264_fixes = H264DecodingFixes()

# Aplicar correções na importação
h264_fixes.apply_all_fixes()