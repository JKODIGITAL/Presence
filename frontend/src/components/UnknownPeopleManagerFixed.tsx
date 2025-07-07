/**
 * UnknownPeopleManagerFixed - Versão corrigida e simplificada
 */

import React, { useState, useEffect, useRef } from 'react';
import { ApiService, UnknownPerson } from '../services/api';
import {
  CogIcon,
  MagnifyingGlassIcon,
  AdjustmentsHorizontalIcon,
  UserGroupIcon,
  ClockIcon,
  CheckIcon,
  PhotoIcon,
  ArrowPathIcon,
  XMarkIcon,
  ChartBarIcon
} from '@heroicons/react/24/outline';
import { toast } from 'react-hot-toast';

interface ConfigData {
  face_quality_rules: {
    min_face_width: number;
    min_face_height: number;
    min_face_area_ratio: number;
    max_similarity_threshold: number;
    min_detection_confidence: number;
    max_face_angle: number;
    min_brightness: number;
    max_brightness: number;
    min_sharpness: number;
  };
  temporal_rules: {
    min_presence_duration: number;
    min_frame_count: number;
    cooldown_period: number;
    face_tracking_timeout: number;
    max_detection_attempts: number;
  };
  system_settings?: {
    unknown_threshold: number;
    max_unknowns_per_session: number;
    auto_cleanup_days: number;
    unknown_images_dir: string;
  };
}

interface StatsData {
  totals: {
    total: number;
    pending: number;
    identified: number;
    ignored: number;
  };
}

