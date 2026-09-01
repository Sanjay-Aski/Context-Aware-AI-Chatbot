# ChatModel Frontend

React and Vite interface for the ChatModel FastAPI backend. The app supports multiple conversations, Markdown-rendered replies and tables, multi-file attachments, conversation deletion, and full JSON history export.

## Development

```powershell
npm install
npm run dev
```

Run the backend separately; the Vite development server proxies `/api` requests to `http://127.0.0.1:8000`.

## Checks

```powershell
npm run lint
npm run build
```

See the [project README](../README.md) for backend setup, environment configuration, attachment support, and run instructions.
