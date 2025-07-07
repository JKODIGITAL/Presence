/**
 * API Service - Comunicação com o backend
 */

// Get API URL from environment or default
const getApiUrl = (): string => {
  console.log('Configurando URL da API...');
  
  // Para depuração: imprimir variáveis de ambiente disponíveis
  console.log('VITE_API_URL = ', (import.meta as any)?.env?.VITE_API_URL);
  console.log('window.location = ', window.location.hostname, window.location.port);
  
  // Try to get from meta env (Vite) first - ALWAYS prioritize this
  const metaEnv = (import.meta as any)?.env?.VITE_API_URL;
  if (metaEnv && metaEnv.trim() !== '') {
    console.log('✅ Usando VITE_API_URL do ambiente:', metaEnv);
    return metaEnv;
  }
  
  // Check if we're in browser environment
  if (typeof window !== 'undefined') {
    // Para desenvolvimento local (localhost ou 127.0.0.1)
    const isLocalDev = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1';
    
    if (isLocalDev) {
      // Para desenvolvimento local Windows nativo, usar porta da API
      console.log('✅ Desenvolvimento local detectado, usando porta da API 17234');
      return 'http://localhost:17234';
    }
    
    // Docker environment detection
    // Se estamos rodando na porta 3000 mas não é localhost, provavelmente é Docker
    if (window.location.port === '3000') {
      console.log('✅ Docker environment detectado, usando URLs relativas');
      return '';  // No Docker, o proxy deve funcionar com URLs relativas
    }
    
    // Se não for localhost/127.0.0.1, provavelmente estamos em produção
    const productionUrl = `http://${window.location.hostname}:17234`;
    console.log('✅ Ambiente de produção detectado, usando:', productionUrl);
    return productionUrl;
  }
  
  // Default fallback
  console.log('⚠️ Usando URL de fallback: http://localhost:17234');
  return 'http://localhost:17234';
};

const API_BASE_URL = getApiUrl();

console.log('API Base URL:', API_BASE_URL);

// Uso de API_VERSION para garantir que estamos usando a versão correta da API
const API_VERSION = 'v1';

export interface Person {
  id: string;
  name: string;
  department?: string;
  email?: string;
  phone?: string;
  is_unknown: boolean;
  thumbnail_path?: string;
  first_seen: string;
  last_seen: string;
  recognition_count: number;
  confidence: number;
  status: string;
  detection_enabled: boolean;
  tags?: string;
  created_at: string;
  updated_at: string;
}

export interface Camera {
  id: string;
  name: string;
  url: string;
  type: "ip" | "webcam" | "video";
  status: "active" | "inactive" | "error" | "testing";
  fps: number;
  resolution_width: number;
  resolution_height: number;
  fps_limit: number;
  location?: string;
  description?: string;
  last_frame_at?: string;
  created_at: string;
  updated_at: string;
  
  // New validation and performance fields
  connection_quality?: number;
  last_connection_test?: string;
  connection_test_result?: string;
  actual_fps?: number;
  latency_ms?: number;
  packet_loss_percent?: number;
  bandwidth_mbps?: number;
  manufacturer?: string;
  model?: string;
  firmware_version?: string;
  has_ptz?: boolean;
  has_audio?: boolean;
  has_recording?: boolean;
  supports_onvif?: boolean;
  config?: string;
  rtsp_transport?: string;
  connection_timeout?: number;
  reconnect_attempts?: number;
  is_enabled?: boolean;
  auto_reconnect?: boolean;
  last_error?: string;
  error_count?: number;
  codec?: string;
  ip_address?: string;
  port?: number;
  username?: string;
  password?: string;
  stream_path?: string;
}