const UnknownPeopleManagerFixed: React.FC = () => {
  const [unknownPeople, setUnknownPeople] = useState<UnknownPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const configUpdateTimeout = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (configUpdateTimeout.current) {
        clearTimeout(configUpdateTimeout.current);
      }
    };
  }, []);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      await Promise.all([
        loadUnknownPeople(),
        loadConfig(),
        loadStats()
      ]);
    } finally {
      setLoading(false);
    }
  };

  const loadUnknownPeople = async () => {
    try {
      const response = await ApiService.getUnknownPeople();
      setUnknownPeople(response.unknown_people || []);
    } catch (err) {
      console.error('Erro ao carregar pessoas desconhecidas:', err);
      toast.error('Erro ao carregar pessoas desconhecidas');
    }
  };

  const loadConfig = async () => {
    try {
      const apiUrl = 'http://localhost:17234';
      const response = await fetch(`${apiUrl}/api/v1/unknown-detection/config`);
      if (response.ok) {
        const configData = await response.json();
        setConfig(configData);
      }
    } catch (err) {
      console.error('Erro ao carregar configuração:', err);
    }
  };

  const loadStats = async () => {
    try {
      const apiUrl = 'http://localhost:17234';
      const response = await fetch(`${apiUrl}/api/v1/unknown-detection/stats`);
      if (response.ok) {
        const statsData = await response.json();
        setStats(statsData);
      }
    } catch (err) {
      console.error('Erro ao carregar estatísticas:', err);
    }
  };

  const updateConfigValue = (section: string, key: string, value: number) => {
    if (!config) return;

    // Atualizar estado local imediatamente para feedback visual
    const updatedConfig = { ...config };
    (updatedConfig as any)[section][key] = value;
    setConfig(updatedConfig);

    // Debounce para evitar muitas chamadas à API
    clearTimeout(configUpdateTimeout.current);
    configUpdateTimeout.current = setTimeout(() => {
      saveConfigToServer(updatedConfig);
    }, 500);
  };

  const saveConfigToServer = async (configToSave: ConfigData) => {
    try {
      const apiUrl = 'http://localhost:17234';
      
      // Debug: Log da estrutura enviada
      console.log('Salvando configuração:', JSON.stringify(configToSave, null, 2));
      
      const response = await fetch(`${apiUrl}/api/v1/unknown-detection/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(configToSave),
      });

      if (response.ok) {
        const result = await response.json();
        console.log('Resposta da API:', result);
        toast.success('Configuração salva!');
      } else {
        const errorText = await response.text();
        console.error('Erro na API:', response.status, errorText);
        toast.error(`Erro ao salvar configuração: ${response.status}`);
        // Recarregar config em caso de erro
        loadConfig();
      }
    } catch (err) {
      console.error('Erro de rede:', err);
      toast.error('Erro ao salvar configuração');
      // Recarregar config em caso de erro
      loadConfig();
    }
  };

  const filteredPeople = unknownPeople.filter(person =>
    person.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (person.camera_id && person.camera_id.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-[var(--bg-card-hover)] rounded-lg w-1/3"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-64 bg-[var(--bg-card-hover)] rounded-lg"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-main)] flex items-center gap-3">
            <div className="p-2 rounded-lg bg-gradient-to-br from-orange-500 to-red-500 shadow-lg">
              <UserGroupIcon className="w-6 h-6 text-white" />
            </div>
            Pessoas Desconhecidas
          </h2>
          <p className="text-[var(--text-secondary)] mt-1">
            Gerencie e identifique pessoas detectadas pelo sistema
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => setShowConfig(!showConfig)}
            className="btn btn-secondary flex items-center gap-2"
          >
            <CogIcon className="w-4 h-4" />
            Configurações
          </button>
          <button
            onClick={loadData}
            className="btn btn-primary flex items-center gap-2"
          >
            <ArrowPathIcon className="w-4 h-4" />
            Atualizar
          </button>
        </div>
      </div>

      {/* Estatísticas */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[var(--text-secondary)] text-sm font-medium">Total</p>
                <p className="text-2xl font-bold text-[var(--text-main)]">{stats.totals.total}</p>
              </div>
              <div className="p-3 rounded-full bg-blue-100 text-blue-600">
                <UserGroupIcon className="w-6 h-6" />
              </div>
            </div>
          </div>
          
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[var(--text-secondary)] text-sm font-medium">Pendentes</p>
                <p className="text-2xl font-bold text-orange-600">{stats.totals.pending}</p>
              </div>
              <div className="p-3 rounded-full bg-orange-100 text-orange-600">
                <ClockIcon className="w-6 h-6" />
              </div>
            </div>
          </div>
          
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[var(--text-secondary)] text-sm font-medium">Identificadas</p>
                <p className="text-2xl font-bold text-green-600">{stats.totals.identified}</p>
              </div>
              <div className="p-3 rounded-full bg-green-100 text-green-600">
                <CheckIcon className="w-6 h-6" />
              </div>
            </div>
          </div>
          
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[var(--text-secondary)] text-sm font-medium">Sistema</p>
                <p className="text-2xl font-bold text-[var(--primary)]">Online</p>
              </div>
              <div className="p-3 rounded-full bg-blue-100 text-[var(--primary)]">
                <ChartBarIcon className="w-6 h-6" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Configurações */}
      {showConfig && config && (
        <div className="card p-6 border border-[var(--border)]">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-[var(--text-main)] flex items-center gap-2">
              <AdjustmentsHorizontalIcon className="w-5 h-5 text-[var(--primary)]" />
              Configurações de Detecção
            </h3>
            <button
              onClick={() => setShowConfig(false)}
              className="btn btn-primary text-sm"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Qualidade Facial */}
            <div className="space-y-4">
              <h4 className="font-semibold text-[var(--text-main)] border-b border-[var(--border)] pb-2">
                Qualidade Facial
              </h4>
              
              <div>
                <label className="form-label">
                  Threshold de Similaridade ({(config.face_quality_rules.max_similarity_threshold * 100).toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="0.8"
                  step="0.05"
                  className="w-full slider-primary"
                  value={config.face_quality_rules.max_similarity_threshold}
                  onChange={(e) => updateConfigValue('face_quality_rules', 'max_similarity_threshold', parseFloat(e.target.value))}
                />
                <div className="flex justify-between text-xs text-[var(--text-secondary)] mt-1">
                  <span>10%</span>
                  <span>Faces com similaridade abaixo deste valor serão consideradas desconhecidas</span>
                  <span>80%</span>
                </div>
              </div>

              <div>
                <label className="form-label">
                  Confiança de Detecção ({(config.face_quality_rules.min_detection_confidence * 100).toFixed(0)}%)
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="0.95"
                  step="0.05"
                  className="w-full slider-primary"
                  value={config.face_quality_rules.min_detection_confidence}
                  onChange={(e) => updateConfigValue('face_quality_rules', 'min_detection_confidence', parseFloat(e.target.value))}
                />
                <div className="flex justify-between text-xs text-[var(--text-secondary)] mt-1">
                  <span>50%</span>
                  <span>Confiança mínima para aceitar detecção</span>
                  <span>95%</span>
                </div>
              </div>

              <div>
                <label className="form-label">
                  Tamanho Mínimo da Face ({config.face_quality_rules.min_face_width}x{config.face_quality_rules.min_face_height}px)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="range"
                    min="50"
                    max="200"
                    step="10"
                    className="slider-primary"
                    value={config.face_quality_rules.min_face_width}
                    onChange={(e) => updateConfigValue('face_quality_rules', 'min_face_width', parseInt(e.target.value))}
                  />
                  <input
                    type="range"
                    min="50"
                    max="200"
                    step="10"
                    className="slider-primary"
                    value={config.face_quality_rules.min_face_height}
                    onChange={(e) => updateConfigValue('face_quality_rules', 'min_face_height', parseInt(e.target.value))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-[var(--text-secondary)] mt-1">
                  <span>Largura: 50-200px</span>
                  <span>Altura: 50-200px</span>
                </div>
              </div>

              {config.face_quality_rules.max_face_angle !== undefined && (
                <div>
                  <label className="form-label">
                    Ângulo Máximo da Face ({config.face_quality_rules.max_face_angle.toFixed(0)}°)
                  </label>
                  <input
                    type="range"
                    min="10"
                    max="45"
                    step="5"
                    className="w-full slider-primary"
                    value={config.face_quality_rules.max_face_angle}
                    onChange={(e) => updateConfigValue('face_quality_rules', 'max_face_angle', parseFloat(e.target.value))}
                  />
                  <div className="flex justify-between text-xs text-[var(--text-secondary)] mt-1">
                    <span>10°</span>
                    <span>Máximo ângulo de inclinação aceito</span>
                    <span>45°</span>
                  </div>
                </div>
              )}
            </div>

            {/* Critérios Temporais */}
            <div className="space-y-4">
              <h4 className="font-semibold text-[var(--text-main)] border-b border-[var(--border)] pb-2">
                Critérios Temporais
              </h4>
              
              <div>
                <label className="form-label">
                  Tempo Mínimo de Presença ({config.temporal_rules.min_presence_duration}s)
                </label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="0.5"
                  className="w-full slider-primary"
                  value={config.temporal_rules.min_presence_duration}
                  onChange={(e) => updateConfigValue('temporal_rules', 'min_presence_duration', parseFloat(e.target.value))}
                />
                <div className="flex justify-between text-xs text-[var(--text-secondary)] mt-1">
                  <span>1s</span>
                  <span>Tempo mínimo que a face deve permanecer visível</span>
                  <span>10s</span>
                </div>
              </div>

              <div>
                <label className="form-label">
                  Frames Mínimos ({config.temporal_rules.min_frame_count})
                </label>
                <input
                  type="range"
                  min="5"
                  max="30"
                  step="1"
                  className="w-full slider-primary"
                  value={config.temporal_rules.min_frame_count}
                  onChange={(e) => updateConfigValue('temporal_rules', 'min_frame_count', parseInt(e.target.value))}
                />
                <div className="flex justify-between text-xs text-[var(--text-secondary)] mt-1">
                  <span>5</span>
                  <span>Número mínimo de frames com a mesma face</span>
                  <span>30</span>
                </div>
              </div>

              <div>
                <label className="form-label">
                  Período de Cooldown ({config.temporal_rules.cooldown_period}s)
                </label>
                <input
                  type="range"
                  min="30"
                  max="300"
                  step="30"
                  className="w-full slider-primary"
                  value={config.temporal_rules.cooldown_period}
                  onChange={(e) => updateConfigValue('temporal_rules', 'cooldown_period', parseFloat(e.target.value))}
                />
                <div className="flex justify-between text-xs text-[var(--text-secondary)] mt-1">
                  <span>30s</span>
                  <span>Intervalo entre detecções da mesma face</span>
                  <span>5min</span>
                </div>
              </div>
            </div>
          </div>

          {/* Botões de Ação */}
          <div className="mt-6 flex justify-between items-center">
            <div className="text-sm text-[var(--text-secondary)] flex items-center gap-2">
              💡 Configurações são salvas automaticamente
            </div>
            <div className="flex gap-2">
              <button
                onClick={loadConfig}
                className="btn btn-secondary text-sm flex items-center gap-2"
              >
                <ArrowPathIcon className="w-4 h-4" />
                Recarregar
              </button>
              <button
                onClick={() => setShowConfig(false)}
                className="btn btn-primary text-sm flex items-center gap-2"
              >
                <XMarkIcon className="w-4 h-4" />
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Busca */}
      <div className="card p-4">
        <div className="relative">
          <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-[var(--text-secondary)]" />
          <input
            type="text"
            placeholder="Buscar por ID ou câmera..."
            className="form-input pl-10"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Lista de Pessoas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredPeople.map((person) => (
          <div key={person.id} className="card p-4 border border-[var(--border)]">
            {/* Imagem */}
            <div className="aspect-square bg-[var(--bg-card-hover)] rounded-lg mb-3 overflow-hidden">
              {person.image_data ? (
                <img
                  src={`data:image/jpeg;base64,${person.image_data}`}
                  alt={`Desconhecido ${person.id}`}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <PhotoIcon className="w-12 h-12 text-[var(--text-muted)]" />
                </div>
              )}
            </div>

            {/* Informações */}
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-[var(--text-secondary)]">ID:</span>
                <span className="ml-2 font-mono text-[var(--text-main)]">
                  {person.id.slice(-8)}
                </span>
              </div>
              
              <div>
                <span className="text-[var(--text-secondary)]">Detectado:</span>
                <span className="ml-2 text-[var(--text-main)]">
                  {new Date(person.detected_at).toLocaleDateString('pt-BR')}
                </span>
              </div>
              
              {person.quality_score && (
                <div>
                  <span className="text-[var(--text-secondary)]">Qualidade:</span>
                  <span className="ml-2 text-[var(--text-main)]">
                    {(person.quality_score * 100).toFixed(1)}%
                  </span>
                </div>
              )}
              
              <div>
                <span className="text-[var(--text-secondary)]">Câmera:</span>
                <span className="ml-2 text-[var(--text-main)]">
                  {person.camera_id}
                </span>
              </div>

              <div className={`badge ${
                person.status === 'pending' ? 'badge-yellow' :
                person.status === 'identified' ? 'badge-green' :
                'badge-gray'
              }`}>
                {person.status === 'pending' ? 'Pendente' :
                 person.status === 'identified' ? 'Identificada' :
                 'Ignorada'}
              </div>
            </div>
          </div>
        ))}
      </div>

      {filteredPeople.length === 0 && !loading && (
        <div className="text-center py-12">
          <UserGroupIcon className="w-16 h-16 text-[var(--text-muted)] mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-[var(--text-main)] mb-2">
            Nenhuma pessoa desconhecida encontrada
          </h3>
          <p className="text-[var(--text-secondary)]">
            O sistema ainda não detectou pessoas desconhecidas
          </p>
        </div>
      )}
    </div>
  );
};

export default UnknownPeopleManagerFixed;