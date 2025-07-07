/**
 * ThemeSelector - Componente para alternar entre temas dark/light/pro
 */

import React, { useState, useEffect } from 'react';
import {
  SunIcon,
  MoonIcon,
  SparklesIcon,
  ChevronDownIcon,
  CheckIcon
} from '@heroicons/react/24/outline';
import { applyTheme } from '../utils/themeInitializer';

interface Theme {
  id: string;
  name: string;
  icon: React.ReactNode;
  description: string;
}

const themes: Theme[] = [
  {
    id: 'theme-light',
    name: 'Light',
    icon: <SunIcon className="w-4 h-4" />,
    description: 'Tema claro padrão'
  },
  {
    id: 'theme-dark',
    name: 'Dark',
    icon: <MoonIcon className="w-4 h-4" />,
    description: 'Tema escuro para ambientes com pouca luz'
  },
  {
    id: 'theme-pro',
    name: 'Professional',
    icon: <SparklesIcon className="w-4 h-4" />,
    description: 'Tema profissional sofisticado'
  }
];

const ThemeSelector: React.FC = () => {
  const [currentTheme, setCurrentTheme] = useState('theme-pro');
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    // Carregar tema salvo do localStorage
    const savedTheme = localStorage.getItem('presence-theme') || 'theme-pro';
    setCurrentTheme(savedTheme);
    
    // Aplicar tema imediatamente
    const applyThemeNow = (themeId: string) => {
      // Remover classes de tema existentes do body
      document.body.className = document.body.className.replace(/theme-\w+/g, '');
      // Adicionar nova classe de tema
      document.body.classList.add(themeId);
      
      // Aplicar ao elemento raiz também para máxima compatibilidade
      const root = document.documentElement;
      root.className = root.className.replace(/theme-\w+/g, '');
      root.classList.add(themeId);
      
      // Salvar no localStorage
      localStorage.setItem('presence-theme', themeId);
      
      console.log('Tema aplicado:', themeId);
    };
    
    applyThemeNow(savedTheme);
  }, []);

  const handleThemeChange = (themeId: string) => {
    setCurrentTheme(themeId);
    
    // Aplicar tema
    document.body.className = document.body.className.replace(/theme-\w+/g, '');
    document.body.classList.add(themeId);
    
    const root = document.documentElement;
    root.className = root.className.replace(/theme-\w+/g, '');
    root.classList.add(themeId);
    
    localStorage.setItem('presence-theme', themeId);
    console.log('Tema alterado para:', themeId);
    
    setIsOpen(false);
  };

  const currentThemeData = themes.find(t => t.id === currentTheme) || themes[2];

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-color bg-surface hover:bg-surface-secondary text-primary transition-all duration-200 text-sm shadow-sm"
      >
        <span className="text-primary">
          {currentThemeData.icon}
        </span>
        <span className="font-medium hidden sm:inline">
          {currentThemeData.name}
        </span>
        <ChevronDownIcon className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          {/* Overlay para fechar o dropdown */}
          <div 
            className="fixed inset-0 z-10" 
            onClick={() => setIsOpen(false)}
          />
          
          {/* Menu dropdown */}
          <div className="absolute right-0 bottom-full mb-2 w-64 modal-bg border border-color rounded-lg shadow-lg z-50 animate-fadeIn">
            <div className="p-2">
              <div className="text-xs font-semibold text-secondary uppercase tracking-wide px-3 py-2">
                Tema da Interface
              </div>
              
              {themes.map((theme) => (
                <button
                  key={theme.id}
                  onClick={() => handleThemeChange(theme.id)}
                  className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-left transition-all duration-200 ${
                    currentTheme === theme.id
                      ? 'bg-primary text-white shadow-sm'
                      : 'hover:bg-surface text-primary'
                  }`}
                >
                  <span className={currentTheme === theme.id ? 'text-white' : 'text-primary'}>
                    {theme.icon}
                  </span>
                  <div className="flex-1">
                    <div className="font-medium text-sm">
                      {theme.name}
                    </div>
                    <div className={`text-xs ${
                      currentTheme === theme.id 
                        ? 'text-white/80' 
                        : 'text-secondary'
                    }`}>
                      {theme.description}
                    </div>
                  </div>
                  {currentTheme === theme.id && (
                    <CheckIcon className="w-4 h-4 text-white" />
                  )}
                </button>
              ))}
            </div>
            
            <div className="border-t border-color p-3">
              <div className="text-xs text-muted text-center">
                O tema será salvo automaticamente
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ThemeSelector;