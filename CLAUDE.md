# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Critical Architecture Overview

This is a **dual-environment** facial recognition system running on Windows:

1. **MSYS2 UCRT64 Environment** - For GStreamer and camera processing
   - Path: `C:\msys64\ucrt64\bin\python.exe`
   - Used by: Camera Worker
   - Key packages: GStreamer, OpenCV, PyGObject, python-socketio[client]

2. **Conda Environment (presence)** - For ML/AI and web services
   - Path: `C:\Users\Danilo\miniconda3\envs\presence`
   - Used by: API Server, Recognition Worker, WebRTC Server
   - Key packages: InsightFace, FAISS, PyTorch, aiortc, FastAPI

**NEVER mix these environments!** Each component must run in its designated environment.

## System Architecture

```
[RTSP/MP4] → [Camera Worker] → [Recognition Worker] → [Camera Worker] → [WebRTC] → [Frontend]
             (MSYS2:GStreamer)   (Conda:ML/AI)        (Overlay)        (Conda)     (Node.js)
```

### Key Communication Protocols

1. **Camera Worker ↔ Recognition Worker**: Socket.IO
   - Camera sends: `process_frame` event with `{frame_base64, camera_id, timestamp, frame_id}`
   - Recognition sends: `recognition_result` event with face data

2. **Camera Worker → WebRTC Bridge**: Socket.IO
   - Camera sends: `processed_frame` event with overlaid frames

3. **WebRTC → Frontend**: WebRTC DataChannel + Socket.IO signaling

## Common Commands

### Quick Start (PowerShell)
```powershell
.\start-system-webrtc.ps1
```

### Manual Component Start

1. **API Server** (Conda terminal):
```bash
conda activate presence
cd app
python -m uvicorn api.main:app --host 0.0.0.0 --port 17234
```

2. **Recognition Worker** (Conda terminal):
```bash
conda activate presence
cd app/recognition_worker
python main.py
```

3. **WebRTC Server** (Conda terminal):
```bash
conda activate presence
cd app/webrtc_worker
python vms_webrtc_server_native.py
```

4. **Camera Worker** (MSYS2 UCRT64 terminal):
```bash
cd app/camera_worker
python main.py
```

5. **Frontend** (Regular terminal):
```bash
cd frontend
npm run dev
```

### Testing
```bash
# Test RTSP connectivity
python test_rtsp_connectivity.py

# Test camera source
python test_camera_source.py

# Check system status
.\check-system-status.ps1
```

### Troubleshooting Socket.IO in MSYS2

If Camera Worker can't connect to Recognition Worker:

1. **Check Socket.IO installation in MSYS2 UCRT64**:
```bash
pip show python-socketio
```

2. **Install if missing**:
```bash
pip install python-socketio[client]
```

3. **Verify no environment mixing**:
```bash
which python  # Should show /ucrt64/bin/python
```

## Key Configuration Files

- `app/core/config.py` - Main configuration (Conda apps)
- `app/camera_worker/simple_config.py` - Simplified config for MSYS2
- `start-system-webrtc.ps1` - System startup script with all environment setup

## Pipeline Types

### Unified GStreamer Pipeline
Both RTSP cameras and MP4 files use the same pipeline in `app/core/performance/camera_worker.py`:

- **RTSP**: `rtspsrc` → decode → process → overlay → encode
- **MP4**: `filesrc` → `decodebin` → process → overlay → encode

The `source_type` field determines which source to use.

## Common Issues

1. **"Recognition worker não disponível"**: Socket.IO not installed in MSYS2 or connection blocked
2. **"Pipeline continua rodando apesar do warning"**: Normal for offline RTSP cameras
3. **Import errors mixing environments**: Check PATH doesn't include both Conda and MSYS2

## Database

- Location: `data/db/presence.db`
- Type: SQLite
- Models: `app/database/models.py`

## GPU Support

- Requires NVIDIA GPU with CUDA 11.8+
- Set `USE_GPU=false` to run in CPU mode
- GStreamer uses NVDEC/NVENC when available

## Port Assignments

- API Server: 17234
- Recognition Worker: 17235  
- WebRTC Server: 17236+
- Frontend Dev: 3000 (Vite) or 1420 (Tauri)

## Performance Optimization

The system uses Performance Worker mode by default (`USE_PERFORMANCE_WORKER=true`), which:
- Runs one process per camera
- Uses multiprocessing queues
- Implements frame skipping based on FPS limits

## Frontend Notes

- Framework: React + TypeScript + Tauri
- Build: Vite
- Key components: `VMSMonitor.tsx` for camera grid view
- WebRTC connections managed per camera