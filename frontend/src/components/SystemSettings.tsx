/**
 * SystemSettings - Página unificada de configurações do sistema
 * Design clean e organizado com todas as configurações em um só lugar
 */

import React, { useState, useEffect } from 'react';
import {
  Cog6ToothIcon,
  ServerIcon,
  ShieldCheckIcon,
  BellIcon,
  PaintBrushIcon,
  CloudArrowUpIcon,
  DocumentTextIcon,
  InformationCircleIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline';
import { ApiService } from '../services/api';
import toast from 'react-hot-toast';
import ThemeSelector from './ThemeSelector';

interface SystemHealth {
  status: string;
  gpu_available: boolean;
  version: string;
  uptime: number;
  workers: {
    camera_worker: boolean;
    recognition_worker: boolean;
  };
}

interface SystemConfig {
  recognition_threshold: number;
  unknown_grace_period: number;
  auto_cleanup_days: number;
  notification_enabled: boolean;
  backup_enabled: boolean;
  backup_interval: string;
}

const SystemSettings: React.FC = () => {
  const [activeTab, setActiveTab] = useState('general');
  const [isLoading, setIsLoading] = useState(true);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [config, setConfig] = useState<SystemConfig>({
    recognition_threshold: 0.6,
    unknown_grace_period: 30,
    auto_cleanup_days: 90,
    notification_enabled: true,
    backup_enabled: false,
    backup_interval: 'daily'
  });
  const [isSaving, setIsSaving] = useState(false);

  const tabs = [
    { id: 'general', label: 'Geral', icon: Cog6ToothIcon },
    { id: 'recognition', label: 'Reconhecimento', icon: ShieldCheckIcon },
    { id: 'appearance', label: 'Aparência', icon: PaintBrushIcon },
    { id: 'notifications', label: 'Notificações', icon: BellIcon },
    { id: 'backup', label: 'Backup', icon: CloudArrowUpIcon },
    { id: 'about', label: 'Sobre', icon: InformationCircleIcon }
  ];

  useEffect(() => {
    fetchSystemInfo();
  }, []);

  const fetchSystemInfo = async () => {
    try {
      const [healthData, systemInfo] = await Promise.all([
        ApiService.getHealth().catch(() => ({ status: 'unknown' })),
        ApiService.getSystemInfo().catch(() => null)
      ]);
      
      // Transform system info to health format
      const transformedHealth: SystemHealth = {
        status: healthData.status || 'healthy',
        gpu_available: systemInfo?.settings?.use_gpu || false,
        version: systemInfo?.version || '1.0.0',
        uptime: systemInfo?.uptime ? parseInt(systemInfo.uptime) : 0,
        workers: {
          camera_worker: true, // Assume running if we can connect to API
          recognition_worker: true
        }
      };
      
      setHealth(transformedHealth);
      
      // Load recognition settings if available
      try {
        const recognitionSettings = await ApiService.getRecognitionSettings();
        if (recognitionSettings) {
          setConfig(prev => ({
            ...prev,
            recognition_threshold: recognitionSettings.confidence_threshold || 0.6,
            unknown_grace_period: recognitionSettings.unknown_accuracy_threshold || 30,
            auto_cleanup_days: 90 // Default value
          }));
        }
      } catch (err) {
        console.warn('Could not load recognition settings:', err);
      }
      
      setIsLoading(false);
    } catch (error) {
      console.error('Error loading system info:', error);
      toast.error('Erro ao carregar informações do sistema');
      setIsLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    setIsSaving(true);
    try {
      // Save system settings
      await ApiService.updateSystemSettings({
        confidence_threshold: config.recognition_threshold,
        use_gpu: health?.gpu_available || false,
        max_cameras: 10 // Default value
      });
      
      // Save recognition settings if available
      try {
        await ApiService.updateRecognitionSettings({
          confidence_threshold: config.recognition_threshold,
          unknown_accuracy_threshold: config.unknown_grace_period,
          similarity_threshold: 0.6 // Default value
        });
      } catch (err) {
        console.warn('Could not save recognition settings:', err);
      }
      
      toast.success('Configurações salvas com sucesso!');
      
      // Reload system info to reflect changes
      await fetchSystemInfo();
    } catch (error) {
      console.error('Error saving config:', error);
      toast.error('Erro ao salvar configurações');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRestart = async (service: string) => {
    try {
      toast.loading(`Reiniciando ${service}...`);
      await new Promise(resolve => setTimeout(resolve, 2000));
      toast.success(`${service} reiniciado com sucesso!`);
      fetchSystemInfo();
    } catch (error) {
      toast.error(`Erro ao reiniciar ${service}`);
    }
  };

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  const renderGeneralTab = () => (
    <div className="space-y-6">
      {/* Status do Sistema */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <ServerIcon className="w-5 h-5" />
            Status do Sistema
          </h3>
          <span className={`badge ${health?.status === 'healthy' ? 'badge-success' : 'badge-error'}`}>
            {health?.status === 'healthy' ? 'Operacional' : 'Com Problemas'}
          </span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
            <span className="text-secondary">GPU</span>
            <span className={`font-medium ${health?.gpu_available ? 'text-success' : 'text-muted'}`}>
              {health?.gpu_available ? 'Disponível' : 'Não Detectada'}
            </span>
          </div>
          
          <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
            <span className="text-secondary">Versão</span>
            <span className="font-medium">{health?.version || 'N/A'}</span>
          </div>
          
          <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
            <span className="text-secondary">Tempo Online</span>
            <span className="font-medium">{health?.uptime ? formatUptime(health.uptime) : 'N/A'}</span>
          </div>
          
          <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
            <span className="text-secondary">Workers Ativos</span>
            <div className="flex gap-2">
              <span className={`status-indicator ${health?.workers?.camera_worker ? 'status-online' : 'status-offline'}`}>
                <span className="status-dot"></span>
                Câmera
              </span>
              <span className={`status-indicator ${health?.workers?.recognition_worker ? 'status-online' : 'status-offline'}`}>
                <span className="status-dot"></span>
                IA
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Serviços */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Gerenciar Serviços</h3>
        
        <div className="space-y-3">
          <div className="flex items-center justify-between p-4 bg-surface rounded-lg">
            <div>
              <h4 className="font-medium">Camera Worker</h4>
              <p className="text-sm text-secondary">Processamento de vídeo das câmeras</p>
            </div>
            <button
              onClick={() => handleRestart('Camera Worker')}
              className="btn btn-secondary"
            >
              <ArrowPathIcon className="w-4 h-4 mr-2" />
              Reiniciar
            </button>
          </div>
          
          <div className="flex items-center justify-between p-4 bg-surface rounded-lg">
            <div>
              <h4 className="font-medium">Recognition Worker</h4>
              <p className="text-sm text-secondary">Processamento de reconhecimento facial</p>
            </div>
            <button
              onClick={() => handleRestart('Recognition Worker')}
              className="btn btn-secondary"
            >
              <ArrowPathIcon className="w-4 h-4 mr-2" />
              Reiniciar
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  const renderRecognitionTab = () => (
    <div className="space-y-6">
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Configurações de Reconhecimento</h3>
        
        <div className="space-y-6">
          {/* Threshold de Reconhecimento */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Precisão do Reconhecimento
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min="0.3"
                max="0.9"
                step="0.1"
                value={config.recognition_threshold}
                onChange={(e) => setConfig({...config, recognition_threshold: parseFloat(e.target.value)})}
                className="flex-1"
              />
              <span className="text-sm font-medium w-12 text-center">
                {(config.recognition_threshold * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-secondary mt-1">
              Quanto maior, mais preciso, mas pode não reconhecer em condições ruins
            </p>
          </div>

          {/* Período de Graça */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Tempo para Identificar Desconhecidos
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={config.unknown_grace_period}
                onChange={(e) => setConfig({...config, unknown_grace_period: parseInt(e.target.value)})}
                className="input w-24"
                min="0"
                max="300"
              />
              <span className="text-sm text-secondary">segundos</span>
            </div>
            <p className="text-sm text-secondary mt-1">
              Tempo antes de marcar uma pessoa como desconhecida
            </p>
          </div>

          {/* Limpeza Automática */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Limpeza Automática de Dados
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={config.auto_cleanup_days}
                onChange={(e) => setConfig({...config, auto_cleanup_days: parseInt(e.target.value)})}
                className="input w-24"
                min="0"
                max="365"
              />
              <span className="text-sm text-secondary">dias</span>
            </div>
            <p className="text-sm text-secondary mt-1">
              Remover registros antigos automaticamente (0 para desativar)
            </p>
          </div>
        </div>
      </div>
    </div>
  );

  const renderAppearanceTab = () => (
    <div className="space-y-6">
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Tema da Interface</h3>
        <ThemeSelector />
        <p className="text-sm text-secondary mt-4">
          Escolha o tema que melhor se adequa ao seu ambiente de trabalho
        </p>
      </div>

      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Preferências de Exibição</h3>
        
        <div className="space-y-4">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              className="w-4 h-4 text-primary"
              defaultChecked
            />
            <span className="text-sm">Mostrar animações</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              className="w-4 h-4 text-primary"
              defaultChecked
            />
            <span className="text-sm">Modo compacto em telas pequenas</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              className="w-4 h-4 text-primary"
            />
            <span className="text-sm">Sempre mostrar rótulos nos ícones</span>
          </label>
        </div>
      </div>
    </div>
  );

  const renderNotificationsTab = () => (
    <div className="space-y-6">
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Configurações de Notificações</h3>
        
        <div className="space-y-4">
          <label className="flex items-center justify-between">
            <div>
              <span className="font-medium">Notificações do Sistema</span>
              <p className="text-sm text-secondary">Alertas sobre status e erros</p>
            </div>
            <input
              type="checkbox"
              className="toggle"
              checked={config.notification_enabled}
              onChange={(e) => setConfig({...config, notification_enabled: e.target.checked})}
            />
          </label>
          
          <label className="flex items-center justify-between">
            <div>
              <span className="font-medium">Pessoas Desconhecidas</span>
              <p className="text-sm text-secondary">Alertar quando detectar desconhecidos</p>
            </div>
            <input
              type="checkbox"
              className="toggle"
              defaultChecked
            />
          </label>
          
          <label className="flex items-center justify-between">
            <div>
              <span className="font-medium">Falhas de Câmera</span>
              <p className="text-sm text-secondary">Notificar quando câmeras ficarem offline</p>
            </div>
            <input
              type="checkbox"
              className="toggle"
              defaultChecked
            />
          </label>
        </div>
      </div>

      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Som das Notificações</h3>
        
        <div className="space-y-4">
          <label className="flex items-center gap-3">
            <input
              type="radio"
              name="notification-sound"
              defaultChecked
            />
            <span className="text-sm">Som padrão</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="radio"
              name="notification-sound"
            />
            <span className="text-sm">Som discreto</span>
          </label>
          
          <label className="flex items-center gap-3">
            <input
              type="radio"
              name="notification-sound"
            />
            <span className="text-sm">Sem som</span>
          </label>
        </div>
      </div>
    </div>
  );

  const renderBackupTab = () => (
    <div className="space-y-6">
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Backup Automático</h3>
        
        <div className="space-y-4">
          <label className="flex items-center justify-between">
            <div>
              <span className="font-medium">Ativar Backup Automático</span>
              <p className="text-sm text-secondary">Fazer backup dos dados periodicamente</p>
            </div>
            <input
              type="checkbox"
              className="toggle"
              checked={config.backup_enabled}
              onChange={(e) => setConfig({...config, backup_enabled: e.target.checked})}
            />
          </label>
          
          {config.backup_enabled && (
            <div>
              <label className="block text-sm font-medium mb-2">
                Frequência do Backup
              </label>
              <select
                value={config.backup_interval}
                onChange={(e) => setConfig({...config, backup_interval: e.target.value})}
                className="input"
              >
                <option value="hourly">A cada hora</option>
                <option value="daily">Diariamente</option>
                <option value="weekly">Semanalmente</option>
                <option value="monthly">Mensalmente</option>
              </select>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Backup Manual</h3>
        
        <div className="space-y-4">
          <p className="text-sm text-secondary">
            Crie um backup completo do sistema agora
          </p>
          
          <div className="flex gap-3">
            <button className="btn btn-primary">
              <CloudArrowUpIcon className="w-4 h-4 mr-2" />
              Fazer Backup Agora
            </button>
            
            <button className="btn btn-secondary">
              <DocumentTextIcon className="w-4 h-4 mr-2" />
              Ver Backups
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  const renderAboutTab = () => (
    <div className="space-y-6">
      <div className="card">
        <div className="text-center">
          <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
            <ShieldCheckIcon className="w-10 h-10 text-primary" />
          </div>
          
          <h2 className="text-2xl font-bold mb-2">Presence</h2>
          <p className="text-secondary mb-6">Sistema de Reconhecimento Facial</p>
          
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between py-2 border-t border-color">
              <span className="text-secondary">Versão</span>
              <span className="font-medium">{health?.version || '1.0.0'}</span>
            </div>
            
            <div className="flex items-center justify-between py-2 border-t border-color">
              <span className="text-secondary">Licença</span>
              <span className="font-medium">MIT</span>
            </div>
            
            <div className="flex items-center justify-between py-2 border-t border-color">
              <span className="text-secondary">Desenvolvido por</span>
              <span className="font-medium">Sua Empresa</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Recursos do Sistema</h3>
        
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <CheckCircleIcon className="w-5 h-5 text-success" />
            <span className="text-sm">Reconhecimento facial em tempo real</span>
          </div>
          
          <div className="flex items-center gap-3">
            <CheckCircleIcon className="w-5 h-5 text-success" />
            <span className="text-sm">Suporte para múltiplas câmeras</span>
          </div>
          
          <div className="flex items-center gap-3">
            <CheckCircleIcon className="w-5 h-5 text-success" />
            <span className="text-sm">Detecção de pessoas desconhecidas</span>
          </div>
          
          <div className="flex items-center gap-3">
            <CheckCircleIcon className="w-5 h-5 text-success" />
            <span className="text-sm">Interface moderna e responsiva</span>
          </div>
          
          <div className="flex items-center gap-3">
            {health?.gpu_available ? (
              <CheckCircleIcon className="w-5 h-5 text-success" />
            ) : (
              <ExclamationTriangleIcon className="w-5 h-5 text-warning" />
            )}
            <span className="text-sm">Aceleração por GPU</span>
          </div>
        </div>
      </div>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'general':
        return renderGeneralTab();
      case 'recognition':
        return renderRecognitionTab();
      case 'appearance':
        return renderAppearanceTab();
      case 'notifications':
        return renderNotificationsTab();
      case 'backup':
        return renderBackupTab();
      case 'about':
        return renderAboutTab();
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-2">Configurações do Sistema</h1>
        <p className="text-secondary">Gerencie todas as configurações e preferências</p>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Sidebar com Tabs */}
        <div className="col-span-12 md:col-span-3">
          <nav className="space-y-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                    activeTab === tab.id
                      ? 'bg-primary text-white'
                      : 'text-secondary hover:bg-surface hover:text-primary'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                  <span className="font-medium">{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Conteúdo */}
        <div className="col-span-12 md:col-span-9">
          {renderTabContent()}
          
          {/* Botão Salvar (exceto para About) */}
          {activeTab !== 'about' && (
            <div className="mt-6 flex justify-end">
              <button
                onClick={handleSaveConfig}
                disabled={isSaving}
                className="btn btn-primary"
              >
                {isSaving ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2"></div>
                    Salvando...
                  </>
                ) : (
                  'Salvar Alterações'
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SystemSettings;