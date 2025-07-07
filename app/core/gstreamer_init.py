"""
Módulo centralizado para inicialização do GStreamer com tratamento robusto de erros
"""

import os
import sys
import platform
import logging
from typing import Tuple, Optional
from loguru import logger

# Variáveis globais para o estado do GStreamer
GSTREAMER_AVAILABLE = False
GSTREAMER_ERROR = None
Gst = None
GstApp = None
GLib = None

def setup_gstreamer_environment() -> bool:
    """Configurar ambiente GStreamer antes da importação"""
    try:
        system = platform.system()
        
        if system == 'Windows':
            # SOLUÇÃO DEFINITIVA: Usar apenas conda environment
            conda_prefix = os.environ.get('CONDA_PREFIX', '')
            if conda_prefix and 'presence' in conda_prefix:
                logger.info(f"Usando GStreamer do conda: {conda_prefix}")
                return True
            
            # Fallback: Se não tiver conda, tentar outras instalações
            gst_paths = [
                "C:\\msys64\\ucrt64",  # MSYS2 UCRT64 (prioridade)
                "C:\\gstreamer\\1.0",
                "C:\\Program Files\\gstreamer\\1.0", 
                "C:\\Program Files (x86)\\gstreamer\\1.0",
                os.path.expandvars("%GSTREAMER_ROOT_X86_64%"),
                os.path.expandvars("%GSTREAMER_ROOT_X86%")
            ]
            
            found_gst_path = None
            
            # Primeiro, garantir que MSYS2 esteja no PATH
            msys2_paths = [
                "C:\\msys64\\ucrt64\\bin",
                "C:\\msys64\\ucrt64\\lib",
                "C:\\msys64\\ucrt64\\include"
            ]
            
            for msys2_path in msys2_paths:
                if os.path.exists(msys2_path) and msys2_path not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = msys2_path + os.pathsep + os.environ.get('PATH', '')
                    logger.info(f"Adicionado caminho MSYS2 ao PATH: {msys2_path}")
            
            # Configurar variáveis específicas do MSYS2/GStreamer
            msys2_prefix = "C:\\msys64\\ucrt64"
            if os.path.exists(msys2_prefix):
                # Configurar PKG_CONFIG_PATH para MSYS2
                pkg_config_paths = [
                    f"{msys2_prefix}\\lib\\pkgconfig",
                    f"{msys2_prefix}\\share\\pkgconfig"
                ]
                current_pkg_config = os.environ.get('PKG_CONFIG_PATH', '')
                for pkg_path in pkg_config_paths:
                    if os.path.exists(pkg_path) and pkg_path not in current_pkg_config:
                        if current_pkg_config:
                            current_pkg_config += os.pathsep + pkg_path
                        else:
                            current_pkg_config = pkg_path
                os.environ['PKG_CONFIG_PATH'] = current_pkg_config
                
                # Configurar GI_TYPELIB_PATH para MSYS2
                gi_typelib_path = f"{msys2_prefix}\\lib\\girepository-1.0"
                if os.path.exists(gi_typelib_path):
                    os.environ['GI_TYPELIB_PATH'] = gi_typelib_path
                    logger.info(f"Configurado GI_TYPELIB_PATH: {gi_typelib_path}")
                
                # Configurar GST_PLUGIN_PATH para MSYS2  
                gst_plugin_paths = [
                    f"{msys2_prefix}\\lib\\gstreamer-1.0",
                    f"{msys2_prefix}\\lib\\gst-plugins-base",
                    f"{msys2_prefix}\\lib\\gst-plugins-good",
                    f"{msys2_prefix}\\lib\\gst-plugins-bad",
                    f"{msys2_prefix}\\lib\\gst-plugins-ugly"
                ]
                current_gst_plugins = os.environ.get('GST_PLUGIN_PATH', '')
                for plugin_path in gst_plugin_paths:
                    if os.path.exists(plugin_path) and plugin_path not in current_gst_plugins:
                        if current_gst_plugins:
                            current_gst_plugins += os.pathsep + plugin_path
                        else:
                            current_gst_plugins = plugin_path
                if current_gst_plugins:
                    os.environ['GST_PLUGIN_PATH'] = current_gst_plugins
                    logger.info(f"Configurado GST_PLUGIN_PATH: {current_gst_plugins}")
            
            # Procurar por GStreamer nas localizações
            for path in gst_paths:
                bin_path = os.path.join(path, 'bin')
                
                # Para MSYS2, verificar se gst-launch-1.0.exe existe
                if path.startswith("C:\\msys64"):
                    gst_launch = os.path.join(bin_path, 'gst-launch-1.0.exe')
                    if os.path.exists(gst_launch):
                        found_gst_path = path
                        logger.info(f"GStreamer MSYS2 encontrado em: {path}")
                        break
                else:
                    # Para instalações tradicionais
                    if os.path.exists(bin_path):
                        found_gst_path = path
                        logger.info(f"GStreamer encontrado em: {path}")
                        break
            
            if not found_gst_path:
                logger.warning("GStreamer não encontrado no Windows")
                return False
            
            return True
                
        elif system == 'Linux':
            # No Linux, verificar se GStreamer está instalado
            import subprocess
            try:
                result = subprocess.run(['which', 'gst-launch-1.0'], 
                                     capture_output=True, text=True)
                return result.returncode == 0
            except:
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Erro ao configurar ambiente GStreamer: {e}")
        return False

