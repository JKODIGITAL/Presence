"""
Inicialização simplificada do GStreamer para ambiente MSYS2
SEM dependências externas complexas
"""

import os
import sys
import logging
from typing import Tuple, Optional, Any

# Configurar logging básico
logger = logging.getLogger(__name__)


def initialize_gstreamer() -> None:
    """Inicialização básica do GStreamer para MSYS2"""
    try:
        # Configurar variáveis de ambiente para GStreamer no MSYS2
        gst_plugin_path = "C:/msys64/mingw64/lib/gstreamer-1.0"
        if os.path.exists(gst_plugin_path):
            os.environ['GST_PLUGIN_PATH'] = gst_plugin_path
            logger.info(f"GST_PLUGIN_PATH configurado: {gst_plugin_path}")
        
        # Configurar PATH para incluir binários GStreamer
        gst_bin_path = "C:/msys64/mingw64/bin"
        if gst_bin_path not in os.environ.get('PATH', ''):
            current_path = os.environ.get('PATH', '')
            os.environ['PATH'] = f"{gst_bin_path};{current_path}"
            logger.info(f"PATH atualizado para incluir: {gst_bin_path}")
        
        # Configurações adicionais do GStreamer
        os.environ['GST_DEBUG'] = os.environ.get('GST_DEBUG', '1')  # Nível baixo de debug
        os.environ['GST_REGISTRY_FORK'] = 'no'  # Evitar problemas de fork
        
        logger.info("GStreamer inicialização básica concluída")
        
    except Exception as e:
        logger.error(f"Erro na inicialização básica do GStreamer: {e}")


def safe_import_gstreamer() -> Tuple[Optional[Any], Optional[Any], Optional[Any], bool, Optional[str]]:
    """Importação segura do GStreamer para MSYS2"""
    try:
        # Tentar importar gi primeiro
        import gi
        logger.info("gi (PyGObject) importado com sucesso")
        
        # Configurar versões
        gi.require_version('Gst', '1.0')
        gi.require_version('GstApp', '1.0')
        
        # Importar módulos GStreamer
        from gi.repository import Gst, GstApp, GLib
        
        # Inicializar GStreamer
        if not Gst.is_initialized():
            Gst.init(None)
            logger.info("GStreamer inicializado com sucesso")
        
        # Verificar versão
        version = Gst.version()
        logger.info(f"GStreamer versão: {version.major}.{version.minor}.{version.micro}")
        
        return Gst, GstApp, GLib, True, None
        
    except ImportError as e:
        error_msg = f"Erro ao importar GStreamer: {e}"
        logger.error(error_msg)
        logger.error("Certifique-se de que os seguintes pacotes estão instalados:")
        logger.error("- mingw-w64-x86_64-gstreamer")
        logger.error("- mingw-w64-x86_64-python-gobject")
        logger.error("Execute: pacman -S mingw-w64-x86_64-gstreamer mingw-w64-x86_64-python-gobject")
        
        return None, None, None, False, error_msg
        
    except Exception as e:
        error_msg = f"Erro inesperado ao inicializar GStreamer: {e}"
        logger.error(error_msg)
        return None, None, None, False, error_msg


def check_gstreamer_plugins(required_plugins: list = None) -> dict:
    """Verificar plugins disponíveis do GStreamer"""
    if required_plugins is None:
        required_plugins = [
            'rtspsrc',      # Para câmeras RTSP  
            'v4l2src',      # Para câmeras USB (Linux)
            'ksvideosrc',   # Para câmeras USB (Windows)
            'videoconvert', # Conversão de formato
            'videoscale',   # Redimensionamento
            'appsink',      # Sink para aplicação
            'queue',        # Buffer
        ]
    
    results = {}
    
    try:
        import subprocess
        gst_inspect = "C:/msys64/mingw64/bin/gst-inspect-1.0.exe"
        
        if not os.path.exists(gst_inspect):
            logger.warning(f"gst-inspect-1.0 não encontrado em: {gst_inspect}")
            return {plugin: False for plugin in required_plugins}
        
        for plugin in required_plugins:
            try:
                result = subprocess.run(
                    [gst_inspect, plugin], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                results[plugin] = result.returncode == 0
                
                if results[plugin]:
                    logger.debug(f"Plugin {plugin}: disponível")
                else:
                    logger.warning(f"Plugin {plugin}: não disponível")
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout ao verificar plugin {plugin}")
                results[plugin] = False
            except Exception as e:
                logger.warning(f"Erro ao verificar plugin {plugin}: {e}")
                results[plugin] = False
                
    except Exception as e:
        logger.error(f"Erro ao verificar plugins GStreamer: {e}")
        results = {plugin: False for plugin in required_plugins}
    
    return results


# Variáveis globais para compatibilidade
GSTREAMER_AVAILABLE = False
Gst = None
GstApp = None 
GLib = None
gstreamer_error = None

# Inicializar automaticamente quando o módulo for importado
try:
    initialize_gstreamer()
    Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error = safe_import_gstreamer()
except Exception as e:
    logger.error(f"Erro na inicialização automática: {e}")
    GSTREAMER_AVAILABLE = False
    gstreamer_error = str(e)

if GSTREAMER_AVAILABLE:
    logger.info("🎥 Simple GStreamer Init: Inicialização bem-sucedida")
else:
    logger.warning("⚠️ Simple GStreamer Init: GStreamer não disponível")
    logger.warning(f"Erro: {gstreamer_error}")