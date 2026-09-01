# ChatModel

A full-stack AI chat workspace with a React/Vite frontend and FastAPI backend. Conversations are stored in MongoDB, prompts and history are formatted with LangChain, and responses are generated through Ollama Cloud using the official async Python SDK.

## Features

- Multiple conversations with persistent message history.
- Assistant replies rendered as GitHub-style Markdown, including tables, lists, and code blocks.
- Per-conversation actions to delete a chat or export its complete history as JSON. Exports include attachment bytes encoded as Base64.
- Multi-file attachments shown as cards in the conversation and stored in MongoDB GridFS.
- File content extraction for PDF, DOCX, PPTX, XLSX, CSV/TSV, text, and common source-code files including Python, Java, C, and C++.
- Image understanding and sampled video frames sent as visual context to the model.
- Audio and video speech transcription using `faster-whisper` on the backend.

## Requirements

- Python 3.10 or newer.
- Node.js and npm.
- A running MongoDB instance. The default connection is `mongodb://localhost:27017`.
- An Ollama Cloud API key.

## Configuration

Copy the example environment file and add your Ollama Cloud key:

```powershell
Copy-Item Backend/.env.example Backend/.env
```

Set `OLLAMA_API_KEY` in `Backend/.env`. The default model is `gemma4:31b`; `OLLAMA_BASE_URL` defaults to `https://ollama.com`. Keep the API key in the backend environment file; the frontend does not need it.

Other backend settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `DB_NAME` | `chatmodel` | Database name |
| `OLLAMA_MODEL` | `gemma4:31b` | Ollama Cloud model identifier |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Model request timeout |
| `MAX_UPLOAD_SIZE_MB` | `25` | Maximum size per attachment |
| `MAX_FILES_PER_MESSAGE` | `8` | Maximum attachments per message |
| `AUDIO_TRANSCRIPTION_MODEL` | `tiny` | faster-whisper model used for audio/video transcription |

The first audio or video transcription may download the configured faster-whisper model. Device and compute settings can be changed with `AUDIO_TRANSCRIPTION_DEVICE` and `AUDIO_TRANSCRIPTION_COMPUTE_TYPE`.

## Run locally

Start the backend in one terminal from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Backend/requirements.txt
python Backend/server.py
```

If you already have a virtual environment, activate it and skip the first three setup commands. The API runs at `http://127.0.0.1:8000`. Check its status at `http://127.0.0.1:8000/api/health`.

Start the frontend in another terminal:

```powershell
cd Frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). Vite proxies `/api` requests to the backend on port 8000.

## Tests and checks

Run backend tests from `Backend`:

```powershell
python -m unittest discover -s tests -v
python -m py_compile server.py file_readers.py
```

Run frontend checks from `Frontend`:

```powershell
npm run lint
npm run build
```

## Notes

- MongoDB stores chats and message metadata; original uploaded file bytes are kept in GridFS rather than embedded in chat documents.
- The model receives extracted text and supported image content. Audio is transcribed locally before the transcript is sent to Ollama Cloud.
- The backend has no local Ollama model fallback; it requires a configured Ollama Cloud key and a reachable Cloud endpoint.
