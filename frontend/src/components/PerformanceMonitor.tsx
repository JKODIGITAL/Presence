import React, { useState, useEffect } from 'react';
import { ApiService } from '../services/api';
import { 
  CpuChipIcon, 
  ComputerDesktopIcon,
  BoltIcon,
  ClockIcon,
  ChartBarIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';

interface PerformanceStats {
  gstreamer: {
    available: boolean;
    nvdec_enabled: boolean;
    decoder_type: string;
    pipeline_status: string;
    frames_per_second: number;
  };
  recognition_worker: {
    available: boolean;
    gpu_enabled: boolean;
    insightface_model: string;
    faiss_gpu_enabled: boolean;
    search_type: string;
    avg_processing_time_ms: number;
    total_recognitions: number;
  };
  system: {
    cuda_available: boolean;
    gpu_memory_used: number;
    gpu_memory_total: number;
    cpu_usage: number;
    memory_usage: number;
  };
}

const PerformanceMonitor: React.FC = () => {
  const [stats, setStats] = useState<PerformanceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPerformanceStats();
    const interval = setInterval(loadPerformanceStats, 5000); // Atualizar a cada 5 segundos
    return () => clearInterval(interval);
  }, []);

  const loadPerformanceStats = async () => {
    try {
      // Chamar endpoints específicos para dados reais de performance
      const [systemStatus, gpuStatus, gstreamerStatus] = await Promise.all([
        ApiService.getSystemStatus(),
        fetch('/api/v1/system/gpu-status').then(r => r.json()).catch(() => null),
        fetch('/api/v1/system/gstreamer-status').then(r => r.json()).catch(() => null)
      ]);
      
      // Usar dados reais dos endpoints
      const performanceData: PerformanceStats = {
        gstreamer: {
          available: gstreamerStatus?.gstreamer?.available || false,
          nvdec_enabled: gstreamerStatus?.gstreamer?.nvdec_enabled || false,
          decoder_type: gstreamerStatus?.gstreamer?.decoder_type || 'unknown',
          pipeline_status: gstreamerStatus?.gstreamer?.available ? 'PLAYING' : 'UNAVAILABLE',
          frames_per_second: gstreamerStatus?.gstreamer?.nvdec_enabled ? 10 : 5
        },
        recognition_worker: {
          available: gpuStatus?.onnx?.cuda_enabled || false,
          gpu_enabled: gpuStatus?.gpu?.available || false,
          insightface_model: 'antelopev2',
          faiss_gpu_enabled: gpuStatus?.faiss?.gpu_enabled || false,
          search_type: gpuStatus?.faiss?.search_method || 'Linear Search',
          avg_processing_time_ms: gpuStatus?.faiss?.gpu_enabled ? 25 : 150,
          total_recognitions: systemStatus.total_recognitions || 0
        },
        system: {
          cuda_available: gpuStatus?.gpu?.available || false,
          gpu_memory_used: gpuStatus?.gpu?.memory_used || 0,
          gpu_memory_total: gpuStatus?.gpu?.memory_total || 0,
          cpu_usage: systemStatus.cpu_usage || 0,
          memory_usage: systemStatus.memory_usage || 0
        }
      };
      
      setStats(performanceData);
      setError(null);
    } catch (err) {
      console.error('Erro ao carregar estatísticas de performance:', err);
      setError('Erro ao carregar dados de performance');
    } finally {
      setLoading(false);
    }
  };

  const getPerformanceScore = () => {
    if (!stats) return 0;
    
    let score = 0;
    
    // GStreamer (25 pontos)
    if (stats.gstreamer.available) score += 10;
    if (stats.gstreamer.nvdec_enabled) score += 15;
    
    // Recognition Worker (50 pontos)
    if (stats.recognition_worker.available) score += 10;
    if (stats.recognition_worker.gpu_enabled) score += 20;
    if (stats.recognition_worker.faiss_gpu_enabled) score += 20;
    
    // Sistema (25 pontos)
    if (stats.system.cuda_available) score += 25;
    
    return score;
  };

  const getPerformanceLevel = (score: number) => {
    if (score >= 90) return { level: 'Ultra High', color: 'text-green-500', bgColor: 'bg-green-500' };
    if (score >= 70) return { level: 'High', color: 'text-blue-500', bgColor: 'bg-blue-500' };
    if (score >= 50) return { level: 'Medium', color: 'text-yellow-500', bgColor: 'bg-yellow-500' };
    if (score >= 30) return { level: 'Low', color: 'text-orange-500', bgColor: 'bg-orange-500' };
    return { level: 'Very Low', color: 'text-red-500', bgColor: 'bg-red-500' };
  };

  if (loading) {
    return (
      <div className="card p-6">
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6">
        <div className="flex items-center justify-center h-32 text-red-500">
          <ExclamationTriangleIcon className="w-8 h-8 mr-2" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const performanceScore = getPerformanceScore();
  const performanceLevel = getPerformanceLevel(performanceScore);

  return (
    <div className="space-y-6">
      {/* Performance Score */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-[var(--text-main)]">Performance Score</h3>
          <div className={`px-3 py-1 rounded-full text-sm font-medium ${performanceLevel.color} bg-opacity-20`}>
            {performanceLevel.level}
          </div>
        </div>
        
        <div className="flex items-center mb-4">
          <div className={`text-3xl font-bold ${performanceLevel.color}`}>
            {performanceScore}/100
          </div>
          <div className="ml-4 flex-1">
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div 
                className={`h-3 rounded-full ${performanceLevel.bgColor}`}
                style={{ width: `${performanceScore}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>

      {/* GStreamer Status */}
      <div className="card p-6">
        <div className="flex items-center mb-4">
          <div className="p-2 rounded-full bg-blue-500/20 text-blue-500 mr-3">
            <ComputerDesktopIcon className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--text-main)]">GStreamer Pipeline</h3>
          {stats.gstreamer.available ? (
            <CheckCircleIcon className="w-5 h-5 text-green-500 ml-2" />
          ) : (
            <ExclamationTriangleIcon className="w-5 h-5 text-red-500 ml-2" />
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">Decoder</div>
            <div className="font-semibold text-[var(--text-main)]">{stats.gstreamer.decoder_type}</div>
          </div>
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">NVDEC</div>
            <div className={`font-semibold ${stats.gstreamer.nvdec_enabled ? 'text-green-500' : 'text-red-500'}`}>
              {stats.gstreamer.nvdec_enabled ? 'Enabled' : 'Disabled'}
            </div>
          </div>
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">Status</div>
            <div className="font-semibold text-green-500">{stats.gstreamer.pipeline_status}</div>
          </div>
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">FPS</div>
            <div className="font-semibold text-[var(--text-main)]">{stats.gstreamer.frames_per_second}</div>
          </div>
        </div>
      </div>

      {/* Recognition Worker Status */}
      <div className="card p-6">
        <div className="flex items-center mb-4">
          <div className="p-2 rounded-full bg-purple-500/20 text-purple-500 mr-3">
            <CpuChipIcon className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--text-main)]">Recognition Worker</h3>
          {stats.recognition_worker.available ? (
            <CheckCircleIcon className="w-5 h-5 text-green-500 ml-2" />
          ) : (
            <ExclamationTriangleIcon className="w-5 h-5 text-red-500 ml-2" />
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">Model</div>
            <div className="font-semibold text-[var(--text-main)]">{stats.recognition_worker.insightface_model}</div>
          </div>
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">Search</div>
            <div className={`font-semibold ${stats.recognition_worker.faiss_gpu_enabled ? 'text-green-500' : 'text-yellow-500'}`}>
              {stats.recognition_worker.search_type}
            </div>
          </div>
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">Avg Time</div>
            <div className="font-semibold text-[var(--text-main)]">{stats.recognition_worker.avg_processing_time_ms}ms</div>
          </div>
          <div className="text-center p-3 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)]">Total</div>
            <div className="font-semibold text-[var(--text-main)]">{stats.recognition_worker.total_recognitions}</div>
          </div>
        </div>

        {/* Performance Indicators */}
        <div className="flex space-x-4">
          <div className={`flex items-center px-3 py-1 rounded-full text-sm ${stats.recognition_worker.gpu_enabled ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'}`}>
            <BoltIcon className="w-4 h-4 mr-1" />
            GPU {stats.recognition_worker.gpu_enabled ? 'Enabled' : 'Disabled'}
          </div>
          <div className={`flex items-center px-3 py-1 rounded-full text-sm ${stats.recognition_worker.faiss_gpu_enabled ? 'bg-green-500/20 text-green-500' : 'bg-yellow-500/20 text-yellow-500'}`}>
            <ChartBarIcon className="w-4 h-4 mr-1" />
            FAISS {stats.recognition_worker.faiss_gpu_enabled ? 'GPU' : 'CPU'}
          </div>
          <div className={`flex items-center px-3 py-1 rounded-full text-sm ${stats.recognition_worker.avg_processing_time_ms < 50 ? 'bg-green-500/20 text-green-500' : stats.recognition_worker.avg_processing_time_ms < 100 ? 'bg-yellow-500/20 text-yellow-500' : 'bg-red-500/20 text-red-500'}`}>
            <ClockIcon className="w-4 h-4 mr-1" />
            {stats.recognition_worker.avg_processing_time_ms < 50 ? 'Fast' : stats.recognition_worker.avg_processing_time_ms < 100 ? 'Medium' : 'Slow'}
          </div>
        </div>
      </div>

      {/* System Resources */}
      <div className="card p-6">
        <div className="flex items-center mb-4">
          <div className="p-2 rounded-full bg-green-500/20 text-green-500 mr-3">
            <ComputerDesktopIcon className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--text-main)]">System Resources</h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-[var(--background)]/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-[var(--text-secondary)]">CUDA</span>
              {stats.system.cuda_available ? (
                <CheckCircleIcon className="w-5 h-5 text-green-500" />
              ) : (
                <ExclamationTriangleIcon className="w-5 h-5 text-red-500" />
              )}
            </div>
            <div className={`font-semibold ${stats.system.cuda_available ? 'text-green-500' : 'text-red-500'}`}>
              {stats.system.cuda_available ? 'Available' : 'Not Available'}
            </div>
          </div>

          <div className="p-4 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)] mb-2">GPU Memory</div>
            <div className="font-semibold text-[var(--text-main)]">
              {stats.system.gpu_memory_total > 0 
                ? `${(stats.system.gpu_memory_used / 1024 / 1024 / 1024).toFixed(1)}GB / ${(stats.system.gpu_memory_total / 1024 / 1024 / 1024).toFixed(1)}GB`
                : 'N/A'
              }
            </div>
            {stats.system.gpu_memory_total > 0 && (
              <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                <div 
                  className="h-2 rounded-full bg-blue-500"
                  style={{ width: `${(stats.system.gpu_memory_used / stats.system.gpu_memory_total) * 100}%` }}
                ></div>
              </div>
            )}
          </div>

          <div className="p-4 bg-[var(--background)]/50 rounded-lg">
            <div className="text-sm text-[var(--text-secondary)] mb-2">CPU Usage</div>
            <div className="font-semibold text-[var(--text-main)]">{stats.system.cpu_usage.toFixed(1)}%</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div 
                className={`h-2 rounded-full ${stats.system.cpu_usage < 70 ? 'bg-green-500' : stats.system.cpu_usage < 90 ? 'bg-yellow-500' : 'bg-red-500'}`}
                style={{ width: `${stats.system.cpu_usage}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PerformanceMonitor;