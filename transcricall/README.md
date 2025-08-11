## TranscriCall

Sistema de transcripción en vivo para call centers.

### Arquitectura (alto nivel)

```mermaid
flowchart LR
  subgraph Agent PC
    C[Capture Client\n(sounddevice)] -- 5s WAV --> I[Ingest API]
  end

  I -- bytes --> T[Transcriber\n(Vosk)]
  T -- texto --> DB[(SQLite)]
  T -- texto --> WS[WebSocket Manager]
  WS -- push --> FE[Frontend Dashboard]
  DB -- REST --> FE

  subgraph Backend (FastAPI)
    I
    T
    WS
    A[Analytics API]
  end
```

### Funcionalidades
- Captura de audio en vivo (micrófono / monitor Pulseaudio) en fragmentos de 5–10s
- Transcripción con Vosk (offline, gratuito). Opcional: permitir descarga automática del modelo con `ALLOW_AUTO_DOWNLOAD=1`
- Dashboard en tiempo real con WebSocket
- Buscador/filtrado por palabra clave
- Clasificación básica de "cliente caliente" por frases
- Panel de análisis: llamadas por hora, % detección de keywords, ranking de agentes, distribución de duraciones
- Almacenamiento en SQLite

### Requisitos
- Python 3.10+
- Linux con PulseAudio/ALSA. Para capturar salida del sistema use el dispositivo "Monitor" del sink.

### Instalación (local)

```bash
cd transcricall
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Windows CMD
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
# (Opcional) descarga automática de modelo pequeño en español
export ALLOW_AUTO_DOWNLOAD=1
python -c "from backend.inference import ensure_default_model; ensure_default_model('vosk','es')"
```

### Ejecutar backend

```bash
uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
```

Abrir `http://localhost:8000/` para el dashboard.

### Cliente de captura

Listar dispositivos de entrada:
```python
python -c "import sounddevice as sd;print(sd.query_devices())"
```

Grabar y enviar fragmentos de 5s desde un dispositivo específico (micrófono o monitor):
```bash
python capture/capture_client.py --backend http://localhost:8000 --agent-id AGENTE01 --chunk-seconds 5 --device 1
```

Consejo: Para audio del sistema (Linux), use un dispositivo de entrada tipo "Monitor of ...".

### Variables de entorno útiles
- `TRANSCRIBER_ENGINE=vosk` (por defecto)
- `LANGUAGE=es`
- `MODEL_PATH=/ruta/al/modelo/vosk` (si no usa el predeterminado)
- `ALLOW_AUTO_DOWNLOAD=1` descarga el modelo pequeño automáticamente si no existe
- `DB_PATH` ruta del archivo SQLite

### Endpoints clave
- `POST /ingest` ingesta de audio (multipart form: `agent_id`, `call_id` opcional, `audio` WAV 16k mono)
- `GET /transcripts` histórico con filtros `agent_id`, `q`, `since`, `until`
- `GET /analytics/summary` datos para gráficas
- `WS /ws` suscripción y broadcast en vivo (`{ action: 'subscribe', agent_id: 'all'|'AGENTE01' }`)

### Despliegue con Docker (opcional)

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY frontend frontend
ENV TRANSCRIBER_ENGINE=vosk LANGUAGE=es ALLOW_AUTO_DOWNLOAD=1
EXPOSE 8000
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t transcricall -f docker/Dockerfile .
docker run -p 8000:8000 -e ALLOW_AUTO_DOWNLOAD=1 -v $(pwd)/models:/app/models transcricall
```

### Notas de producción
- Coloque el backend detrás de un proxy (Nginx/Caddy) con TLS.
- Limite tamaño de archivos y rate-limit del endpoint `/ingest`.
- Ejecute el worker de transcripción en un threadpool o proceso separado si hay alto volumen.
- Para múltiples agentes, ejecute un cliente de captura por estación o integre con el softphone para duplicar el audio.
