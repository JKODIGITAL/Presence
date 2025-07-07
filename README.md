# Presence - Sistema de Reconhecimento Facial

Sistema de reconhecimento facial em tempo real com streaming WebRTC, desenvolvido para identificação e monitoramento de pessoas em múltiplas câmeras.

## 🚀 Características

- **Reconhecimento Facial em Tempo Real**: Utiliza InsightFace e FAISS para detecção e reconhecimento de faces
- **Pipeline Unificado**: Suporte para câmeras RTSP e arquivos de vídeo MP4 com o mesmo pipeline GStreamer
- **Streaming WebRTC**: Transmissão em tempo real para navegadores usando aiortc
- **Arquitetura Multi-Ambiente**: MSYS2 para GStreamer e Conda para ML/AI
- **Performance Worker**: Processamento paralelo com multiprocessing
- **Comunicação Socket.IO**: Comunicação eficiente entre componentes
- **Interface Moderna**: Frontend React + TypeScript + Tauri

## 🏗️ Arquitetura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Camera Worker  │────▶│   Recognition   │────▶│  Camera Worker  │
│   (GStreamer)   │     │     Worker      │     │   (Overlay)     │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │◀────│  WebRTC Server  │◀────│  Socket.IO      │
│  (React/Tauri)  │     │    (aiortc)     │     │    Bridge       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                ▲
                                │
                        ┌───────┴────────┐
                        │   API Server   │
                        │   (FastAPI)    │
                        └────────────────┘
```

### Componentes Principais

- **Camera Worker**: Captura e processamento com GStreamer
- **Recognition Worker**: Reconhecimento facial com ML
- **WebRTC Server**: Streaming em tempo real
- **API Server**: Backend FastAPI
- **Frontend**: Interface React + TypeScript

## 🛠️ Requisitos

### Windows
- Windows 10/11
- MSYS2 UCRT64 (para GStreamer)
- Anaconda/Miniconda (para Python ML)
- NVIDIA GPU com CUDA (recomendado)

### Dependências Principais
- Python 3.10+
- GStreamer 1.22+
- CUDA 11.8+ (para GPU)
- Node.js 18+

## 📦 Instalação

### 1. Clonar o Repositório
```bash
git clone https://github.com/seu-usuario/presence.git
cd presence
```

### 2. Configurar Ambiente MSYS2
```bash
# No MSYS2 UCRT64
pacman -S mingw-w64-ucrt-x86_64-gstreamer mingw-w64-ucrt-x86_64-gst-plugins-base mingw-w64-ucrt-x86_64-gst-plugins-good mingw-w64-ucrt-x86_64-gst-plugins-bad mingw-w64-ucrt-x86_64-gst-plugins-ugly mingw-w64-ucrt-x86_64-gst-libav mingw-w64-ucrt-x86_64-gst-python mingw-w64-ucrt-x86_64-python-pip mingw-w64-ucrt-x86_64-python-numpy mingw-w64-ucrt-x86_64-opencv mingw-w64-ucrt-x86_64-python-gobject

# Instalar dependências Python
pip install python-socketio[client] loguru aiohttp
```

### 3. Configurar Ambiente Conda
```bash
# Criar ambiente
conda create -n presence python=3.10
conda activate presence

# Instalar dependências
pip install -r requirements.txt
```

### 4. Configurar Frontend
```bash
cd frontend
npm install
```

### 5. Configurar Banco de Dados
```bash
# Copiar exemplo de configuração
cp .env.example .env

# Editar .env com suas configurações
```

## 🚀 Execução

### Método Rápido (PowerShell)
```powershell
.\start-system-webrtc.ps1
```

### Método Manual

1. **API Server** (Terminal Conda)
```bash
conda activate presence
cd app
python -m uvicorn api.main:app --host 0.0.0.0 --port 17234
```

2. **Recognition Worker** (Terminal Conda)
```bash
conda activate presence
cd app/recognition_worker
python main.py
```

3. **WebRTC Server** (Terminal Conda)
```bash
conda activate presence
cd app/webrtc_worker
python vms_webrtc_server_native.py
```

4. **Camera Worker** (Terminal MSYS2)
```bash
cd app/camera_worker
python main.py
```

5. **Frontend** (Terminal Normal)
```bash
cd frontend
npm run dev
```

## 📊 Uso

1. Acesse http://localhost:1420 no navegador
2. Configure câmeras no menu "Cameras"
3. Adicione pessoas no menu "People"
4. Monitore em tempo real no "Monitoring"

## 🔧 Configuração

### Adicionar Câmera RTSP
```json
{
  "name": "Camera Principal",
  "url": "rtsp://usuario:senha@192.168.1.100:554/stream",
  "type": "rtsp",
  "fps_limit": 10
}
```

### Adicionar Arquivo de Vídeo
```json
{
  "name": "Video Teste",
  "url": "videoplayback.mp4",
  "type": "video_file",
  "fps_limit": 25
}
```

## 📝 Variáveis de Ambiente

```env
# API
API_BASE_URL=http://127.0.0.1:17234
DATABASE_URL=sqlite:///./presence.db

# Recognition Worker
RECOGNITION_WORKER_URL=http://127.0.0.1:17235
USE_GPU=true

# WebRTC
WEBRTC_PORT=17236
STUN_SERVER=stun:stun.l.google.com:19302

# Performance
USE_PERFORMANCE_WORKER=true
MAX_CAMERAS_PER_WORKER=4
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie sua feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 🙏 Agradecimentos

- [InsightFace](https://github.com/deepinsight/insightface) - Reconhecimento facial
- [FAISS](https://github.com/facebookresearch/faiss) - Busca vetorial
- [GStreamer](https://gstreamer.freedesktop.org/) - Pipeline de vídeo
- [aiortc](https://github.com/aiortc/aiortc) - WebRTC em Python

## 📞 Suporte

Para reportar bugs ou solicitar features, abra uma issue no GitHub.