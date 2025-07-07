import React from 'react';
import { Page } from '../App'; // Importe o tipo do App
import {
  HomeIcon,
  UsersIcon,
  QuestionMarkCircleIcon,
  CameraIcon,
  TvIcon,
  ClipboardDocumentListIcon,
  Cog6ToothIcon,
  ShieldCheckIcon
} from '@heroicons/react/24/outline';
import ThemeSelector from './ThemeSelector';

interface SidebarProps {
  currentPage: Page; // Use o tipo Page
  onPageChange: (page: Page) => void; // Use o tipo Page
}
const Sidebar: React.FC<SidebarProps> = ({ currentPage, onPageChange }) => {
  // Garanta que os IDs correspondam ao tipo Page
  const menuItems: {
    id: Page;
    label: string;
    icon: React.ReactNode;
    description: string;
  }[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      icon: <HomeIcon className="w-6 h-6" />,
      description: 'Visão geral do sistema'
    },
    {
      id: 'people',
      label: 'Pessoas',
      icon: <UsersIcon className="w-6 h-6" />,
      description: 'Gerenciar pessoas cadastradas'
    },
    {
      id: 'unknown',
      label: 'Desconhecidos',
      icon: <QuestionMarkCircleIcon className="w-6 h-6" />,
      description: 'Identificar pessoas desconhecidas'
    },
    {
      id: 'cameras',
      label: 'Câmeras',
      icon: <CameraIcon className="w-6 h-6" />,
      description: 'Configurar câmeras'
    },
    {
      id: 'vms-webrtc',
      label: 'Monitoramento',
      icon: <TvIcon className="w-6 h-6" />,
      description: 'Central de vídeo'
    },
    {
      id: 'logs',
      label: 'Reconhecimentos',
      icon: <ClipboardDocumentListIcon className="w-6 h-6" />,
      description: 'Histórico de reconhecimentos'
    },
    {
      id: 'system',
      label: 'Configurações',
      icon: <Cog6ToothIcon className="w-6 h-6" />,
      description: 'Sistema e preferências'
    }
  ];

  return (
    <div className="fixed left-0 top-0 h-full w-64 sidebar-bg text-primary shadow-lg border-r border-color transition-all duration-300 flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-color">
        <div className="flex items-center">
          <div className="p-2 rounded-lg bg-primary shadow-lg">
            <ShieldCheckIcon className="w-6 h-6 text-white" />
          </div>
          <div className="ml-3">
            <h1 className="text-xl font-bold text-primary">
              Presence
            </h1>
            <p className="text-secondary text-sm font-medium">
              Sistema Inteligente
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 mt-6 px-3">
        <ul className="space-y-1">
          {menuItems.map((item) => (
            <li key={item.id}>
              <button
                onClick={() => onPageChange(item.id)}
                className={`group w-full text-left px-3 py-3 rounded-xl flex items-center gap-3 transition-all duration-200 relative overflow-hidden ${
                  currentPage === item.id
                    ? 'bg-primary text-white shadow-lg transform scale-[1.02]'
                    : 'hover:bg-surface-secondary text-primary hover:scale-[1.01] hover:shadow-md'
                }`}
              >
                {/* Brilho sutil para item ativo */}
                {currentPage === item.id && (
                  <div className="absolute inset-0 bg-gradient-to-r from-white/10 to-transparent opacity-30"></div>
                )}
                
                <span className={`transition-all duration-200 ${
                  currentPage === item.id 
                    ? 'text-white scale-110' 
                    : 'text-secondary group-hover:text-primary group-hover:scale-105'
                }`}>
                  {item.icon}
                </span>
                <div className="flex-1 relative z-10">
                  <div className={`font-semibold text-sm ${
                    currentPage === item.id 
                      ? 'text-white' 
                      : 'text-primary group-hover:text-primary'
                  }`}>
                    {item.label}
                  </div>
                  <div className={`text-xs transition-colors duration-200 ${
                    currentPage === item.id 
                      ? 'text-white/80' 
                      : 'text-muted group-hover:text-secondary'
                  }`}>
                    {item.description}
                  </div>
                </div>
                
                {/* Indicador de página ativa */}
                {currentPage === item.id && (
                  <div className="w-1 h-8 bg-white/30 rounded-full absolute right-2"></div>
                )}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Theme Selector */}
      <div className="p-3 border-t border-color">
        <div className="mb-3">
          <ThemeSelector />
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-color bg-surface-secondary">
        <div className="text-xs text-muted text-center space-y-1">
          <div className="font-semibold text-secondary">Presence v1.0.0</div>
          <div className="text-muted">© 2024 Sistema Inteligente</div>
          <div className="flex items-center justify-center gap-1 mt-2">
            <div className="status-dot bg-success animate-pulse"></div>
            <span className="text-xs font-medium text-secondary">Sistema Online</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;