export interface CameraValidationResult {
  success: boolean;
  connection_quality: number;
  test_duration: number;
  errors: Array<{
    message: string;
    type: string;
    timestamp: string;
  }>;
  warnings: Array<{
    message: string;
    timestamp: string;
  }>;
  metrics: {
    connection_time_ms?: number;
    first_frame_received?: boolean;
    frame_shape?: number[];
    frames_received?: number;
    frames_expected?: number;
    fps_measured?: number;
    avg_frame_quality?: number;
    quality_stability?: number;
    frame_drop_rate?: number;
    avg_latency_ms?: number;
    max_latency_ms?: number;
    min_latency_ms?: number;
    jitter_ms?: number;
    latency_quality?: number;
    stability_rate?: number;
    total_frames_stability_test?: number;
  };
  capabilities: {
    protocol?: string;
    hostname?: string;
    port?: number;
    actual_resolution?: {
      width: number;
      height: number;
    };
    fps?: number;
    max_resolution?: {
      width: number;
      height: number;
    };
    supported_resolutions?: Array<{
      width: number;
      height: number;
    }>;
    image_controls?: {
      brightness?: boolean;
      contrast?: boolean;
      saturation?: boolean;
    };
    authentication_working?: boolean;
    authentication_required?: boolean;
  };
  suggested_settings: {
    [category: string]: string[];
  };
}

export interface CameraMetrics {
  camera_id: string;
  name: string;
  status: string;
  connection_quality: number;
  last_test?: string;
  performance: {
    actual_fps?: number;
    latency_ms?: number;
    packet_loss_percent?: number;
    bandwidth_mbps?: number;
  };
  configuration: {
    resolution: string;
    fps_limit: number;
    codec?: string;
    transport?: string;
  };
  health: {
    is_healthy: boolean;
    error_count: number;
    last_error?: string;
    last_frame_at?: string;
  };
  capabilities?: any;
}

export interface ValidationHistoryEntry {
  test_date: string;
  result: CameraValidationResult;
}

export interface OptimizationRecommendation {
  current_performance: {
    connection_quality: number;
    avg_latency?: number;
    fps_measured?: number;
    frame_drop_rate?: number;
  };
  optimization_suggestions: {
    [category: string]: string[];
  };
  recommended_changes: Array<{
    setting: string;
    current: any;
    suggested: any;
    reason: string;
  }>;
}

export interface RecognitionLog {
  id: number;
  person_id: string;
  person_name?: string;
  camera_id: string;
  camera_name?: string;
  confidence: number;
  bounding_box?: string;
  frame_path?: string;
  timestamp: string;
  is_unknown: boolean;
}

export interface SystemInfo {
  version: string;
  build_date: string;
  platform: string;
  memory: {
    total: number;
    used: number;
    available: number;
    percent: number;
  };
  disk: {
    total: number;
    used: number;
    free: number;
    percent: number;
  };
  uptime: string;
  settings: {
    confidence_threshold: number;
    similarity_threshold?: number;
    unknown_accuracy_threshold?: number;
    use_gpu: boolean;
    max_cameras: number;
  };
  os_info?: string;
  python_version?: string;
  total_memory?: number;
  cpu_cores?: number;
  gpu_info?: string;
}

export interface UnknownPerson {
  id: string;
  image_data?: string;
  embedding_data?: string;
  bbox_data?: string;
  confidence: number;
  quality_score?: number;
  camera_id: string;
  detected_at: string;
  status: string;
  identified_as_person_id?: string;
  identified_at?: string;
  identified_by?: string;
  frame_count?: number;
  presence_duration?: number;
  additional_data?: string;
  created_at: string;
  updated_at: string;
}

export interface Stats {
  total_people: number;
  active_people: number;
  unknown_people: number;
  recent_recognitions: number;
  total_cameras: number;
  active_cameras: number;
  inactive_cameras: number;
  error_cameras: number;
  frames_processed_today: number;
  total_recognitions_today: number;
  total_recognitions_week: number;
  total_recognitions_month: number;
  unique_people_today: number;
  unknown_faces_today: number;
  avg_confidence: number;
}

class ApiServiceClass {
  private baseUrl = API_BASE_URL;

  // Expose baseUrl as a public getter
  getBaseUrl(): string {
    return this.baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    try {
      console.log(`🔄 Fazendo requisição para: ${this.baseUrl}${endpoint}`);
      
      // Configurar timeout para 30 segundos
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);
      
      const defaultOptions: RequestInit = {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        signal: controller.signal,
      };
      
      const mergedOptions = {
        ...defaultOptions,
        ...options,
      };
      
      const response = await fetch(`${this.baseUrl}${endpoint}`, mergedOptions);
      clearTimeout(timeoutId);
      
      // Verificar se é uma resposta de erro
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`❌ Erro ${response.status}: ${errorText}`);
        
        let errorJson;
        try {
          errorJson = JSON.parse(errorText);
        } catch {
          errorJson = { detail: errorText };
        }
        
