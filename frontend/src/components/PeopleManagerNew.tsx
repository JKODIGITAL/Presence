import React, { useState, useEffect } from 'react';
import { ApiService, Person, Camera } from '../services/api';
import { 
  PlusIcon, 
  PencilIcon, 
  TrashIcon,
  EyeIcon,
  XMarkIcon,
  UserIcon,
  ExclamationTriangleIcon,
  CheckIcon,
  CameraIcon,
  VideoCameraIcon,
  PhotoIcon,
  BuildingOfficeIcon,
  PhoneIcon,
  EnvelopeIcon
} from '@heroicons/react/24/outline';
// import WebRTCCapture from './WebRTCCapture'; // Componente removido

const PeopleManager: React.FC = () => {
  // Estados principais
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Estados do modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingPerson, setEditingPerson] = useState<Person | null>(null);
  
  // Estados de filtros
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDepartment, setFilterDepartment] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  
  // Estados para captura de foto
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  // const [showWebRTCCapture, setShowWebRTCCapture] = useState(false); // WebRTC removido
  const [isProcessingRegistration, setIsProcessingRegistration] = useState(false);

  // Formulário simplificado e prático
  const [formData, setFormData] = useState({
    name: '',
    department: '',
    position: '', // Cargo/função
    email: '',
    phone: '',
    tags: '',
    detection_enabled: true  // Por padrão, detecção habilitada
  });

  useEffect(() => {
    loadPeople();
    loadCameras();
  }, [searchTerm, filterDepartment]);

  const loadCameras = async () => {
    try {
      const response = await ApiService.getCameras({ status: 'active' });
      setCameras(response.cameras);
      // Selecionar primeira câmera ativa automaticamente
      if (response.cameras.length > 0 && !selectedCameraId) {
        setSelectedCameraId(response.cameras[0].id);
      }
    } catch (err) {
      console.error('Erro ao carregar câmeras:', err);
    }
  };

  const loadPeople = async () => {
    try {
      setLoading(true);
      const response = await ApiService.getPeople({
        search: searchTerm || undefined,
        department: filterDepartment || undefined,
        limit: 100
      });
      setPeople(response.people);
      setError(null);
    } catch (err) {
      console.error('Erro ao carregar pessoas:', err);
      setError('Erro ao carregar lista de pessoas');
    } finally {
      setLoading(false);
    }
  };

  /* Handlers para WebRTC - removidos
  const handleOpenWebRTCCapture = () => {
    if (!selectedCameraId) {
      setError('Selecione uma câmera primeiro');
      return;
    }
    setShowWebRTCCapture(true);
  };

  const handleWebRTCCapture = (imageData: string) => {
    setCapturedImage(imageData);
    setShowWebRTCCapture(false);
    console.log('📸 Imagem capturada via WebRTC');
  };
  */

  const handleAddPerson = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!capturedImage) {
      setError('Capture uma foto primeiro');
      return;
    }

    setIsProcessingRegistration(true);
    
    try {
      // Converter base64 para FormData
      const base64Data = capturedImage.split(',')[1];
      const formDataWithImage = new FormData();
      
      formDataWithImage.append('name', formData.name);
      formDataWithImage.append('department', formData.department);
      formDataWithImage.append('email', formData.email);
      formDataWithImage.append('phone', formData.phone);
      formDataWithImage.append('tags', `${formData.position ? `Cargo: ${formData.position}` : ''}${formData.tags ? `, ${formData.tags}` : ''}`);
      formDataWithImage.append('image_base64', base64Data);
      
      console.log('🚀 Registrando pessoa...');
      
      // Usar registro rápido com embeddings em background
      const newPerson = await ApiService.registerPersonFromBase64Quick(formDataWithImage);
      
      console.log('✅ Pessoa registrada:', newPerson);
      
      // Limpar formulário
      setFormData({
        name: '',
        department: '',
        position: '',
        email: '',
        phone: '',
        tags: ''
      });
      setCapturedImage(null);
      setShowAddModal(false);
      
      // Recarregar lista
      await loadPeople();
      
      // Mostrar sucesso
      setSuccessMessage(`✅ ${formData.name} cadastrado(a) com sucesso! Embeddings sendo processados em segundo plano.`);
      setTimeout(() => setSuccessMessage(null), 5000);
      
    } catch (err: any) {
      console.error('❌ Erro ao cadastrar pessoa:', err);
      setError(`Erro ao cadastrar pessoa: ${err.message || 'Erro desconhecido'}`);
    } finally {
      setIsProcessingRegistration(false);
    }
  };

  const handleEditPerson = (person: Person) => {
    setEditingPerson(person);
    setFormData({
      name: person.name,
      department: person.department || '',
      position: '', // Extrair do tags se necessário
      email: person.email || '',
      phone: person.phone || '',
      tags: person.tags || ''
    });
    setShowEditModal(true);
  };

  const handleUpdatePerson = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPerson) return;

    setIsProcessingRegistration(true);

    try {
      // Se há nova foto capturada, usar endpoint com imagem
      if (capturedImage) {
        const base64Data = capturedImage.split(',')[1];
        const formDataWithImage = new FormData();
        
        formDataWithImage.append('name', formData.name);
        formDataWithImage.append('department', formData.department);
        formDataWithImage.append('email', formData.email);
        formDataWithImage.append('phone', formData.phone);
        formDataWithImage.append('tags', `${formData.position ? `Cargo: ${formData.position}` : ''}${formData.tags ? `, ${formData.tags}` : ''}`);
        formDataWithImage.append('image_base64', base64Data);
        
        console.log('🖼️ Atualizando pessoa com nova foto...');
        
        // Usar endpoint específico para atualização com nova foto
        await ApiService.updatePersonWithPhoto(editingPerson.id, formDataWithImage);
        
        setSuccessMessage('✅ Pessoa atualizada com nova foto! Embeddings sendo processados.');
      } else {
        // Atualização sem nova foto
        const updateData = {
          ...formData,
          tags: `${formData.position ? `Cargo: ${formData.position}` : ''}${formData.tags ? `, ${formData.tags}` : ''}`
        };
        
        console.log('📝 Atualizando dados da pessoa...');
        await ApiService.updatePerson(editingPerson.id, updateData);
        
        setSuccessMessage('✅ Pessoa atualizada com sucesso!');
      }
      
      // Limpar formulário e fechar modal
      setFormData({
        name: '',
        department: '',
        position: '',
        email: '',
        phone: '',
        tags: ''
      });
      setCapturedImage(null);
      setShowEditModal(false);
      setEditingPerson(null);
      
      // Recarregar lista
      await loadPeople();
      
      setTimeout(() => setSuccessMessage(null), 5000);
      
    } catch (err: any) {
      console.error('❌ Erro ao atualizar pessoa:', err);
      setError(`Erro ao atualizar pessoa: ${err.message || 'Erro desconhecido'}`);
    } finally {
      setIsProcessingRegistration(false);
    }
  };

  const handleDeletePerson = async (id: string, name: string) => {
    if (!confirm(`Tem certeza que deseja excluir ${name}?`)) {
      return;
    }

    try {
      await ApiService.deletePerson(id);
      loadPeople();
      setSuccessMessage('✅ Pessoa excluída com sucesso!');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      console.error('Erro ao excluir pessoa:', err);
      setError('Erro ao excluir pessoa');
    }
  };

  const clearMessages = () => {
    setError(null);
    setSuccessMessage(null);
  };

  const departmentOptions = ['TI', 'RH', 'Financeiro', 'Operações', 'Vendas', 'Marketing', 'Gerência'];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Mensagens */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <ExclamationTriangleIcon className="w-6 h-6 text-red-500 mr-3" />
              <div>
                <h3 className="text-red-800 font-medium">Erro</h3>
                <p className="text-red-600 text-sm">{error}</p>
              </div>
            </div>
            <button onClick={clearMessages} className="text-red-400 hover:text-red-600">
              <XMarkIcon className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {successMessage && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <CheckIcon className="w-6 h-6 text-green-500 mr-3" />
              <div>
                <h3 className="text-green-800 font-medium">Sucesso</h3>
                <p className="text-green-600 text-sm">{successMessage}</p>
              </div>
            </div>
            <button onClick={clearMessages} className="text-green-400 hover:text-green-600">
              <XMarkIcon className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-primary">Gerenciar Pessoas</h2>
          <p className="text-secondary">Cadastre e gerencie pessoas do sistema</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn btn-primary"
        >
          <PlusIcon className="w-5 h-5 mr-2" />
          Cadastrar Pessoa
        </button>
      </div>

      {/* Filtros */}
      <div className="card p-6 rounded-lg border border-color">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Buscar por nome
            </label>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input"
              placeholder="Digite o nome..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-secondary mb-2">
              Filtrar por departamento
            </label>
            <input
              type="text"
              value={filterDepartment}
              onChange={(e) => setFilterDepartment(e.target.value)}
              className="input"
              placeholder="Digite o departamento..."
              list="filter-department-suggestions"
            />
            <datalist id="filter-department-suggestions">
              <option value="" />
              {departmentOptions.map(dept => (
                <option key={dept} value={dept} />
              ))}
            </datalist>
          </div>
          <div className="flex items-end">
            <button
              onClick={() => {
                setSearchTerm('');
                setFilterDepartment('');
              }}
              className="btn btn-secondary w-full"
            >
              Limpar Filtros
            </button>
          </div>
        </div>
      </div>

      {/* Lista de Pessoas */}
      <div className="card rounded-lg border border-color">
        <div className="px-6 py-4 border-b border-color">
          <h3 className="text-lg font-medium text-primary">
            Pessoas Cadastradas ({people.length})
          </h3>
        </div>
        
        <div className="divide-y divide-border">
          {people.map((person) => (
            <div key={person.id} className="p-6 hover:bg-surface-secondary">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center mr-4 overflow-hidden">
                    <img 
                      src={ApiService.getPersonImage(person.id)} 
                      alt={person.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        e.currentTarget.nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                    <UserIcon className="w-6 h-6 text-primary hidden" />
                  </div>
                  <div>
                    <h4 className="text-lg font-medium text-primary">{person.name}</h4>
                    <div className="flex items-center space-x-4 text-sm text-secondary">
                      {person.department && (
                        <div className="flex items-center">
                          <BuildingOfficeIcon className="w-4 h-4 mr-1" />
                          {person.department}
                        </div>
                      )}
                      {person.email && (
                        <div className="flex items-center">
                          <EnvelopeIcon className="w-4 h-4 mr-1" />
                          {person.email}
                        </div>
                      )}
                      {person.phone && (
                        <div className="flex items-center">
                          <PhoneIcon className="w-4 h-4 mr-1" />
                          {person.phone}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center space-x-2 mt-2">
                      <span className={`badge ${
                        person.status === 'active' 
                          ? 'badge-success' 
                          : 'badge-secondary'
                      }`}>
                        {person.status === 'active' ? 'Ativo' : 'Inativo'}
                      </span>
                      {person.recognition_count > 0 && (
                        <span className="text-xs text-muted">
                          {person.recognition_count} reconhecimentos
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleEditPerson(person)}
                    className="p-2 text-muted hover:text-primary transition-colors"
                    title="Editar"
                  >
                    <PencilIcon className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => handleDeletePerson(person.id, person.name)}
                    className="p-2 text-muted hover:text-error transition-colors"
                    title="Excluir"
                  >
                    <TrashIcon className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
          
          {people.length === 0 && (
            <div className="p-12 text-center">
              <UserIcon className="w-16 h-16 text-muted mx-auto mb-4" />
              <h3 className="text-lg font-medium text-primary mb-2">Nenhuma pessoa encontrada</h3>
              <p className="text-secondary">Comece cadastrando a primeira pessoa do sistema.</p>
            </div>
          )}
        </div>
      </div>

      {/* Modal de Adição - Simplificado e Prático */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="modal-bg rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto border border-color">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-semibold text-primary">Cadastrar Nova Pessoa</h3>
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setCapturedImage(null);
                  setFormData({
                    name: '', department: '', position: '', email: '', phone: '', tags: ''
                  });
                }}
                className="text-muted hover:text-primary transition-colors"
              >
                <XMarkIcon className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleAddPerson} className="space-y-6">
              {/* Informações Pessoais */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Nome Completo *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    className="input"
                    placeholder="Ex: João Silva"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Departamento/Setor
                  </label>
                  <input
                    type="text"
                    value={formData.department}
                    onChange={(e) => setFormData({...formData, department: e.target.value})}
                    className="input"
                    placeholder="Ex: TI, RH, 3º Ano A, Administração, etc."
                    list="department-suggestions"
                  />
                  <datalist id="department-suggestions">
                    {departmentOptions.map(dept => (
                      <option key={dept} value={dept} />
                    ))}
                  </datalist>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Cargo/Função
                  </label>
                  <input
                    type="text"
                    value={formData.position}
                    onChange={(e) => setFormData({...formData, position: e.target.value})}
                    className="input"
                    placeholder="Ex: Analista, Gerente, Diretor"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                    className="input"
                    placeholder="joao@empresa.com"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Telefone
                  </label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                    className="input"
                    placeholder="(11) 99999-9999"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Observações
                  </label>
                  <input
                    type="text"
                    value={formData.tags}
                    onChange={(e) => setFormData({...formData, tags: e.target.value})}
                    className="input"
                    placeholder="Informações adicionais"
                  />
                </div>
              </div>

              {/* Captura de Foto */}
              <div className="border-t pt-6">
                <h4 className="text-lg font-medium text-gray-900 mb-4">Captura de Foto</h4>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Seleção de Câmera */}
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-2">
                      Selecionar Câmera
                    </label>
                    <select
                      value={selectedCameraId}
                      onChange={(e) => setSelectedCameraId(e.target.value)}
                      className="input"
                    >
                      <option value="">Selecione uma câmera</option>
                      {cameras.map(camera => (
                        <option key={camera.id} value={camera.id}>
                          {camera.name} ({camera.location || 'Sem localização'})
                        </option>
                      ))}
                    </select>
                    
                    {/* Botão WebRTC removido
                    <button
                      type="button"
                      onClick={handleOpenWebRTCCapture}
                      disabled={!selectedCameraId}
                      className="mt-3 w-full flex items-center justify-center px-4 py-2 btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <VideoCameraIcon className="w-5 h-5 mr-2" />
                      Capturar Foto via WebRTC
                    </button>
                    */}
                  </div>
                  
                  {/* Preview da Foto */}
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-2">
                      Foto Capturada
                    </label>
                    <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center">
                      {capturedImage ? (
                        <div className="relative">
                          <img
                            src={capturedImage}
                            alt="Foto capturada"
                            className="w-full h-48 object-cover rounded-lg"
                          />
                          <button
                            type="button"
                            onClick={() => setCapturedImage(null)}
                            className="absolute top-2 right-2 p-1 bg-red-600 text-white rounded-full hover:bg-red-700"
                          >
                            <XMarkIcon className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="py-8">
                          <PhotoIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                          <p className="text-gray-500">
                            Nenhuma foto capturada
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Botões */}
              <div className="flex justify-end space-x-4 pt-6 border-t">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false);
                    setCapturedImage(null);
                    setFormData({
                      name: '', department: '', position: '', email: '', phone: '', tags: ''
                    });
                  }}
                  className="px-4 py-2 border border-gray-300 text-secondary rounded-lg hover:bg-gray-50"
                >
                  Cancelar
                </button>
                
                <button
                  type="submit"
                  disabled={!formData.name.trim() || !capturedImage || isProcessingRegistration}
                  className="px-6 py-2 btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                  {isProcessingRegistration ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Processando...
                    </>
                  ) : (
                    <>
                      <CheckIcon className="w-4 h-4 mr-2" />
                      Cadastrar Pessoa
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal de Edição */}
      {showEditModal && editingPerson && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-semibold text-gray-900">Editar Pessoa</h3>
              <button
                onClick={() => {
                  setShowEditModal(false);
                  setEditingPerson(null);
                  setCapturedImage(null);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleUpdatePerson} className="space-y-6">
              {/* Informações Pessoais */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Nome Completo *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    className="input"
                    placeholder="Ex: João Silva"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Departamento/Setor
                  </label>
                  <input
                    type="text"
                    value={formData.department}
                    onChange={(e) => setFormData({...formData, department: e.target.value})}
                    className="input"
                    placeholder="Ex: TI, RH, 3º Ano A, Administração, etc."
                    list="edit-department-suggestions"
                  />
                  <datalist id="edit-department-suggestions">
                    {departmentOptions.map(dept => (
                      <option key={dept} value={dept} />
                    ))}
                  </datalist>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Cargo/Função
                  </label>
                  <input
                    type="text"
                    value={formData.position}
                    onChange={(e) => setFormData({...formData, position: e.target.value})}
                    className="input"
                    placeholder="Ex: Analista, Gerente, Diretor"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({...formData, email: e.target.value})}
                    className="input"
                    placeholder="joao@empresa.com"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Telefone
                  </label>
                  <input
                    type="tel"
                    value={formData.phone}
                    onChange={(e) => setFormData({...formData, phone: e.target.value})}
                    className="input"
                    placeholder="(11) 99999-9999"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Observações
                  </label>
                  <input
                    type="text"
                    value={formData.tags}
                    onChange={(e) => setFormData({...formData, tags: e.target.value})}
                    className="input"
                    placeholder="Informações adicionais"
                  />
                </div>
              </div>

              {/* Foto Atual e Nova Captura */}
              <div className="border-t pt-6">
                <h4 className="text-lg font-medium text-gray-900 mb-4">Foto da Pessoa</h4>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Foto Atual */}
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-2">
                      Foto Atual
                    </label>
                    <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center">
                      <div className="relative">
                        <img
                          src={ApiService.getPersonImage(editingPerson.id)}
                          alt="Foto atual"
                          className="w-full h-48 object-cover rounded-lg"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none';
                            e.currentTarget.nextElementSibling?.classList.remove('hidden');
                          }}
                        />
                        <div className="hidden py-8">
                          <UserIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                          <p className="text-gray-500">Foto não disponível</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Nova Foto */}
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-2">
                      Capturar Nova Foto (Opcional)
                    </label>
                    
                    <div className="space-y-4">
                      {/* Seleção de Câmera */}
                      <div>
                        <select
                          value={selectedCameraId}
                          onChange={(e) => setSelectedCameraId(e.target.value)}
                          className="input"
                        >
                          <option value="">Selecione uma câmera</option>
                          {cameras.map(camera => (
                            <option key={camera.id} value={camera.id}>
                              {camera.name} ({camera.location || 'Sem localização'})
                            </option>
                          ))}
                        </select>
                        
                        {/* Botão WebRTC removido
                        <button
                          type="button"
                          onClick={handleOpenWebRTCCapture}
                          disabled={!selectedCameraId}
                          className="mt-3 w-full flex items-center justify-center px-4 py-2 btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <VideoCameraIcon className="w-5 h-5 mr-2" />
                          Capturar Nova Foto
                        </button>
                        */}
                      </div>
                      
                      {/* Preview da Nova Foto */}
                      <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 text-center">
                        {capturedImage ? (
                          <div className="relative">
                            <img
                              src={capturedImage}
                              alt="Nova foto capturada"
                              className="w-full h-48 object-cover rounded-lg"
                            />
                            <button
                              type="button"
                              onClick={() => setCapturedImage(null)}
                              className="absolute top-2 right-2 p-1 bg-red-600 text-white rounded-full hover:bg-red-700"
                            >
                              <XMarkIcon className="w-4 h-4" />
                            </button>
                            <div className="mt-2 text-sm text-green-600">
                              ✅ Nova foto será salva
                            </div>
                          </div>
                        ) : (
                          <div className="py-8">
                            <PhotoIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                            <p className="text-gray-500">
                              Nenhuma nova foto capturada
                            </p>
                            <p className="text-xs text-gray-400 mt-2">
                              A foto atual será mantida
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Botões */}
              <div className="flex justify-end space-x-4 pt-6 border-t">
                <button
                  type="button"
                  onClick={() => {
                    setShowEditModal(false);
                    setEditingPerson(null);
                    setCapturedImage(null);
                  }}
                  className="px-4 py-2 border border-gray-300 text-secondary rounded-lg hover:bg-gray-50"
                >
                  Cancelar
                </button>
                
                <button
                  type="submit"
                  disabled={!formData.name.trim() || isProcessingRegistration}
                  className="px-6 py-2 btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                  {isProcessingRegistration ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Processando...
                    </>
                  ) : (
                    <>
                      <CheckIcon className="w-4 h-4 mr-2" />
                      Salvar Alterações
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* WebRTC Capture Modal - Componente removido
      <WebRTCCapture
        cameraId={selectedCameraId}
        onCapture={handleWebRTCCapture}
        onClose={() => setShowWebRTCCapture(false)}
        isOpen={showWebRTCCapture}
      />
      */}
    </div>
  );
};

export default PeopleManager;