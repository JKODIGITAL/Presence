"""
Performance Manager - Gerenciador de alta performance para múltiplas câmeras
- 1 processo por câmera
- Comunicação via filas multiprocessing
- Monitoramento e estatísticas centralizadas
"""

import os
import sys
import time
import signal
from typing import Dict, List, Any, Optional
from multiprocessing import Process, Queue, Event, Manager
from loguru import logger
from datetime import datetime, timedelta
import threading
import asyncio
from dataclasses import asdict
import json

from .camera_worker import start_camera_worker, FrameData, RecognitionResult


class PerformanceManager:
    """
    Gerenciador de alta performance para processamento de múltiplas câmeras IP
    
    Características:
    - 1 processo dedicado por câmera
    - Comunicação via filas multiprocessing
    - Monitoramento de saúde dos workers
    - Estatísticas centralizadas
    - Auto-restart de workers com falha
    """
    
    def __init__(self):
        self.workers: Dict[str, Dict[str, Any]] = {}  # camera_id -> worker info
        self.result_queues: Dict[str, Queue] = {}     # camera_id -> result queue
        self.stop_events: Dict[str, Event] = {}       # camera_id -> stop event
        
        # Estado do manager
        self.is_running = False
        self.manager_process = None
        
        # Configurações
        self.max_queue_size = 100
        self.worker_timeout = 30  # segundos
        self.restart_delay = 5    # segundos entre restarts
        self.max_restarts = 3     # máximo de restarts automáticos
        
        # Estatísticas centralizadas
        self.stats = {
            'total_cameras': 0,
            'active_cameras': 0,
            'total_frames_processed': 0,
            'total_faces_detected': 0,
            'total_recognitions': 0,
            'average_processing_time_ms': 0,
            'start_time': None,
            'last_activity': None
        }
        
        # Callbacks para resultados
        self.result_callbacks = []
        
        # Thread para processamento de resultados
        self.result_processor_thread = None
        self.result_processor_stop = threading.Event()
        
        logger.info("Performance Manager inicializado")
    
    def add_camera(self, camera_id: str, camera_config: Dict[str, Any]) -> bool:
        """
        Adicionar câmera ao sistema de alta performance
        
        Args:
            camera_id: ID único da câmera
            camera_config: Configuração da câmera (url, type, fps_limit, etc.)
            
        Returns:
            bool: True se adicionada com sucesso
        """
        try:
            if camera_id in self.workers:
                logger.warning(f"Câmera {camera_id} já existe")
                return False
            
            logger.info(f"Adicionando câmera {camera_id} ao sistema de performance")
            logger.debug(f"Configuração da câmera: {camera_config}")
            
            # Criar fila de resultados
            result_queue = Queue(maxsize=self.max_queue_size)
            stop_event = Event()
            
            # Criar processo worker
            worker_process = Process(
                target=start_camera_worker,
                args=(camera_id, camera_config, result_queue, stop_event),
                name=f"CameraWorker-{camera_id}",
                daemon=False
            )
            
            logger.debug(f"Processo worker criado para câmera {camera_id}")
            
            # Armazenar informações do worker
            self.workers[camera_id] = {
                'process': worker_process,
                'config': camera_config.copy(),
                'start_time': datetime.now(),
                'restart_count': 0,
                'last_activity': None,
                'status': 'starting'
            }
            
            self.result_queues[camera_id] = result_queue
            self.stop_events[camera_id] = stop_event
            
            # Iniciar processo
            logger.debug(f"Iniciando processo worker para câmera {camera_id}")
            worker_process.start()
            
            # Dar tempo ao processo iniciar
            time.sleep(0.1)
            
            # Verificar se processo iniciou
            if worker_process.is_alive():
                logger.info(f"[OK] Processo worker iniciado para câmera {camera_id} (PID: {worker_process.pid})")
                
                # Atualizar estatísticas
                self.stats['total_cameras'] += 1
                self.stats['active_cameras'] += 1
                
                logger.info(f"[OK] Câmera {camera_id} adicionada (PID: {worker_process.pid})")
                return True
            else:
                logger.error(f"[ERROR] Processo worker não iniciou para câmera {camera_id}")
                return False
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao adicionar câmera {camera_id}: {e}")
            return False
    
    def remove_camera(self, camera_id: str) -> bool:
        """
        Remover câmera do sistema
        
        Args:
            camera_id: ID da câmera a ser removida
            
        Returns:
            bool: True se removida com sucesso
        """
        try:
            if camera_id not in self.workers:
                logger.warning(f"Câmera {camera_id} não encontrada")
                return False
            
            logger.info(f"Removendo câmera {camera_id}")
            
            # Sinalizar parada
            if camera_id in self.stop_events:
                self.stop_events[camera_id].set()
            
            # Aguardar processo parar
            worker_info = self.workers[camera_id]
            process = worker_info['process']
            
            if process.is_alive():
                process.join(timeout=10)  # Aguardar 10 segundos
                
                if process.is_alive():
                    logger.warning(f"Forçando término do processo da câmera {camera_id}")
                    process.terminate()
                    process.join(timeout=5)
                    
                    if process.is_alive():
                        logger.error(f"Processo da câmera {camera_id} não respondeu, matando")
                        process.kill()
                        process.join()
            
            # Limpar recursos
            if camera_id in self.result_queues:
                # Drenar fila
                queue = self.result_queues[camera_id]
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except Exception:
                        break
                del self.result_queues[camera_id]
            
            if camera_id in self.stop_events:
                del self.stop_events[camera_id]
            
            del self.workers[camera_id]
            
            # Atualizar estatísticas
            self.stats['total_cameras'] -= 1
            self.stats['active_cameras'] -= 1
            
            logger.info(f"[OK] Câmera {camera_id} removida")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao remover câmera {camera_id}: {e}")
            return False
    
    def start(self) -> bool:
        """Iniciar o manager"""
        try:
            if self.is_running:
                logger.warning("Manager já está rodando")
                return True
            
            logger.info("Iniciando Performance Manager")
            
            # Configurar signal handlers
            self._setup_signal_handlers()
            
            # Iniciar thread de processamento de resultados
            self.result_processor_stop.clear()
            self.result_processor_thread = threading.Thread(
                target=self._process_results_loop,
                daemon=True
            )
            self.result_processor_thread.start()
            
            # Iniciar thread de monitoramento
            self.monitor_thread = threading.Thread(
                target=self._monitor_workers_loop,
                daemon=True
            )
            self.monitor_thread.start()
            
            self.is_running = True
            self.stats['start_time'] = datetime.now()
            
            logger.info("[OK] Performance Manager iniciado")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao iniciar Performance Manager: {e}")
            return False
    
    def stop(self):
        """Parar o manager e todos os workers"""
        try:
            if not self.is_running:
                return
            
            logger.info("Parando Performance Manager")
            
            self.is_running = False
            
            # Parar thread de processamento
            self.result_processor_stop.set()
            if self.result_processor_thread:
                self.result_processor_thread.join(timeout=5)
            
            # Parar todos os workers
            camera_ids = list(self.workers.keys())
            for camera_id in camera_ids:
                self.remove_camera(camera_id)
            
            logger.info("[OK] Performance Manager parado")
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao parar Performance Manager: {e}")
    
    def _setup_signal_handlers(self):
        """Configurar handlers para sinais do sistema"""
        def signal_handler(signum, frame):
            logger.info(f"Recebido sinal {signum}, parando Performance Manager...")
            self.stop()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def _process_results_loop(self):
        """Loop para processar resultados de todas as câmeras"""
        logger.info("Iniciando loop de processamento de resultados")
        
        while not self.result_processor_stop.is_set():
            try:
                # Processar resultados de todas as filas
                for camera_id, queue in self.result_queues.items():
                    try:
                        # Processar múltiplos resultados por iteração
                        processed_count = 0
                        max_per_iteration = 10
                        
                        while processed_count < max_per_iteration and not queue.empty():
                            try:
                                frame_data = queue.get_nowait()
                                self._process_frame_result(frame_data)
                                processed_count += 1
                            except Exception:
                                break
                                
                    except Exception as e:
                        logger.error(f"Erro ao processar resultados da câmera {camera_id}: {e}")
                
                # Pequena pausa para evitar 100% CPU
                time.sleep(0.01)  # 10ms
                
            except Exception as e:
                logger.error(f"Erro no loop de processamento: {e}")
                time.sleep(0.1)
        
        logger.info("Loop de processamento de resultados finalizado")
    
    def _process_frame_result(self, frame_data: FrameData):
        """Processar resultado de um frame"""
        try:
            # Atualizar estatísticas
            self.stats['total_frames_processed'] += 1
            self.stats['total_faces_detected'] += len(frame_data.recognitions)
            self.stats['total_recognitions'] += len([r for r in frame_data.recognitions if not r.is_unknown])
            self.stats['last_activity'] = datetime.now()
            
            # Atualizar estatísticas da câmera
            if frame_data.camera_id in self.workers:
                self.workers[frame_data.camera_id]['last_activity'] = frame_data.timestamp
                self.workers[frame_data.camera_id]['status'] = 'active'
            
            # Calcular tempo médio de processamento
            if self.stats['total_frames_processed'] > 0:
                # Atualizar média móvel simples
                current_avg = self.stats['average_processing_time_ms']
                new_avg = (current_avg * 0.9) + (frame_data.processing_time_ms * 0.1)
                self.stats['average_processing_time_ms'] = new_avg
            
            # Chamar callbacks registrados
            for callback in self.result_callbacks:
                try:
                    callback(frame_data)
                except Exception as e:
                    logger.error(f"Erro em callback de resultado: {e}")
            
            # Log de reconhecimentos importantes
            for recognition in frame_data.recognitions:
                if not recognition.is_unknown and recognition.confidence > 0.8:
                    logger.info(f"👤 {recognition.person_name} reconhecido na câmera {frame_data.camera_id} "
                              f"(conf: {recognition.confidence:.2f})")
            
        except Exception as e:
            logger.error(f"Erro ao processar resultado do frame: {e}")
    
    def _monitor_workers_loop(self):
        """Loop para monitorar saúde dos workers"""
        logger.info("Iniciando loop de monitoramento de workers")
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                for camera_id, worker_info in list(self.workers.items()):
                    try:
                        process = worker_info['process']
                        
                        # Verificar se processo está vivo
                        if not process.is_alive():
                            logger.warning(f"Worker da câmera {camera_id} morreu (exit code: {process.exitcode})")
                            self._restart_worker(camera_id)
                            continue
                        
                        # Verificar timeout de atividade
                        last_activity = worker_info.get('last_activity')
                        if last_activity:
                            inactive_time = (current_time - last_activity).total_seconds()
                            if inactive_time > self.worker_timeout:
                                logger.warning(f"Worker da câmera {camera_id} inativo por {inactive_time:.1f}s")
                                worker_info['status'] = 'inactive'
                                
                                # Se muito tempo inativo, reiniciar
                                if inactive_time > self.worker_timeout * 2:
                                    logger.warning(f"Reiniciando worker inativo da câmera {camera_id}")
                                    self._restart_worker(camera_id)
                        
                    except Exception as e:
                        logger.error(f"Erro ao monitorar worker da câmera {camera_id}: {e}")
                
                time.sleep(5)  # Verificar a cada 5 segundos
                
            except Exception as e:
                logger.error(f"Erro no loop de monitoramento: {e}")
                time.sleep(5)
        
        logger.info("Loop de monitoramento finalizado")
    
    def _restart_worker(self, camera_id: str):
        """Reiniciar worker com falha"""
        try:
            if camera_id not in self.workers:
                return
            
            worker_info = self.workers[camera_id]
            restart_count = worker_info.get('restart_count', 0)
            
            if restart_count >= self.max_restarts:
                logger.error(f"Máximo de restarts atingido para câmera {camera_id}, removendo")
                self.remove_camera(camera_id)
                return
            
            logger.info(f"Reiniciando worker da câmera {camera_id} (tentativa {restart_count + 1})")
            
            # Salvar configuração
            camera_config = worker_info['config'].copy()
            
            # Remover worker atual
            self.remove_camera(camera_id)
            
            # Aguardar um pouco
            time.sleep(self.restart_delay)
            
            # Recriar worker
            if self.add_camera(camera_id, camera_config):
                # Atualizar contador de restarts
                if camera_id in self.workers:
                    self.workers[camera_id]['restart_count'] = restart_count + 1
                logger.info(f"[OK] Worker da câmera {camera_id} reiniciado")
            else:
                logger.error(f"[ERROR] Falha ao reiniciar worker da câmera {camera_id}")
            
        except Exception as e:
            logger.error(f"Erro ao reiniciar worker da câmera {camera_id}: {e}")
    
    def register_result_callback(self, callback):
        """Registrar callback para receber resultados de reconhecimento"""
        self.result_callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do sistema"""
        stats = self.stats.copy()
        
        # Adicionar informações dos workers
        stats['workers'] = {}
        for camera_id, worker_info in self.workers.items():
            process = worker_info['process']
            stats['workers'][camera_id] = {
                'pid': process.pid if process.is_alive() else None,
                'is_alive': process.is_alive(),
                'status': worker_info.get('status', 'unknown'),
                'start_time': worker_info['start_time'].isoformat(),
                'restart_count': worker_info.get('restart_count', 0),
                'last_activity': worker_info['last_activity'].isoformat() if worker_info.get('last_activity') else None,
                'queue_size': self.result_queues[camera_id].qsize() if camera_id in self.result_queues else 0
            }
        
        # Calcular tempo de execução
        if stats['start_time']:
            runtime = datetime.now() - stats['start_time']
            stats['runtime_seconds'] = runtime.total_seconds()
        
        return stats
    
    def get_camera_list(self) -> List[str]:
        """Obter lista de IDs das câmeras ativas"""
        return list(self.workers.keys())
    
    def is_camera_active(self, camera_id: str) -> bool:
        """Verificar se uma câmera está ativa"""
        if camera_id not in self.workers:
            return False
        
        worker_info = self.workers[camera_id]
        process = worker_info['process']
        return process.is_alive()
    
    def __del__(self):
        """Destrutor para garantir limpeza"""
        try:
            self.stop()
        except Exception:
            pass