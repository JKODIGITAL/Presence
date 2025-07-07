import { useState, useEffect } from 'react';
import React from 'react';
import './App.css';
import './styles/design-system.css';
import { Toaster } from 'react-hot-toast';
import { initializeTheme } from './utils/themeInitializer';
import Dashboard from './components/Dashboard';
import Sidebar from './components/Sidebar';
import PeopleManager from './components/PeopleManagerNew';
import CameraManagerClean from './components/CameraManagerClean';
import RecognitionLogs from './components/RecognitionLogs';
import SystemSettings from './components/SystemSettings';
import UnknownPeopleManagerFixed from './components/UnknownPeopleManagerFixed';
// import PerformanceMonitor from './components/PerformanceMonitor'; // Removido do menu
import VMSMonitor from './components/VMSMonitor';
import { ApiService } from './services/api';

export type Page = 'dashboard' | 'people' | 'unknown' | 'cameras' | 'vms-webrtc' | 'logs' | 'system';

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Inicializar tema
    initializeTheme();
    
    const checkApiHealth = async () => {
      try {
        await ApiService.getHealth();
        setIsLoading(false);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Erro desconhecido ao conectar com a API';
        setError(errorMessage);
        setIsLoading(false);
      }
    };

    checkApiHealth();
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard onNavigate={(page) => setCurrentPage(page as Page)} />;
      case 'people':
        return <PeopleManager />;
      case 'unknown':
        return <UnknownPeopleManagerFixed />;
      case 'cameras':
        return <CameraManagerClean />;
      case 'vms-webrtc':
        return <VMSMonitor />;
      case 'logs':
        return <RecognitionLogs />;
      case 'system':
        return <SystemSettings />;
      default:
        return <Dashboard onNavigate={(page) => setCurrentPage(page as Page)} />;
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-32 w-32 border-4 border-primary border-t-transparent mx-auto"></div>
          <p className="mt-4 text-secondary">Carregando...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-4">⚠️</div>
          <h1 className="text-2xl font-bold text-primary mb-2">Erro de Conexão</h1>
          <p className="text-secondary mb-4">{error}</p>
          <button 
            onClick={() => window.location.reload()} 
            className="btn btn-primary"
          >
            Tentar Novamente
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Toaster position="top-right" />
      <div className="flex">
        <Sidebar 
          currentPage={currentPage} 
          onPageChange={(page: Page) => setCurrentPage(page)}  
        />
        
        <main className="flex-1 ml-64">
          <header className="header-bg shadow-sm border-b border-color">
            <div className="px-6 py-4">
              <h1 className="text-2xl font-bold text-primary">
                {currentPage === 'dashboard' && 'Dashboard'}
                {currentPage === 'people' && 'Gerenciar Pessoas'}
                {currentPage === 'unknown' && 'Pessoas Desconhecidas'}
                {currentPage === 'cameras' && 'Câmeras'}
                {currentPage === 'vms-webrtc' && 'Central de Monitoramento'}
                {currentPage === 'logs' && 'Logs de Reconhecimento'}
                {currentPage === 'system' && 'Configurações do Sistema'}
              </h1>
              <div className="flex items-center mt-2">
                <div className="flex items-center">
                  <div className="status-dot bg-success mr-2"></div>
                  <span className="text-sm text-secondary">
                    API Conectada
                  </span>
                </div>
              </div>
            </div>
          </header>
          
          <div className="p-6">
            {renderPage()}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