def initialize_gstreamer() -> Tuple[bool, Optional[str]]:
    """Inicializar GStreamer com tratamento robusto de erros"""
    global GSTREAMER_AVAILABLE, GSTREAMER_ERROR, Gst, GstApp, GLib
    
    # Se já foi inicializado, retornar o resultado
    if GSTREAMER_AVAILABLE or GSTREAMER_ERROR:
        return GSTREAMER_AVAILABLE, GSTREAMER_ERROR
    
    # Verificar se é Recognition Worker - se for, desabilitar GStreamer
    if os.environ.get('RECOGNITION_WORKER') == 'true':
        GSTREAMER_ERROR = "Recognition Worker - GStreamer desabilitado intencionalmente"
        logger.info("Recognition Worker detectado - GStreamer desabilitado para evitar conflitos")
        return False, GSTREAMER_ERROR
    
    # SOLUÇÃO DEFINITIVA: Configurar antes de importar
    use_native = os.environ.get("FORCE_GSTREAMER_NATIVE", "false").lower() == "true"
    
    if use_native:
        logger.info("[CONFIG] Forçando uso do GStreamer MSYS2 via variável de ambiente")
        GSTREAMER_ROOT = r"C:\msys64\ucrt64"
        os.environ["PATH"] = GSTREAMER_ROOT + r"\bin;" + os.environ.get("PATH", "")
        os.environ["GI_TYPELIB_PATH"] = GSTREAMER_ROOT + r"\lib\girepository-1.0"
        os.environ["GST_PLUGIN_PATH"] = GSTREAMER_ROOT + r"\lib\gstreamer-1.0"
        os.environ["PKG_CONFIG_PATH"] = GSTREAMER_ROOT + r"\lib\pkgconfig"
        logger.info("[OK] Variáveis do GStreamer MSYS2 configuradas ANTES da importação")
    else:
        logger.info("[TEST] Usando GStreamer do Conda (sem forçar nativo)")
        # Configurar ambiente primeiro
        if not setup_gstreamer_environment():
            GSTREAMER_ERROR = "Falha ao configurar ambiente GStreamer"
            return False, GSTREAMER_ERROR
    
    try:
        # Tentar importar PyGObject
        try:
            import gi
        except ImportError as e:
            GSTREAMER_ERROR = f"PyGObject não instalado: {e}"
            return False, GSTREAMER_ERROR
        except Exception as e:
            # Capturar erro específico de DLL no Windows
            if "DLL load failed" in str(e) or "procedimento especificado" in str(e):
                GSTREAMER_ERROR = f"Erro de DLL do PyGObject/GStreamer: {e}"
                return False, GSTREAMER_ERROR
            else:
                GSTREAMER_ERROR = f"Erro inesperado ao importar PyGObject: {e}"
                return False, GSTREAMER_ERROR
        
        # Configurar versões do GStreamer
        try:
            gi.require_version('Gst', '1.0')
            gi.require_version('GstApp', '1.0')
        except ValueError as e:
            GSTREAMER_ERROR = f"Versão do GStreamer não suportada: {e}"
            return False, GSTREAMER_ERROR
        
        # Importar módulos GStreamer
        try:
            from gi.repository import Gst as _Gst, GstApp as _GstApp, GLib as _GLib
            Gst = _Gst
            GstApp = _GstApp
            GLib = _GLib
        except ImportError as e:
            if "DLL load failed" in str(e):
                GSTREAMER_ERROR = f"DLL do GStreamer não encontrada: {e}"
                return False, GSTREAMER_ERROR
            else:
                GSTREAMER_ERROR = f"Erro ao importar módulos GStreamer: {e}"
                return False, GSTREAMER_ERROR
        
        # Inicializar GStreamer
        try:
            if not Gst.is_initialized():
                Gst.init(None)
            
            if not Gst.is_initialized():
                GSTREAMER_ERROR = "GStreamer não inicializou corretamente"
                return False, GSTREAMER_ERROR
        except Exception as e:
            GSTREAMER_ERROR = f"Erro ao inicializar GStreamer: {e}"
            return False, GSTREAMER_ERROR
        
        # Sucesso!
        GSTREAMER_AVAILABLE = True
        version = Gst.version_string()
        logger.info(f"GStreamer inicializado com sucesso: {version}")
        return True, None
        
    except Exception as e:
        GSTREAMER_ERROR = f"Erro inesperado na inicialização: {e}"
        return False, GSTREAMER_ERROR

def get_gstreamer_status() -> dict:
    """Obter status detalhado do GStreamer"""
    available, error = initialize_gstreamer()
    
    status = {
        'available': available,
        'error': error,
        'version': None,
        'plugins': []
    }
    
    if available and Gst:
        try:
            status['version'] = Gst.version_string()
            
            # Verificar alguns plugins críticos
            registry = Gst.Registry.get()
            critical_plugins = ['rtspsrc', 'v4l2src', 'appsink', 'videoconvert', 'videoscale']
            
            for plugin_name in critical_plugins:
                plugin = registry.find_feature(plugin_name, Gst.ElementFactory.__gtype__)
                status['plugins'].append({
                    'name': plugin_name,
                    'available': plugin is not None
                })
                
        except Exception as e:
            status['error'] = f"Erro ao obter informações: {e}"
    
    return status

def safe_import_gstreamer():
    """Importação segura do GStreamer retornando objetos ou None"""
    available, error = initialize_gstreamer()
    
    if available:
        return Gst, GstApp, GLib, True, None
    else:
        return None, None, None, False, error

# Não inicializar automaticamente - deixar para ser chamado explicitamente
# quando as variáveis de ambiente estiverem configuradas
# initialize_gstreamer()  # Removido para evitar problemas de ordem