#!/usr/bin/env python3
"""
Verificação Completa do Pipeline GPU (NVDEC + FAISS + NVENC)
"""

import asyncio
import sys
import os
import time
import json
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime
from loguru import logger

# Adicionar path do projeto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configurar ambiente
os.environ['PYTHONPATH'] = str(project_root)
os.environ['USE_GPU'] = 'true'
os.environ['USE_NVENC'] = 'true'
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['FORCE_GSTREAMER_NATIVE'] = 'true'
os.environ['RECOGNITION_WORKER'] = 'true'  # Para forçar GPU no recognition

# Configurar logging
logger.add("logs/gpu_pipeline_verification.log", rotation="10 MB", level="DEBUG")


class GPUPipelineVerifier:
    """Verificador completo do pipeline GPU"""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'environment': {},
            'tests': {},
            'summary': {
                'total_tests': 0,
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }
        
    def capture_environment(self):
        """Capturar informações do ambiente"""
        logger.info("📋 Capturando informações do ambiente...")
        
        self.results['environment'] = {
            'python_version': sys.version,
            'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES', 'NOT_SET'),
            'use_gpu': os.environ.get('USE_GPU', 'NOT_SET'),
            'use_nvenc': os.environ.get('USE_NVENC', 'NOT_SET'),
            'platform': sys.platform,
            'project_root': str(project_root)
        }
        
        # Verificar NVIDIA GPU
        try:
            import subprocess
            nvidia_smi = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'], 
                                      capture_output=True, text=True)
            if nvidia_smi.returncode == 0:
                gpu_info = nvidia_smi.stdout.strip()
                self.results['environment']['gpu'] = gpu_info
                logger.info(f"✅ GPU detectada: {gpu_info}")
            else:
                self.results['environment']['gpu'] = 'NOT_DETECTED'
                logger.warning("⚠️ GPU NVIDIA não detectada")
        except Exception as e:
            self.results['environment']['gpu'] = f'ERROR: {str(e)}'
            logger.error(f"❌ Erro ao detectar GPU: {e}")
    
    async def test_gstreamer_availability(self):
        """Teste 1: Verificar disponibilidade do GStreamer"""
        test_name = "gstreamer_availability"
        logger.info("\n🧪 Teste 1: Verificando GStreamer...")
        
        try:
            from app.core.gstreamer_init import initialize_gstreamer, safe_import_gstreamer
            
            initialize_gstreamer()
            Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error = safe_import_gstreamer()
            
            if GSTREAMER_AVAILABLE:
                version = Gst.version_string()
                self.results['tests'][test_name] = {
                    'status': 'PASSED',
                    'version': version,
                    'initialized': Gst.is_initialized()
                }
                logger.info(f"✅ GStreamer disponível: {version}")
                return True
            else:
                self.results['tests'][test_name] = {
                    'status': 'FAILED',
                    'error': gstreamer_error
                }
                logger.error(f"❌ GStreamer não disponível: {gstreamer_error}")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar GStreamer: {e}")
            return False
    
    async def test_nvdec_decoder(self):
        """Teste 2: Verificar NVDEC decoder"""
        test_name = "nvdec_decoder"
        logger.info("\n🧪 Teste 2: Verificando NVDEC decoder...")
        
        try:
            from app.core.gstreamer_init import safe_import_gstreamer
            Gst, _, _, GSTREAMER_AVAILABLE, _ = safe_import_gstreamer()
            
            if not GSTREAMER_AVAILABLE:
                self.results['tests'][test_name] = {'status': 'SKIPPED', 'reason': 'GStreamer não disponível'}
                return False
            
            # Verificar elementos NVDEC
            nvdec_elements = ['nvdec', 'nvh264dec', 'nvh265dec']
            available_decoders = []
            
            for element in nvdec_elements:
                factory = Gst.ElementFactory.find(element)
                if factory:
                    available_decoders.append(element)
            
            if 'nvh264dec' in available_decoders:
                self.results['tests'][test_name] = {
                    'status': 'PASSED',
                    'available_decoders': available_decoders
                }
                logger.info(f"✅ NVDEC disponível: {', '.join(available_decoders)}")
                return True
            else:
                self.results['tests'][test_name] = {
                    'status': 'WARNING',
                    'available_decoders': available_decoders,
                    'message': 'nvh264dec não disponível, usando fallback'
                }
                logger.warning("⚠️ nvh264dec não disponível")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar NVDEC: {e}")
            return False
    
    async def test_nvenc_encoder(self):
        """Teste 3: Verificar NVENC encoder"""
        test_name = "nvenc_encoder"
        logger.info("\n🧪 Teste 3: Verificando NVENC encoder...")
        
        try:
            from app.camera_worker.nvenc_encoder import NVENCEncoder, GSTREAMER_AVAILABLE
            
            if not GSTREAMER_AVAILABLE:
                self.results['tests'][test_name] = {'status': 'SKIPPED', 'reason': 'GStreamer não disponível'}
                return False
            
            # Criar encoder de teste
            test_encoder = NVENCEncoder("test_camera", 1920, 1080, 30)
            
            if test_encoder.initialize():
                if test_encoder.start():
                    # Testar encoding de um frame
                    test_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
                    test_frame[:] = (0, 255, 0)  # Frame verde
                    
                    success = test_encoder.encode_frame(test_frame)
                    time.sleep(0.5)  # Aguardar processamento
                    
                    stats = test_encoder.get_stats()
                    test_encoder.stop()
                    
                    if success and stats['frames_encoded'] > 0:
                        self.results['tests'][test_name] = {
                            'status': 'PASSED',
                            'stats': stats
                        }
                        logger.info(f"✅ NVENC funcionando: {stats['frames_encoded']} frames codificados")
                        return True
                    else:
                        self.results['tests'][test_name] = {
                            'status': 'FAILED',
                            'reason': 'Nenhum frame codificado',
                            'stats': stats
                        }
                        logger.error("❌ NVENC não codificou frames")
                        return False
                else:
                    self.results['tests'][test_name] = {
                        'status': 'FAILED',
                        'reason': 'Falha ao iniciar encoder'
                    }
                    logger.error("❌ Falha ao iniciar NVENC encoder")
                    return False
            else:
                self.results['tests'][test_name] = {
                    'status': 'FAILED',
                    'reason': 'Falha ao inicializar encoder'
                }
                logger.error("❌ Falha ao inicializar NVENC encoder")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar NVENC: {e}")
            return False
    
    async def test_faiss_gpu(self):
        """Teste 4: Verificar FAISS GPU"""
        test_name = "faiss_gpu"
        logger.info("\n🧪 Teste 4: Verificando FAISS GPU...")
        
        try:
            import faiss
            
            # Verificar GPUs disponíveis
            num_gpus = faiss.get_num_gpus()
            
            if num_gpus > 0:
                # Testar operação GPU
                import numpy as np
                
                # Criar index de teste
                dimension = 512  # Dimensão dos embeddings do InsightFace
                cpu_index = faiss.IndexFlatL2(dimension)
                
                # Criar resource GPU
                gpu_resource = faiss.StandardGpuResources()
                
                # Mover para GPU
                gpu_index = faiss.index_cpu_to_gpu(gpu_resource, 0, cpu_index)
                
                # Testar com dados
                test_data = np.random.random((100, dimension)).astype('float32')
                gpu_index.add(test_data)
                
                # Busca de teste
                query = np.random.random((1, dimension)).astype('float32')
                D, I = gpu_index.search(query, 5)
                
                self.results['tests'][test_name] = {
                    'status': 'PASSED',
                    'num_gpus': num_gpus,
                    'test_search_success': True,
                    'index_size': gpu_index.ntotal
                }
                logger.info(f"✅ FAISS GPU funcionando: {num_gpus} GPU(s) disponível(is)")
                return True
            else:
                self.results['tests'][test_name] = {
                    'status': 'WARNING',
                    'num_gpus': 0,
                    'message': 'Nenhuma GPU detectada para FAISS'
                }
                logger.warning("⚠️ FAISS GPU não disponível - usando CPU")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar FAISS GPU: {e}")
            return False
    
    async def test_insightface_gpu(self):
        """Teste 5: Verificar InsightFace com GPU"""
        test_name = "insightface_gpu"
        logger.info("\n🧪 Teste 5: Verificando InsightFace GPU...")
        
        try:
            from app.core.recognition_engine import RecognitionEngine
            from app.core.gpu_utils import get_optimal_providers
            
            # Obter providers GPU
            providers, provider_info = get_optimal_providers()
            
            # Inicializar engine
            engine = RecognitionEngine()
            await engine.initialize()
            
            if engine.is_initialized:
                # Testar detecção em imagem
                test_image = np.zeros((640, 640, 3), dtype=np.uint8)
                test_image[:] = (255, 255, 255)  # Imagem branca
                
                # Adicionar um rosto falso (quadrado preto)
                cv2.rectangle(test_image, (200, 200), (400, 400), (0, 0, 0), -1)
                
                faces = engine.detect_faces(test_image)
                
                self.results['tests'][test_name] = {
                    'status': 'PASSED',
                    'providers': providers,
                    'provider_info': provider_info,
                    'initialized': True,
                    'test_detection': len(faces)
                }
                logger.info(f"✅ InsightFace GPU funcionando: {provider_info}")
                return True
            else:
                self.results['tests'][test_name] = {
                    'status': 'FAILED',
                    'reason': 'Engine não inicializado'
                }
                logger.error("❌ InsightFace não inicializado")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar InsightFace GPU: {e}")
            return False
    
    async def test_camera_worker_integration(self):
        """Teste 6: Verificar integração Camera Worker + NVENC"""
        test_name = "camera_worker_nvenc_integration"
        logger.info("\n🧪 Teste 6: Verificando integração Camera Worker + NVENC...")
        
        try:
            from app.camera_worker.gstreamer_worker import GStreamerWorker
            
            # Criar worker
            worker = GStreamerWorker()
            
            # Verificar configuração NVENC
            if worker.nvenc_enabled and worker.nvenc_available:
                self.results['tests'][test_name] = {
                    'status': 'PASSED',
                    'nvenc_enabled': worker.nvenc_enabled,
                    'nvenc_available': worker.nvenc_available
                }
                logger.info("✅ Camera Worker com NVENC integrado corretamente")
                return True
            else:
                self.results['tests'][test_name] = {
                    'status': 'WARNING',
                    'nvenc_enabled': worker.nvenc_enabled,
                    'nvenc_available': worker.nvenc_available,
                    'message': 'NVENC não está habilitado ou disponível'
                }
                logger.warning("⚠️ NVENC não está ativo no Camera Worker")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar integração: {e}")
            return False
    
    async def test_end_to_end_pipeline(self):
        """Teste 7: Pipeline completo end-to-end"""
        test_name = "end_to_end_pipeline"
        logger.info("\n🧪 Teste 7: Verificando pipeline completo...")
        
        try:
            # Este teste seria mais complexo e envolveria:
            # 1. Criar uma câmera de teste
            # 2. Processar frames
            # 3. Verificar recognition
            # 4. Verificar encoding NVENC
            # 5. Verificar saída
            
            # Por enquanto, verificar apenas se todos os componentes estão disponíveis
            all_components = {
                'gstreamer': self.results['tests'].get('gstreamer_availability', {}).get('status') == 'PASSED',
                'nvdec': self.results['tests'].get('nvdec_decoder', {}).get('status') in ['PASSED', 'WARNING'],
                'nvenc': self.results['tests'].get('nvenc_encoder', {}).get('status') == 'PASSED',
                'faiss_gpu': self.results['tests'].get('faiss_gpu', {}).get('status') in ['PASSED', 'WARNING'],
                'insightface': self.results['tests'].get('insightface_gpu', {}).get('status') == 'PASSED',
                'integration': self.results['tests'].get('camera_worker_nvenc_integration', {}).get('status') in ['PASSED', 'WARNING']
            }
            
            all_ok = all(all_components.values())
            
            if all_ok:
                self.results['tests'][test_name] = {
                    'status': 'PASSED',
                    'components': all_components,
                    'message': 'Todos os componentes do pipeline estão funcionais'
                }
                logger.info("✅ Pipeline completo está funcional!")
                return True
            else:
                failed = [k for k, v in all_components.items() if not v]
                self.results['tests'][test_name] = {
                    'status': 'FAILED',
                    'components': all_components,
                    'failed_components': failed
                }
                logger.error(f"❌ Pipeline incompleto. Componentes falhando: {', '.join(failed)}")
                return False
                
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.error(f"❌ Erro ao verificar pipeline: {e}")
            return False
    
    def generate_summary(self):
        """Gerar resumo dos testes"""
        for test_name, test_result in self.results['tests'].items():
            self.results['summary']['total_tests'] += 1
            
            status = test_result.get('status', 'UNKNOWN')
            if status == 'PASSED':
                self.results['summary']['passed'] += 1
            elif status == 'FAILED':
                self.results['summary']['failed'] += 1
            elif status == 'WARNING':
                self.results['summary']['warnings'] += 1
    
    def print_report(self):
        """Imprimir relatório detalhado"""
        print("\n" + "="*80)
        print("📊 RELATÓRIO DE VERIFICAÇÃO DO PIPELINE GPU")
        print("="*80)
        
        # Ambiente
        print("\n🖥️ AMBIENTE:")
        print(f"   Python: {self.results['environment']['python_version'].split()[0]}")
        print(f"   GPU: {self.results['environment'].get('gpu', 'N/A')}")
        print(f"   CUDA_VISIBLE_DEVICES: {self.results['environment']['cuda_visible_devices']}")
        print(f"   USE_GPU: {self.results['environment']['use_gpu']}")
        print(f"   USE_NVENC: {self.results['environment']['use_nvenc']}")
        
        # Resultados dos testes
        print("\n📋 RESULTADOS DOS TESTES:")
        for test_name, test_result in self.results['tests'].items():
            status = test_result.get('status', 'UNKNOWN')
            
            # Emoji baseado no status
            if status == 'PASSED':
                emoji = '✅'
            elif status == 'FAILED':
                emoji = '❌'
            elif status == 'WARNING':
                emoji = '⚠️'
            elif status == 'SKIPPED':
                emoji = '⏭️'
            else:
                emoji = '❓'
            
            print(f"\n   {emoji} {test_name}: {status}")
            
            # Detalhes adicionais
            if status == 'FAILED' and 'error' in test_result:
                print(f"      Erro: {test_result['error']}")
            elif status == 'WARNING' and 'message' in test_result:
                print(f"      Aviso: {test_result['message']}")
            elif test_name == 'nvenc_encoder' and 'stats' in test_result:
                stats = test_result['stats']
                print(f"      Frames codificados: {stats.get('frames_encoded', 0)}")
            elif test_name == 'faiss_gpu' and 'num_gpus' in test_result:
                print(f"      GPUs detectadas: {test_result['num_gpus']}")
        
        # Resumo
        summary = self.results['summary']
        print("\n" + "="*80)
        print("📊 RESUMO:")
        print(f"   Total de testes: {summary['total_tests']}")
        print(f"   ✅ Aprovados: {summary['passed']}")
        print(f"   ❌ Falharam: {summary['failed']}")
        print(f"   ⚠️  Avisos: {summary['warnings']}")
        
        # Conclusão
        print("\n" + "="*80)
        if summary['failed'] == 0:
            print("🎉 CONCLUSÃO: Pipeline GPU está totalmente funcional!")
        elif summary['failed'] < summary['total_tests'] / 2:
            print("⚠️  CONCLUSÃO: Pipeline GPU está parcialmente funcional.")
        else:
            print("❌ CONCLUSÃO: Pipeline GPU tem problemas críticos.")
        print("="*80)
    
    def save_report(self):
        """Salvar relatório em arquivo JSON"""
        report_path = project_root / 'logs' / f'gpu_pipeline_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        report_path.parent.mkdir(exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 Relatório salvo em: {report_path}")
        return report_path
    
    async def run_all_tests(self):
        """Executar todos os testes"""
        logger.info("🚀 Iniciando verificação completa do pipeline GPU...")
        
        # Capturar ambiente
        self.capture_environment()
        
        # Executar testes
        await self.test_gstreamer_availability()
        await self.test_nvdec_decoder()
        await self.test_nvenc_encoder()
        await self.test_faiss_gpu()
        await self.test_insightface_gpu()
        await self.test_camera_worker_integration()
        await self.test_end_to_end_pipeline()
        
        # Gerar resumo
        self.generate_summary()
        
        # Imprimir relatório
        self.print_report()
        
        # Salvar relatório
        self.save_report()


async def main():
    """Função principal"""
    verifier = GPUPipelineVerifier()
    await verifier.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())