# ChatModel Frontend

React and Vite frontend for the FastAPI chat backend. Development requests under `/api` are proxied to `http://127.0.0.1:8000`.

## Run

```bash
npm install
npm run dev
```

The app keeps a browser session ID and supports multiple conversations, message history, and text file attachments. Backend API errors appear above the composer, and failed sends keep the draft available for retry.
