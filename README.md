# ChatModel

A React chat frontend and FastAPI backend with MongoDB conversation storage, LangChain prompt and history formatting, and direct Ollama Cloud inference through the official async Python SDK.

## Backend setup

1. Copy `Backend/.env.example` to `Backend/.env` and set `MONGO_URL` and `OLLAMA_API_KEY`.
2. Install backend packages from the project root:

   ```bash
   python -m pip install -r Backend/requirements.txt
   ```

3. Start FastAPI from the `Backend` directory:

   ```bash
   python server.py
   ```

The API starts on `http://127.0.0.1:8000`. Visit `/api/health` to check backend, MongoDB, and Cloud configuration status.

## Frontend setup

```bash
cd Frontend
npm install
npm run dev
```

Vite serves the app on port 5173 and proxies `/api` requests to the backend on port 8000. The Ollama API key stays in `Backend/.env` and is never sent to the browser.

## Attachments

The chat accepts up to eight files per message (25 MB each by default). PDF, DOCX, PPTX, XLSX, CSV/TSV, common source-code and text files, images, audio, and video are processed for model context. Original file bytes are stored in MongoDB GridFS and displayed as downloadable attachment cards. Scanned PDF pages and video frames are sampled for visual context. Audio and video speech are transcribed with `faster-whisper` on the backend; its small `tiny` model is downloaded on first use. Limits and transcription settings are configurable in `Backend/.env`.

Assistant messages render GitHub-style Markdown, including horizontally scrollable tables. The three-dot menu on a conversation can delete it or export the complete history as JSON, including attached binary files encoded as Base64.
