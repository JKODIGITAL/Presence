import React, { useState, useEffect } from 'react';
import { ApiService, Stats, Person, Camera } from '../services/api';
import DepartmentPresence from './DepartmentPresence';
import {
  UsersIcon,
  CameraIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  EyeIcon,
  ExclamationTriangleIcon,
  ClockIcon
} from '@heroicons/react/24/outline';

interface DashboardProps {
  onNavigate: (page: string) => void;
}

interface StatsCard {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: string;
  color: string;
}

interface FilteredStats extends Stats {
  departmentBreakdown?: Array<{ department: string; count: number; recognitions: number }>;
  locationBreakdown?: Array<{ location: string; count: number; recognitions: number }>;
}

const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const [stats, setStats] = useState<FilteredStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  
  // Filter states
  const [selectedDepartment, setSelectedDepartment] = useState<string>('');
  const [selectedLocation, setSelectedLocation] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [showFilters, setShowFilters] = useState(false);
  
  // Breakdown data
  const [departments, setDepartments] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  
  // Attendance data
  const [attendanceData, setAttendanceData] = useState<any>(null);
  const [missingPeople, setMissingPeople] = useState<any>(null);
  const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [showMissingModal, setShowMissingModal] = useState(false);
  const [selectedDeptForMissing, setSelectedDeptForMissing] = useState<string>('');
  
  // Tab management
  const [activeTab, setActiveTab] = useState<'overview' | 'performance'>('overview');

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    loadStats();
    loadAttendanceData();
    const interval = setInterval(() => {
      loadStats();
      loadAttendanceData();
    }, 30000); // Atualizar a cada 30 segundos
    return () => clearInterval(interval);
  }, [selectedDepartment, selectedLocation, startDate, endDate, selectedDate]);

  const loadInitialData = async () => {
    try {
      console.log('🔄 Carregando dados iniciais do dashboard...');
      
      // Load people and cameras to get available departments and locations
      const [peopleResponse, camerasResponse] = await Promise.all([
        ApiService.getPeople({ limit: 100 }).catch(err => {
          console.error('Erro ao carregar pessoas:', err);
          return { people: [], total: 0 };
        }),
        ApiService.getCameras().catch(err => {
          console.error('Erro ao carregar câmeras:', err);
          return { cameras: [], total: 0, active: 0, inactive: 0, error: 0 };
        })
      ]);
      
      console.log('👥 Pessoas carregadas:', peopleResponse.people?.length || 0, peopleResponse);
      console.log('🎥 Câmeras carregadas:', camerasResponse.cameras?.length || 0, camerasResponse);
      
      // Debug: mostrar IDs das pessoas e câmeras
      if (peopleResponse.people?.length > 0) {
        console.log('👤 Primeiras pessoas:', peopleResponse.people.slice(0, 3).map(p => ({id: p.id, name: p.name})));
      }
      if (camerasResponse.cameras?.length > 0) {
        console.log('📹 Primeiras câmeras:', camerasResponse.cameras.slice(0, 3).map(c => ({id: c.id, name: c.name, status: c.status})));
      }
      
      setPeople(peopleResponse.people || []);
      setCameras(camerasResponse.cameras || []);
      
      // Extract unique departments and locations
      const uniqueDepartments = [...new Set(
        (peopleResponse.people || [])
          .filter(person => person.department)
          .map(person => person.department!)
      )];
      
      const uniqueLocations = [...new Set(
        (camerasResponse.cameras || [])
          .filter(camera => camera.location)
          .map(camera => camera.location!)
      )];
      
      console.log('🏢 Departamentos encontrados:', uniqueDepartments);
      console.log('📍 Localizações encontradas:', uniqueLocations);
      
      setDepartments(uniqueDepartments);
      setLocations(uniqueLocations);
      
      // Load initial stats
      loadStats();
    } catch (err) {
      console.error('❌ Erro ao carregar dados iniciais:', err);
      setError('Erro ao carregar dados iniciais');
    }
  };

  const loadStats = async () => {
    try {
      setLoading(true);
      
      // Use the correct API methods that exist in the service
      const [systemInfo, peopleResponse, camerasResponse] = await Promise.all([
        ApiService.getSystemInfo().catch(() => null),
        ApiService.getPeople({ limit: 1000 }).catch(() => ({ people: [], total: 0 })),
        ApiService.getCameras().catch(() => ({ cameras: [], total: 0, active: 0, inactive: 0, error: 0 }))
      ]);

      // Calculate stats from actual data
      const people = peopleResponse.people || [];
      const cameras = camerasResponse.cameras || [];
      
      const activePeople = people.filter(p => p.status === 'active').length;
      const activeCameras = cameras.filter(c => c.status === 'active').length;
      const inactiveCameras = cameras.filter(c => c.status === 'inactive').length;
      const errorCameras = cameras.filter(c => c.status === 'error').length;
      
      // Build comprehensive stats object
      let filteredStats: FilteredStats = {
        total_people: people.length,
        active_people: activePeople,
        unknown_people: people.filter(p => p.is_unknown).length,
        recent_recognitions: 0, // Will be populated from recognition API
        total_cameras: cameras.length,
        active_cameras: activeCameras,
        inactive_cameras: inactiveCameras,
        error_cameras: errorCameras,
        frames_processed_today: 0,
        total_recognitions_today: 0,
        total_recognitions_week: 0,
        total_recognitions_month: 0,
        unique_people_today: 0,
        unknown_faces_today: 0,
        avg_confidence: 0
      };
      
      // Try to get recognition stats
      try {
        const recognitionLogs = await ApiService.getRecognitionLogs({ limit: 100 });
        const today = new Date().toISOString().split('T')[0];
        const todayLogs = recognitionLogs.logs.filter(log => 
          log.timestamp.startsWith(today)
        );
        
        filteredStats.total_recognitions_today = todayLogs.length;
        filteredStats.unique_people_today = new Set(todayLogs.map(log => log.person_id)).size;
        filteredStats.unknown_faces_today = todayLogs.filter(log => log.is_unknown).length;
        
        if (todayLogs.length > 0) {
          filteredStats.avg_confidence = todayLogs.reduce((sum, log) => sum + log.confidence, 0) / todayLogs.length;
        }
      } catch (err) {
        console.warn('Could not load recognition stats:', err);
      }

      // Apply department filtering if selected
      if (selectedDepartment) {
        const departmentPeople = people.filter(p => p.department === selectedDepartment);
        filteredStats.total_people = departmentPeople.length;
        filteredStats.active_people = departmentPeople.filter(p => p.status === 'active').length;
      }

      // Apply location filtering if selected
      if (selectedLocation) {
        const locationCameras = cameras.filter(c => c.location === selectedLocation);
        filteredStats.total_cameras = locationCameras.length;
        filteredStats.active_cameras = locationCameras.filter(c => c.status === 'active').length;
        filteredStats.inactive_cameras = locationCameras.filter(c => c.status === 'inactive').length;
        filteredStats.error_cameras = locationCameras.filter(c => c.status === 'error').length;
      }

      // Generate breakdown data
      if (!selectedDepartment) {
        filteredStats.departmentBreakdown = departments.map(dept => {
          const deptPeople = people.filter(p => p.department === dept);
          return {
            department: dept,
            count: deptPeople.length,
            recognitions: deptPeople.reduce((sum, p) => sum + p.recognition_count, 0)
          };
        });
      }

      if (!selectedLocation) {
        filteredStats.locationBreakdown = locations.map(loc => {
          const locCameras = cameras.filter(c => c.location === loc);
          return {
            location: loc,
            count: locCameras.length,
            recognitions: 0 // This would need to be calculated from recognition logs
          };
        });
      }

      setStats(filteredStats);
      setError(null);
    } catch (err) {
      console.error('Erro ao carregar estatísticas:', err);
      setError('Erro ao carregar dados do dashboard');
    } finally {
      setLoading(false);
    }
  };

  const loadAttendanceData = async () => {
    try {
      const data = await ApiService.getDepartmentAttendance(selectedDate);
      setAttendanceData(data);
    } catch (err) {
      console.error('Erro ao carregar dados de presença:', err);
    }
  };

  const loadMissingPeople = async (department?: string) => {
    try {
      const data = await ApiService.getMissingPeople(department, selectedDate);
      setMissingPeople(data);
      setSelectedDeptForMissing(department || '');
      setShowMissingModal(true);
    } catch (err) {
      console.error('Erro ao carregar pessoas ausentes:', err);
    }
  };

  const clearFilters = () => {
    setSelectedDepartment('');
    setSelectedLocation('');
    setStartDate('');
    setEndDate('');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-center">
          <div className="text-red-500 text-xl mr-3">
            <ExclamationTriangleIcon className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-red-800 font-medium">Erro no Dashboard</h3>
            <p className="text-red-600 text-sm">{error}</p>
          </div>
        </div>
        <button
          onClick={loadStats}
          className="mt-3 btn btn-danger text-sm"
        >
          Tentar Novamente
        </button>
      </div>
    );
  }

  const statsCards: StatsCard[] = [
    {
      title: 'Pessoas Cadastradas',
      value: stats?.total_people || 0,
      icon: <UsersIcon className="w-7 h-7" />,
      color: 'bg-primary'
    },
    {
      title: 'Câmeras Ativas',
      value: `${stats?.active_cameras || 0}/${stats?.total_cameras || 0}`,
      icon: <CameraIcon className="w-7 h-7" />,
      color: 'bg-success'
    },
    {
      title: 'Reconhecimentos Hoje',
      value: stats?.total_recognitions_today || 0,
      icon: <ChartBarIcon className="w-7 h-7" />,
      color: 'bg-secondary'
    },
    {
      title: 'Pessoas Únicas Hoje',
      value: stats?.unique_people_today || 0,
      icon: <UsersIcon className="w-7 h-7" />,
      color: 'bg-info'
    },
    {
      title: 'Faces Desconhecidas',
      value: stats?.unknown_faces_today || 0,
      icon: <ExclamationTriangleIcon className="w-7 h-7" />,
      color: 'bg-warning'
    },
    {
      title: 'Confiança Média',
      value: `${((stats?.avg_confidence || 0) * 100).toFixed(1)}%`,
      icon: <ChartBarIcon className="w-7 h-7" />,
      color: 'bg-accent'
    }
  ];

  return (
    <div className="space-y-6">
      {/* Welcome Section */}
      <div className="bg-primary rounded-lg p-6 text-white shadow-lg">
        <div className="flex justify-between items-start">
          <div className="flex-1">
            <h2 className="text-2xl font-bold mb-2 text-white">Bem-vindo ao Presence</h2>
            <p className="text-white/90 mb-4">
              Sistema de controle de presença com reconhecimento facial. Monitore entradas, saídas e gerencie pessoas.
            </p>
            <div className="mt-4 flex items-center text-sm">
              <div className="flex items-center mr-6">
                <div className="w-2 h-2 bg-white rounded-full mr-2 animate-pulse"></div>
                <span className="text-white/90">Sistema Online</span>
              </div>
              <div className="text-white/80">
                Última atualização: {new Date().toLocaleTimeString('pt-BR')}
              </div>
            </div>
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="bg-white/20 hover:bg-white/30 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
          >
            <Cog6ToothIcon className="w-4 h-4" />
            Filtros
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-color">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('overview')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'overview'
                ? 'border-primary text-primary'
                : 'border-transparent text-secondary hover:text-primary hover:border-border'
            }`}
          >
            <div className="flex items-center gap-2">
              <ChartBarIcon className="w-4 h-4" />
              Overview
            </div>
          </button>
          <button
            onClick={() => setActiveTab('performance')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'performance'
                ? 'border-primary text-primary'
                : 'border-transparent text-secondary hover:text-primary hover:border-border'
            }`}
          >
            <div className="flex items-center gap-2">
              <UsersIcon className="w-4 h-4" />
              Presença por Departamento
            </div>
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'performance' ? (
        <DepartmentPresence />
      ) : (
        <>
          {/* Filter Controls */}
      {showFilters && (
        <div className="card rounded-lg shadow-md p-6 border border-color">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-primary">Filtros do Dashboard</h3>
            <button
              onClick={clearFilters}
              className="text-sm text-secondary hover:text-primary"
            >
              Limpar Filtros
            </button>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Department Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <UsersIcon className="w-4 h-4 inline mr-1" />
                Departamento
              </label>
              <select
                value={selectedDepartment}
                onChange={(e) => setSelectedDepartment(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">Todos os departamentos</option>
                {departments.map((dept) => (
                  <option key={dept} value={dept}>
                    {dept}
                  </option>
                ))}
              </select>
            </div>

            {/* Location Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <CameraIcon className="w-4 h-4 inline mr-1" />
                Localização
              </label>
              <select
                value={selectedLocation}
                onChange={(e) => setSelectedLocation(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">Todas as localizações</option>
                {locations.map((loc) => (
                  <option key={loc} value={loc}>
                    {loc}
                  </option>
                ))}
              </select>
            </div>

            {/* Date Range */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <ClockIcon className="w-4 h-4 inline mr-1" />
                Data Início
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <ClockIcon className="w-4 h-4 inline mr-1" />
                Data Fim
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Active Filters Display */}
          {(selectedDepartment || selectedLocation || startDate || endDate) && (
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="text-sm text-gray-600">Filtros ativos:</span>
              {selectedDepartment && (
                <span className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full">
                  Depto: {selectedDepartment}
                </span>
              )}
              {selectedLocation && (
                <span className="bg-green-100 text-green-800 text-xs px-2 py-1 rounded-full">
                  Local: {selectedLocation}
                </span>
              )}
              {startDate && (
                <span className="bg-purple-100 text-purple-800 text-xs px-2 py-1 rounded-full">
                  De: {startDate}
                </span>
              )}
              {endDate && (
                <span className="bg-purple-100 text-purple-800 text-xs px-2 py-1 rounded-full">
                  Até: {endDate}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {statsCards.map((card, index) => (
          <div key={index} className="card rounded-lg shadow-md p-6 hover:shadow-lg transition-all duration-300 flex items-center justify-between group">
            <div className="flex-1">
              <p className="text-sm font-medium text-secondary mb-1">{card.title}</p>
              <p className="text-3xl font-bold text-primary">{card.value}</p>
            </div>
            <div className={`p-3 rounded-full ${card.color} text-white shadow-md group-hover:scale-110 transition-transform duration-200`}>
              {card.icon}
            </div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-lg font-semibold text-primary mb-4">Ações Rápidas</h3>
          <div className="space-y-3">
            <button 
              onClick={() => onNavigate('people')}
              className="w-full text-left p-3 rounded-lg border border-color hover:bg-primary/10 hover:border-[var(--primary)] transition-all duration-200 flex items-center gap-3 group"
            >
              <UsersIcon className="w-5 h-5 text-primary group-hover:scale-110 transition-transform duration-200" />
              <div>
                <div className="font-medium text-primary">Cadastrar Nova Pessoa</div>
                <div className="text-sm text-secondary">Adicionar pessoa ao sistema</div>
              </div>
            </button>
            
            <button 
              onClick={() => onNavigate('cameras')}
              className="w-full text-left p-3 rounded-lg border border-color hover:bg-primary/10 hover:border-[var(--primary)] transition-all duration-200 flex items-center gap-3 group"
            >
              <CameraIcon className="w-5 h-5 text-primary group-hover:scale-110 transition-transform duration-200" />
              <div>
                <div className="font-medium text-primary">Adicionar Câmera</div>
                <div className="text-sm text-secondary">Configurar nova câmera</div>
              </div>
            </button>
            
            <button 
              onClick={() => onNavigate('logs')}
              className="w-full text-left p-3 rounded-lg border border-color hover:bg-primary/10 hover:border-[var(--primary)] transition-all duration-200 flex items-center gap-3 group"
            >
              <ChartBarIcon className="w-5 h-5 text-primary group-hover:scale-110 transition-transform duration-200" />
              <div>
                <div className="font-medium text-primary">Ver Relatórios</div>
                <div className="text-sm text-secondary">Acessar logs e estatísticas</div>
              </div>
            </button>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-semibold text-primary mb-4">Atividade Recente</h3>
          <div className="space-y-3">
            {stats && stats.total_recognitions_today > 0 ? (
              <div className="text-center py-8">
                <div className="text-4xl mb-2">🎉</div>
                <p className="text-gray-600">
                  Sistema processando reconhecimentos hoje!
                </p>
                <p className="text-sm text-gray-500 mt-1">
                  {stats.total_recognitions_today} reconhecimentos realizados
                </p>
              </div>
            ) : (
              <div className="text-center py-8">
                <div className="text-4xl mb-2">😴</div>
                <p className="text-gray-600">Nenhuma atividade recente</p>
                <p className="text-sm text-gray-500 mt-1">
                  Aguardando reconhecimentos...
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Department and Location Breakdown */}
      {stats && (stats.departmentBreakdown || stats.locationBreakdown) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Department Breakdown */}
          {stats.departmentBreakdown && stats.departmentBreakdown.length > 0 && (
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-primary mb-4 flex items-center">
                <UsersIcon className="w-5 h-5 mr-2 text-primary" />
                Breakdown por Departamento
              </h3>
              <div className="space-y-3">
                {stats.departmentBreakdown.map((dept, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                    <div className="flex items-center">
                      <div className="w-3 h-3 bg-blue-500 rounded-full mr-3"></div>
                      <div>
                        <div className="font-medium text-gray-900">{dept.department}</div>
                        <div className="text-sm text-gray-500">{dept.count} pessoas</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-gray-900">{dept.recognitions}</div>
                      <div className="text-sm text-gray-500">reconhecimentos</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Location Breakdown */}
          {stats.locationBreakdown && stats.locationBreakdown.length > 0 && (
            <div className="card p-6">
              <h3 className="text-lg font-semibold text-primary mb-4 flex items-center">
                <CameraIcon className="w-5 h-5 mr-2 text-primary" />
                Breakdown por Localização
              </h3>
              <div className="space-y-3">
                {stats.locationBreakdown.map((loc, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                    <div className="flex items-center">
                      <div className="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                      <div>
                        <div className="font-medium text-gray-900">{loc.location}</div>
                        <div className="text-sm text-gray-500">{loc.count} câmeras</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-gray-900">{loc.recognitions}</div>
                      <div className="text-sm text-gray-500">reconhecimentos</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* System Health */}
      <div className="card p-6">
        <h3 className="text-lg font-semibold text-primary mb-4">Status do Sistema</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center p-3 bg-surface-secondary rounded-lg border border-color">
            <div className="status-dot bg-success mr-3"></div>
            <div>
              <div className="font-medium text-primary">API Backend</div>
              <div className="text-sm text-success">Funcionando</div>
            </div>
          </div>
          
          <div className="flex items-center p-3 bg-surface-secondary rounded-lg border border-color">
            <div className="status-dot bg-info mr-3"></div>
            <div>
              <div className="font-medium text-primary">Banco de Dados</div>
              <div className="text-sm text-info">Conectado</div>
            </div>
          </div>
          
          <div className="flex items-center p-3 bg-surface-secondary rounded-lg border border-color">
            <div className="status-dot bg-accent mr-3"></div>
            <div>
              <div className="font-medium text-primary">Engine de Reconhecimento</div>
              <div className="text-sm text-accent">Ativo</div>
            </div>
          </div>
        </div>
      </div>

      {/* Department Attendance Section */}
      <div className="mt-8">
        <div className="card">
          <div className="p-6 border-b border-color">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-primary">Presença por Departamento</h3>
              <div className="flex items-center gap-3">
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="form-input"
                />
                <button
                  onClick={() => loadMissingPeople()}
                  className="btn btn-secondary text-sm"
                >
                  <EyeIcon className="w-4 h-4 mr-1" />
                  Ver Ausentes
                </button>
              </div>
            </div>
          </div>

          <div className="p-6">
            {attendanceData ? (
              <>
                {/* Summary Stats */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                  <div className="card-secondary p-4 rounded-lg border border-color">
                    <div className="text-sm text-secondary">Total Departamentos</div>
                    <div className="text-2xl font-bold text-primary">
                      {attendanceData.summary.total_departments}
                    </div>
                  </div>
                  <div className="card-secondary p-4 rounded-lg border border-color">
                    <div className="text-sm text-secondary">Pessoas Cadastradas</div>
                    <div className="text-2xl font-bold text-primary">
                      {attendanceData.summary.total_people}
                    </div>
                  </div>
                  <div className="card-secondary p-4 rounded-lg border border-color">
                    <div className="text-sm text-secondary">Reconhecidas Hoje</div>
                    <div className="text-2xl font-bold text-primary">
                      {attendanceData.summary.total_recognized}
                    </div>
                  </div>
                  <div className="card-secondary p-4 rounded-lg border border-color">
                    <div className="text-sm text-secondary">Taxa Geral</div>
                    <div className="text-2xl font-bold text-primary">
                      {attendanceData.summary.overall_attendance_rate}%
                    </div>
                  </div>
                </div>

                {/* Department Chart */}
                <div className="space-y-4">
                  {attendanceData.departments.map((dept: any) => (
                    <div key={dept.department} className="bg-surface-elevated border border-color p-4 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <UsersIcon className="w-5 h-5 text-primary" />
                          <span className="font-medium text-primary">{dept.department}</span>
                          <button
                            onClick={() => loadMissingPeople(dept.department)}
                            className="text-xs bg-surface-secondary hover:bg-surface border border-color px-2 py-1 rounded transition-colors text-secondary"
                          >
                            Ver Ausentes
                          </button>
                        </div>
                        <div className="text-right">
                          <div className="text-sm text-secondary">
                            {dept.recognized_today}/{dept.total_people}
                          </div>
                          <div className={`text-sm font-medium ${
                            dept.attendance_rate >= 80 ? 'text-success' :
                            dept.attendance_rate >= 60 ? 'text-warning' :
                            'text-error'
                          }`}>
                            {dept.attendance_rate}%
                          </div>
                        </div>
                      </div>
                      <div className="w-full bg-surface-secondary rounded-full h-3">
                        <div
                          className={`h-3 rounded-full transition-all duration-300 ${
                            dept.attendance_rate >= 80 ? 'bg-success' :
                            dept.attendance_rate >= 60 ? 'bg-warning' :
                            'bg-error'
                          }`}
                          style={{ width: `${dept.attendance_rate}%` }}
                        ></div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-center py-8">
                <ChartBarIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-500">Carregando dados de presença...</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Missing People Modal */}
      {showMissingModal && missingPeople && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-primary">
                Pessoas Ausentes - {selectedDeptForMissing || 'Todos os Departamentos'}
              </h3>
              <button
                onClick={() => setShowMissingModal(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <ExclamationTriangleIcon className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              {missingPeople.missing_people.length > 0 ? (
                <div className="space-y-3">
                  {missingPeople.missing_people.map((person: any) => (
                    <div key={person.id} className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium text-primary">{person.name}</div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">
                            {person.department} {person.email && `• ${person.email}`}
                          </div>
                          {person.last_seen && (
                            <div className="text-xs text-gray-500 mt-1">
                              Última vez vista: {new Date(person.last_seen).toLocaleString('pt-BR')}
                            </div>
                          )}
                        </div>
                        <div className="text-right">
                          <div className="text-sm text-gray-600 dark:text-gray-400">
                            {person.recognition_count} reconhecimentos
                          </div>
                          {person.phone && (
                            <div className="text-xs text-gray-500">
                              {person.phone}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <div className="text-4xl mb-2">🎉</div>
                  <p className="text-gray-600 dark:text-gray-400">
                    Todas as pessoas compareceram hoje!
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
};

export default Dashboard;