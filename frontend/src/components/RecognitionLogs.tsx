import React, { useState, useEffect } from 'react';
import { ApiService, RecognitionLog } from '../services/api';
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  EyeIcon
} from '@heroicons/react/24/outline';

const RecognitionLogs: React.FC = () => {
  const [logs, setLogs] = useState<RecognitionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLog, setSelectedLog] = useState<RecognitionLog | null>(null);

  // Filters
  const [filterCamera, setFilterCamera] = useState('');
  const [filterPerson, setFilterPerson] = useState('');
  const [filterUnknown, setFilterUnknown] = useState<boolean | undefined>(undefined);
  const [filterDate, setFilterDate] = useState('');

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const itemsPerPage = 20;

  useEffect(() => {
    loadLogs();
  }, [currentPage, filterCamera, filterPerson, filterUnknown, filterDate]);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const params: any = {
        skip: (currentPage - 1) * itemsPerPage,
        limit: itemsPerPage,
      };

      if (filterCamera) params.camera_id = filterCamera;
      if (filterPerson) params.person_id = filterPerson;
      if (filterUnknown !== undefined) params.is_unknown = filterUnknown;
      if (filterDate) {
        const startDate = new Date(filterDate);
        const endDate = new Date(filterDate);
        endDate.setHours(23, 59, 59, 999);
        params.start_date = startDate.toISOString();
        params.end_date = endDate.toISOString();
      }

      const response = await ApiService.getRecognitionLogs(params);
      setLogs(response.logs);
      setTotalPages(Math.ceil(response.total / itemsPerPage));
      setError(null);
    } catch (err) {
      console.error('Erro ao carregar logs:', err);
      setError('Erro ao carregar logs de reconhecimento');
    } finally {
      setLoading(false);
    }
  };

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString('pt-BR');
  };

  const formatConfidence = (confidence: number) => {
    return `${(confidence * 100).toFixed(1)}%`;
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-[var(--success)]';
    if (confidence >= 0.6) return 'text-yellow-600';
    return 'text-[var(--danger)]';
  };

  const clearFilters = () => {
    setFilterCamera('');
    setFilterPerson('');
    setFilterUnknown(undefined);
    setFilterDate('');
    setCurrentPage(1);
  };

  if (loading && logs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center">
            <ExclamationTriangleIcon className="w-6 h-6 text-red-500 mr-3" />
            <div>
              <h3 className="text-red-800 font-medium">Erro</h3>
              <p className="text-red-600 text-sm">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-main)]">Logs de Reconhecimento</h2>
          <p className="text-[var(--text-secondary)]">Histórico de todas as detecções</p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={loadLogs}
            className="btn btn-primary flex items-center"
          >
            <ArrowPathIcon className="w-4 h-4 mr-2" />
            Atualizar
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-6">
        <h3 className="text-lg font-semibold mb-4 text-[var(--text-main)]">Filtros</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-[var(--text-main)] mb-2">
              Filtrar por data
            </label>
            <input
              type="date"
              value={filterDate}
              onChange={(e) => setFilterDate(e.target.value)}
              className="form-input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--text-main)] mb-2">
              Tipo de reconhecimento
            </label>
            <select
              value={filterUnknown === undefined ? '' : filterUnknown ? 'true' : 'false'}
              onChange={(e) => {
                if (e.target.value === '') {
                  setFilterUnknown(undefined);
                } else {
                  setFilterUnknown(e.target.value === 'true');
                }
              }}
              className="form-input"
            >
              <option value="">Todos</option>
              <option value="false">Pessoas conhecidas</option>
              <option value="true">Pessoas desconhecidas</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--text-main)] mb-2">
              Câmera
            </label>
            <input
              type="text"
              value={filterCamera}
              onChange={(e) => setFilterCamera(e.target.value)}
              className="form-input"
              placeholder="ID da câmera"
            />
          </div>

          <div className="flex items-end">
            <button
              onClick={clearFilters}
              className="btn btn-secondary w-full"
            >
              Limpar Filtros
            </button>
          </div>
        </div>
      </div>

      {/* Logs Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[var(--border)]">
            <thead className="bg-[var(--bg-main)]">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Data/Hora
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Pessoa
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Câmera
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Confiança
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="bg-[var(--bg-card)] divide-y divide-[var(--border)]">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-[var(--primary)]/5">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-[var(--text-main)]">
                    {formatDateTime(log.timestamp)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-[var(--text-main)]">
                      {log.person_name || 'Desconhecido'}
                    </div>
                    <div className="text-sm text-[var(--text-secondary)]">
                      {log.person_id}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-[var(--text-main)]">
                    {log.camera_name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`text-sm font-medium ${getConfidenceColor(log.confidence)}`}>
                      {formatConfidence(log.confidence)}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                      log.is_unknown 
                        ? 'bg-yellow-100 text-yellow-800' 
                        : 'bg-[var(--success)]/20 text-[var(--success)]'
                    }`}>
                      {log.is_unknown ? 'Desconhecido' : 'Conhecido'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <div className="flex space-x-2">
                      <button
                        onClick={() => setSelectedLog(log)}
                        className="text-[var(--primary)] hover:text-[var(--primary)]/80"
                      >
                        <EyeIcon className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-[var(--text-secondary)]">
            Página {currentPage} de {totalPages}
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="btn btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Anterior
            </button>
            <button
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className="btn btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Próxima
            </button>
          </div>
        </div>
      )}

      {/* Log Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-[var(--bg-card)] rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold mb-4 text-[var(--text-main)]">Detalhes do Reconhecimento</h3>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Foto do Reconhecimento */}
              <div className="space-y-3">
                <label className="text-sm font-medium text-[var(--text-secondary)]">Foto do Reconhecimento:</label>
                <div className="aspect-video bg-gray-100 rounded-lg overflow-hidden">
                  {selectedLog.frame_path ? (
                    <img
                      src={`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:17234'}/data/frames/${selectedLog.frame_path}`}
                      alt="Frame do reconhecimento"
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        // Fallback se não conseguir carregar a imagem
                        (e.target as HTMLImageElement).src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgdmlld0JveD0iMCAwIDMyMCAxODAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIiBmaWxsPSIjRjNGNEY2Ii8+CjxwYXRoIGQ9Ik0xNDQuNSA5MEM0NC41IDkwIDQ0LjUgOTAgMTQ0LjUgOTBaIiBzdHJva2U9IiM5Q0EzQUYiIHN0cm9rZS13aWR0aD0iMiIvPgo8L3N2Zz4K';
                      }}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                      <div className="text-center">
                        <div className="text-4xl mb-2">📷</div>
                        <p>Imagem não disponível</p>
                      </div>
                    </div>
                  )}
                </div>
                
                {/* Bounding Box Info */}
                {selectedLog.bounding_box && (
                  <div>
                    <label className="text-sm font-medium text-[var(--text-secondary)]">Posição da Face:</label>
                    <p className="text-xs text-[var(--text-main)] font-mono">
                      {selectedLog.bounding_box}
                    </p>
                  </div>
                )}
              </div>

              {/* Informações do Reconhecimento */}
              <div className="space-y-3">
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)]">Pessoa:</label>
                  <p className="text-[var(--text-main)] font-medium">{selectedLog.person_name || 'Desconhecido'}</p>
                  {selectedLog.person_id && (
                    <p className="text-xs text-[var(--text-secondary)]">ID: {selectedLog.person_id}</p>
                  )}
                </div>
                
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)]">Câmera:</label>
                  <p className="text-[var(--text-main)]">{selectedLog.camera_name}</p>
                </div>
                
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)]">Confiança:</label>
                  <div className="flex items-center gap-2">
                    <p className={`font-medium ${getConfidenceColor(selectedLog.confidence)}`}>
                      {formatConfidence(selectedLog.confidence)}
                    </p>
                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                      <div 
                        className={`h-2 rounded-full ${
                          selectedLog.confidence >= 0.8 ? 'bg-green-500' :
                          selectedLog.confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${selectedLog.confidence * 100}%` }}
                      ></div>
                    </div>
                  </div>
                </div>
                
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)]">Data/Hora:</label>
                  <p className="text-[var(--text-main)]">{formatDateTime(selectedLog.timestamp)}</p>
                </div>
                
                <div>
                  <label className="text-sm font-medium text-[var(--text-secondary)]">Status:</label>
                  <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                    selectedLog.is_unknown 
                      ? 'bg-yellow-100 text-yellow-800' 
                      : 'bg-[var(--success)]/20 text-[var(--success)]'
                  }`}>
                    {selectedLog.is_unknown ? 'Desconhecido' : 'Conhecido'}
                  </span>
                </div>
              </div>
            </div>
            
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setSelectedLog(null)}
                className="btn btn-secondary"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RecognitionLogs;