        throw new Error(errorJson.detail || `Erro ${response.status}`);
      }
      
      // Para requests que não retornam JSON
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.indexOf('application/json') !== -1) {
        console.log('✅ Resposta JSON recebida');
        return await response.json();
      } else {
        console.log('✅ Resposta não-JSON recebida');
        return await response.text() as unknown as T;
      }
      
    } catch (error) {
      console.error('❌ Erro na requisição:', error);
      throw error;
    }
  }

  // Health & System
  async getHealth() {
    console.log('ApiService.getHealth() called, baseUrl:', this.baseUrl);
    const result = await this.request('/health');
    console.log('Health check result:', result);
    return result;
  }

  async getSystemInfo(): Promise<SystemInfo> {
    return this.request(`/api/${API_VERSION}/system/info`);
  }

  async getSystemStatus() {
    return this.request(`/api/${API_VERSION}/system/status`);
  }

  // People API
  async getPeople(params: {
    skip?: number;
    limit?: number;
    search?: string;
    department?: string;
    status?: string;
  } = {}): Promise<{ people: Person[]; total: number; page: number; per_page: number }> {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        queryParams.append(key, value.toString());
      }
    });
    
    return this.request(`/api/${API_VERSION}/people/?${queryParams}`);
  }

  async getPerson(id: string): Promise<Person> {
    return this.request(`/api/v1/people/${id}`);
  }

  async createPerson(data: {
    name: string;
    department?: string;
    email?: string;
    phone?: string;
    tags?: string;
  }): Promise<Person> {
    return this.request('/api/v1/people/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updatePerson(id: string, data: Partial<Person>): Promise<Person> {
    return this.request(`/api/v1/people/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deletePerson(id: string): Promise<{ message: string }> {
    console.log('Enviando requisição para excluir pessoa:', id);
    try {
      const url = `${this.baseUrl}/api/v1/people/${id}`;
      console.log('URL da requisição:', url);
      
      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      console.log('Status da resposta:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Erro na resposta da API:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('Resposta da exclusão:', data);
      return data;
    } catch (error) {
      console.error('Erro ao excluir pessoa:', error);
      throw error;
    }
  }

  async registerPersonWithImage(formData: FormData): Promise<Person> {
    const response = await fetch(`${this.baseUrl}/api/v1/people/register`, {
      method: 'POST',
      body: formData, // FormData já define o Content-Type correto
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async registerPersonWithCamera(formData: FormData): Promise<Person> {
    const response = await fetch(`${this.baseUrl}/api/v1/people/register-with-camera`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async registerPersonFromBase64(formData: FormData): Promise<Person> {
    const url = `${this.baseUrl}/api/v1/people/register-from-base64`;
    
    console.log('Chamando API para cadastrar pessoa com base64:', url);
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      console.log('Resposta da API:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Erro na resposta da API:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

      const data = await response.json();
      console.log('Pessoa cadastrada com sucesso:', data);
      return data;
    } catch (error) {
      console.error('Erro ao cadastrar pessoa com base64:', error);
      throw error;
    }
  }

  async registerPersonFromBase64Quick(formData: FormData): Promise<Person> {
    const url = `${this.baseUrl}/api/v1/people/register-from-base64-quick`;
    
    console.log('Chamando API para cadastrar pessoa rapidamente com base64:', url);
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      console.log('Resposta da API rápida:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Erro na resposta da API rápida:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

      const data = await response.json();
      console.log('Pessoa cadastrada rapidamente com sucesso:', data);
      return data;
    } catch (error) {
      console.error('Erro ao cadastrar pessoa rapidamente com base64:', error);
      throw error;
    }
  }

  async registerPersonWithImageQuick(formData: FormData): Promise<Person> {
    const url = `${this.baseUrl}/api/v1/people/register-quick`;
    
    console.log('Chamando API para cadastrar pessoa rapidamente com imagem:', url);
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      console.log('Resposta da API rápida:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Erro na resposta da API rápida:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

      const data = await response.json();
      console.log('Pessoa cadastrada rapidamente com sucesso:', data);
      return data;
    } catch (error) {
      console.error('Erro ao cadastrar pessoa rapidamente com imagem:', error);
      throw error;
    }
  }

  async associateUnknownToPerson(unknownId: string, personId: string): Promise<{ message: string }> {
    return this.request(`/api/v1/unknown/${unknownId}/associate`, {
      method: 'POST',
      body: JSON.stringify({ person_id: personId }),
    });
  }

  async getPeopleStats(): Promise<Stats> {
    return this.request(`/api/${API_VERSION}/people/stats`);
  }

  async getDepartmentAttendance(date?: string): Promise<{
    date: string;
    departments: Array<{
      department: string;
      total_people: number;
      recognized_today: number;
      not_recognized_today: number;
      attendance_rate: number;
    }>;
    summary: {
      total_departments: number;
      total_people: number;
      total_recognized: number;
      overall_attendance_rate: number;
    };
  }> {
    const params = date ? `?date=${date}` : '';
    return this.request(`/api/v1/people/attendance/departments${params}`);
  }

  async getMissingPeople(department?: string, date?: string): Promise<{
    date: string;
    department_filter?: string;
    missing_people: Array<{
      id: string;
      name: string;
      department: string;
      email?: string;
      phone?: string;
      last_seen?: string;
      recognition_count: number;
    }>;
    count: number;
  }> {
    const params = new URLSearchParams();
    if (department) params.append('department', department);
    if (date) params.append('date', date);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return this.request(`/api/v1/people/attendance/missing${queryString}`);
  }

  // Cameras API
  async getCameras(params: {
    skip?: number;
    limit?: number;
    status?: string;
    camera_type?: string;
  } = {}): Promise<{ cameras: Camera[]; total: number; active: number; inactive: number; error: number }> {
    try {
      console.log('Buscando câmeras com parâmetros:', params);
      
      // Construir query string
      const queryParams = new URLSearchParams();
      if (params.skip !== undefined) queryParams.append('skip', params.skip.toString());
      if (params.limit !== undefined) queryParams.append('limit', params.limit.toString());
      if (params.status) queryParams.append('status', params.status);
      if (params.camera_type) queryParams.append('camera_type', params.camera_type);
      
      const queryString = queryParams.toString();
      const endpoint = `/api/${API_VERSION}/cameras${queryString ? `?${queryString}` : ''}`;
      
      console.log(`Endpoint: ${endpoint}`);
      return await this.request<{ cameras: Camera[]; total: number; active: number; inactive: number; error: number }>(endpoint);
    } catch (error) {
      console.error('Erro ao buscar câmeras:', error);
      throw error;
    }
  }

  async getCamera(id: string): Promise<Camera> {
    return this.request(`/api/v1/cameras/${id}`);
  }

  async createCameraSimple(
    data: {
      name: string;
      url: string;
      type: string;
      fps?: number;
      resolution_width?: number;
      resolution_height?: number;
      fps_limit?: number;
      location?: string;
      description?: string;
      username?: string;
      password?: string;
    }
  ): Promise<Camera> {
    console.log('📡 Enviando dados para endpoint simples:', data);
    return this.request(`/api/v1/cameras/simple`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async uploadVideoCamera(formData: FormData): Promise<Camera> {
    console.log('📹 Fazendo upload de vídeo para câmera');
    const response = await fetch(`${this.baseUrl}/api/v1/cameras/upload-video`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    return response.json();
  }

  async createCamera(
    data: {
      name: string;
      url: string;
      type: string;
      fps?: number;
      resolution_width?: number;
      resolution_height?: number;
      fps_limit?: number;
      location?: string;
      description?: string;
      username?: string;
      password?: string;
    },
    validate: boolean = true,
    validation_type: string = "basic"
  ): Promise<Camera & { validation_result?: CameraValidationResult }> {
    const queryParams = new URLSearchParams();
    queryParams.append('validate', validate.toString());
    queryParams.append('validation_type', validation_type);
    
    return this.request(`/api/v1/cameras/?${queryParams}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateCamera(cameraId: string, cameraData: Partial<Camera>): Promise<Camera> {
    const response = await fetch(`${this.baseUrl}/api/v1/cameras/${cameraId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(cameraData),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async updateCameraConfig(cameraId: string, configData: Record<string, any>): Promise<Camera> {
    const response = await fetch(`${this.baseUrl}/api/v1/cameras/${cameraId}/config`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(configData),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    console.log(`Configuração da câmera ${cameraId} atualizada com sucesso`);
    return response.json();
  }

  async disableCamera(cameraId: string): Promise<any> {
    return this.request(`/api/v1/cameras/${cameraId}/disable`, {
      method: 'POST',
    });
  }

  async deleteCamera(id: string): Promise<{ message: string }> {
    return this.request(`/api/v1/cameras/${id}`, {
      method: 'DELETE',
    });
  }

  async testCameraConnection(
    id: string, 
    test_type: string = "basic"
  ): Promise<{
    camera_id: string;
    test_type: string;
    success: boolean;
    connection_quality: number;
    test_duration: number;
    metrics: any;
    capabilities: any;
    errors: any[];
    warnings: any[];
    suggestions: any;
    tested_at: string;
  }> {
    return this.request(`/api/v1/cameras/${id}/test?test_type=${test_type}`, {
      method: 'POST',
    });
  }

  // Nova API de validação pré-cadastro
  async validateCameraBeforeCreation(
    url: string,
    username?: string,
    password?: string,
    test_type: string = "full"
  ): Promise<{
    url: string;
    validation_type: string;
    success: boolean;
    connection_quality: number;
    test_duration: number;
    metrics: any;
    capabilities: any;
    errors: any[];
    warnings: any[];
    suggestions: any;
    recommended_settings: any;
    validated_at: string;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('url', url);
    queryParams.append('test_type', test_type);
    if (username) queryParams.append('username', username);
    if (password) queryParams.append('password', password);
    
    return this.request(`/api/v1/cameras/validate?${queryParams}`, {
      method: 'POST',
    });
  }

  // Histórico de validações
  async getCameraValidationHistory(
    camera_id: string,
    limit: number = 10
  ): Promise<{
    camera_id: string;
    validation_history: ValidationHistoryEntry[];
    total_tests: number;
  }> {
    return this.request(`/api/v1/cameras/${camera_id}/validation/history?limit=${limit}`);
  }

  // Métricas detalhadas da câmera
  async getCameraMetrics(camera_id: string): Promise<CameraMetrics> {
    return this.request(`/api/v1/cameras/${camera_id}/metrics`);
  }

  // Recomendações de otimização
  async getCameraOptimizationRecommendations(camera_id: string): Promise<OptimizationRecommendation> {
    return this.request(`/api/v1/cameras/${camera_id}/optimize`, {
      method: 'POST',
    });
  }

  async updateCameraStatus(id: string, status: string): Promise<{ message: string }> {
    return this.request(`/api/v1/cameras/${id}/status?status=${status}`, {
      method: 'PUT',
    });
  }

  async getCameraStats(): Promise<Stats> {
    return this.request('/api/v1/cameras/stats');
  }

  async captureFromCamera(cameraId: string): Promise<{
    success: boolean;
    image_data: string;
    image_format: string;
    camera_id: string;
    camera_name: string;
    timestamp: string;
  }> {
    console.log('Enviando requisição para capturar imagem da câmera:', cameraId);
    try {
      const url = `${this.baseUrl}/api/v1/cameras/${cameraId}/capture`;
      console.log('URL da requisição:', url);
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      console.log('Status da resposta:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Erro na resposta da API:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('Dados da resposta recebidos, imagem presente:', !!data.image_data);
      return data;
    } catch (error) {
      console.error('Erro ao capturar imagem da câmera:', error);
      throw error;
    }
  }

  // Recognition API
  async getRecognitionLogs(params: {
    skip?: number;
    limit?: number;
    camera_id?: string;
    person_id?: string;
    is_unknown?: boolean;
    start_date?: string;
    end_date?: string;
  } = {}): Promise<{ logs: RecognitionLog[]; total: number; page: number; per_page: number }> {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        queryParams.append(key, value.toString());
      }
    });
    
    return this.request(`/api/v1/recognition/logs?${queryParams}`);
  }

  async getRecognitionStats(): Promise<Stats> {
    return this.request('/api/v1/recognition/stats');
  }

  async getStreamStatus(cameraId: string): Promise<any> {
    return this.request(`/api/v1/recognition/stream/${cameraId}/status`);
  }


  // Unknown People API
  async getUnknownPeople(params: {
    skip?: number;
    limit?: number;
  } = {}): Promise<{ unknown_people: UnknownPerson[]; total: number; page: number; per_page: number }> {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        queryParams.append(key, value.toString());
      }
    });
    
    return this.request(`/api/v1/unknown/?${queryParams}`);
  }

  async getUnknownPerson(id: string): Promise<UnknownPerson> {
    return this.request(`/api/v1/unknown/${id}`);
  }

  async getUnknownPersonImage(id: string): Promise<string> {
    return `${this.baseUrl}/api/v1/unknown/${id}/image`;
  }

  async identifyUnknown(id: string, data: {
    name: string;
    department?: string;
    email?: string;
    phone?: string;
    tags?: string;
  }): Promise<Person> {
    return this.request(`/api/v1/unknown/${id}/identify`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateUnknownPerson(id: string, data: {
    name?: string;
    tags?: string;
  }): Promise<{ message: string }> {
    return this.request(`/api/v1/unknown/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteUnknownPerson(id: string): Promise<{ message: string }> {
    return this.request(`/api/v1/unknown/${id}`, {
      method: 'DELETE',
    });
  }

  async registerUnknownPerson(formData: FormData): Promise<Person> {
    const response = await fetch(`${this.baseUrl}/api/v1/unknown/register`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async getUnknownPeopleStats(): Promise<{
    total_unknown: number;
    recent_unknown: number;
    with_images: number;
    without_images: number;
  }> {
    return this.request('/api/v1/unknown/stats/summary');
  }

  // Unknown Person Management Methods
  async identifyUnknownPerson(unknownId: string, personId: string): Promise<{ message: string }> {
    return this.request(`/api/v1/unknown/${unknownId}/identify/${personId}`, {
      method: 'POST',
    });
  }

  async ignoreUnknownPerson(unknownId: string): Promise<{ message: string }> {
    return this.request(`/api/v1/unknown/${unknownId}/ignore`, {
      method: 'POST',
    });
  }

  // Person Image API
  async getPersonImage(id: string): Promise<string> {
    return `${this.baseUrl}/api/v1/people/${id}/image`;
  }

  async updatePersonImage(id: string, formData: FormData): Promise<Person> {
    const response = await fetch(`${this.baseUrl}/api/v1/people/${id}/image`, {
      method: 'PUT',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async updatePersonWithPhoto(id: string, formData: FormData): Promise<Person> {
    console.log('📤 Enviando atualização com foto para:', `${this.baseUrl}/api/v1/people/${id}/update-with-photo`);
    
    const response = await fetch(`${this.baseUrl}/api/v1/people/${id}/update-with-photo`, {
      method: 'PUT',
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    return response.json();
  }

  async validatePersonFace(id: string): Promise<{
    success: boolean;
    message: string;
    faces_detected: number;
    validation_status: string;
    face_quality?: number;
  }> {
    const response = await fetch(`${this.baseUrl}/api/v1/people/${id}/validate-face`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  // Utility methods
  formatDateTime(dateString: string): string {
    return new Date(dateString).toLocaleString('pt-BR');
  }

  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString('pt-BR');
  }

  formatTime(dateString: string): string {
    return new Date(dateString).toLocaleTimeString('pt-BR');
  }

  formatBytes(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatPercentage(value: number): string {
    return `${value.toFixed(1)}%`;
  }

  async updateSystemSettings(data: Partial<{ confidence_threshold: number; use_gpu: boolean; max_cameras: number }>): Promise<{ message: string; updated: any }> {
    return this.request('/api/v1/system/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // Configurações de reconhecimento facial
  async getRecognitionSettings(): Promise<any> {
    return this.request('/api/v1/system/recognition-settings');
  }

  async updateRecognitionSettings(settings: any): Promise<any> {
    return this.request('/api/v1/system/recognition-settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // Performance Monitoring API
  async getPerformanceStats(): Promise<any> {
    return this.request('/api/v1/system/performance');
  }

  async getGStreamerStats(): Promise<any> {
    return this.request('/api/v1/system/gstreamer-stats');
  }

  async getRecognitionWorkerStats(): Promise<any> {
    return this.request('/api/v1/system/recognition-worker-stats');
  }

  async getCudaStatus(): Promise<any> {
    return this.request('/api/v1/system/cuda-status');
  }

  // Usar pipeline alternativo para câmera problemática
  async useAltPipeline(cameraId: string): Promise<any> {
    return this.request(`/api/v1/cameras/${cameraId}/use-alt-pipeline`, {
      method: 'POST',
    });
  }

}

export const ApiService = new ApiServiceClass();