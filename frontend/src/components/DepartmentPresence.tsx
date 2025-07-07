import React, { useState, useEffect } from 'react';
import { ApiService } from '../services/api';
import {
  UsersIcon,
  BuildingOfficeIcon,
  ChartBarIcon,
  ClockIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

interface DepartmentData {
  department: string;
  total_people: number;
  recognized_today: number;
  not_recognized_today: number;
  attendance_rate: number;
}

interface AttendanceData {
  date: string;
  departments: DepartmentData[];
  summary: {
    total_departments: number;
    total_people: number;
    total_recognized: number;
    overall_attendance_rate: number;
  };
}

interface MissingPerson {
  id: string;
  name: string;
  department: string;
  email?: string;
  phone?: string;
  last_seen?: string;
  recognition_count: number;
}

const DepartmentPresence: React.FC = () => {
  const [attendanceData, setAttendanceData] = useState<AttendanceData | null>(null);
  const [missingPeople, setMissingPeople] = useState<MissingPerson[]>([]);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [selectedDepartment, setSelectedDepartment] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [showMissingOnly, setShowMissingOnly] = useState(false);

  useEffect(() => {
    loadAttendanceData();
    loadMissingPeople();
  }, [selectedDate, selectedDepartment]);

  const loadAttendanceData = async () => {
    try {
      setLoading(true);
      const data = await ApiService.getDepartmentAttendance(selectedDate);
      setAttendanceData(data);
    } catch (error) {
      console.error('Erro ao carregar dados de presença:', error);
      toast.error('Erro ao carregar dados de presença');
    } finally {
      setLoading(false);
    }
  };

  const loadMissingPeople = async () => {
    try {
      const data = await ApiService.getMissingPeople(selectedDepartment, selectedDate);
      setMissingPeople(data.missing_people);
    } catch (error) {
      console.error('Erro ao carregar pessoas ausentes:', error);
    }
  };

  const getAttendanceColor = (rate: number) => {
    if (rate >= 90) return 'text-success';
    if (rate >= 70) return 'text-warning';
    return 'text-error';
  };

  const getAttendanceIcon = (rate: number) => {
    if (rate >= 90) return <ArrowTrendingUpIcon className="w-5 h-5 text-success" />;
    if (rate >= 70) return <ClockIcon className="w-5 h-5 text-warning" />;
    return <ArrowTrendingDownIcon className="w-5 h-5 text-error" />;
  };

  const formatLastSeen = (lastSeen?: string) => {
    if (!lastSeen) return 'Nunca visto';
    const date = new Date(lastSeen);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return 'Hoje';
    if (diffDays === 1) return 'Ontem';
    return `${diffDays} dias atrás`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header e Controles */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-primary">Presença por Departamento</h2>
          <p className="text-secondary">Acompanhamento de presença organizacional</p>
        </div>
        
        <div className="flex flex-col sm:flex-row gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">Data</label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="input"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-1">Departamento</label>
            <select
              value={selectedDepartment}
              onChange={(e) => setSelectedDepartment(e.target.value)}
              className="input"
            >
              <option value="">Todos os departamentos</option>
              {attendanceData?.departments.map(dept => (
                <option key={dept.department} value={dept.department}>
                  {dept.department}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Resumo Geral */}
      {attendanceData && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="card">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-primary/10 rounded-lg">
                <BuildingOfficeIcon className="w-6 h-6 text-primary" />
              </div>
              <div>
                <p className="text-sm text-secondary">Departamentos</p>
                <p className="text-2xl font-bold">{attendanceData.summary.total_departments}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-blue-100 rounded-lg">
                <UsersIcon className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-secondary">Total de Pessoas</p>
                <p className="text-2xl font-bold">{attendanceData.summary.total_people}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-success/10 rounded-lg">
                <ChartBarIcon className="w-6 h-6 text-success" />
              </div>
              <div>
                <p className="text-sm text-secondary">Presentes Hoje</p>
                <p className="text-2xl font-bold">{attendanceData.summary.total_recognized}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-warning/10 rounded-lg">
                <ArrowTrendingUpIcon className="w-6 h-6 text-warning" />
              </div>
              <div>
                <p className="text-sm text-secondary">Taxa Geral</p>
                <p className={`text-2xl font-bold ${getAttendanceColor(attendanceData.summary.overall_attendance_rate)}`}>
                  {attendanceData.summary.overall_attendance_rate.toFixed(1)}%
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Departamentos */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Presença por Departamento</h3>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="showMissingOnly"
              checked={showMissingOnly}
              onChange={(e) => setShowMissingOnly(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="showMissingOnly" className="text-sm">
              Mostrar apenas com ausências
            </label>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-color">
                <th className="text-left py-3 px-4">Departamento</th>
                <th className="text-center py-3 px-4">Total</th>
                <th className="text-center py-3 px-4">Presentes</th>
                <th className="text-center py-3 px-4">Ausentes</th>
                <th className="text-center py-3 px-4">Taxa</th>
                <th className="text-center py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody>
              {attendanceData?.departments
                .filter(dept => !showMissingOnly || dept.not_recognized_today > 0)
                .map((dept, index) => (
                <tr key={dept.department} className={`border-b border-color ${index % 2 === 0 ? 'bg-surface/30' : ''}`}>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <BuildingOfficeIcon className="w-4 h-4 text-secondary" />
                      <span className="font-medium">{dept.department}</span>
                    </div>
                  </td>
                  <td className="text-center py-3 px-4 font-medium">
                    {dept.total_people}
                  </td>
                  <td className="text-center py-3 px-4">
                    <span className="inline-flex items-center gap-1 text-success">
                      {dept.recognized_today}
                    </span>
                  </td>
                  <td className="text-center py-3 px-4">
                    <span className={`inline-flex items-center gap-1 ${dept.not_recognized_today > 0 ? 'text-error' : 'text-secondary'}`}>
                      {dept.not_recognized_today}
                      {dept.not_recognized_today > 0 && <ExclamationTriangleIcon className="w-4 h-4" />}
                    </span>
                  </td>
                  <td className="text-center py-3 px-4">
                    <span className={`font-bold ${getAttendanceColor(dept.attendance_rate)}`}>
                      {dept.attendance_rate.toFixed(1)}%
                    </span>
                  </td>
                  <td className="text-center py-3 px-4">
                    {getAttendanceIcon(dept.attendance_rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pessoas Ausentes */}
      {missingPeople.length > 0 && (
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <ExclamationTriangleIcon className="w-5 h-5 text-warning" />
            <h3 className="text-lg font-semibold">
              Pessoas Ausentes ({missingPeople.length})
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {missingPeople.map((person) => (
              <div key={person.id} className="border border-color rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h4 className="font-medium">{person.name}</h4>
                    <p className="text-sm text-secondary">{person.department}</p>
                  </div>
                  <span className="badge badge-warning">Ausente</span>
                </div>
                
                <div className="space-y-1 text-sm text-secondary">
                  {person.email && (
                    <div className="flex items-center gap-1">
                      <span>📧</span>
                      <span>{person.email}</span>
                    </div>
                  )}
                  {person.phone && (
                    <div className="flex items-center gap-1">
                      <span>📱</span>
                      <span>{person.phone}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-1">
                    <ClockIcon className="w-4 h-4" />
                    <span>Última vez: {formatLastSeen(person.last_seen)}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <ChartBarIcon className="w-4 h-4" />
                    <span>{person.recognition_count} reconhecimentos</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mensagem quando não há ausentes */}
      {missingPeople.length === 0 && !selectedDepartment && (
        <div className="card text-center py-8">
          <div className="text-6xl mb-4">🎉</div>
          <h3 className="text-lg font-semibold mb-2">Excelente!</h3>
          <p className="text-secondary">
            Não há pessoas ausentes hoje{selectedDepartment && ` no departamento "${selectedDepartment}"`}.
          </p>
        </div>
      )}
    </div>
  );
};

export default DepartmentPresence;