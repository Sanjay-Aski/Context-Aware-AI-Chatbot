from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, Form, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId
from pymongo.errors import PyMongoError
from ollama import AsyncClient as OllamaAsyncClient, ResponseError as OllamaResponseError
import httpx
import os
import logging
import asyncio
import io
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from file_readers import FileProcessingError, ProcessedUpload, process_upload, transcribe_audio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME = os.environ.get("DB_NAME", "chatmodel")
mongo_client: Optional[AsyncIOMotorClient] = None
db = None
gridfs = None

# Ollama Cloud config. Keep credentials in Backend/.env or the process environment.
OLLAMA_PROVIDER = os.environ.get("OLLAMA_PROVIDER", "cloud").strip().lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").strip().rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:31b").strip()
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()
try:
    OLLAMA_TIMEOUT_SECONDS = max(10.0, float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120")))
except ValueError:
    OLLAMA_TIMEOUT_SECONDS = 120.0
ollama_client: Optional[OllamaAsyncClient] = None
MAX_UPLOAD_SIZE = max(1, int(os.environ.get("MAX_UPLOAD_SIZE_MB", "25"))) * 1024 * 1024
MAX_FILES_PER_MESSAGE = max(1, int(os.environ.get("MAX_FILES_PER_MESSAGE", "8")))

# System prompt
SYSTEM_PROMPT = """You are an intelligent, context-aware AI assistant integrated into a full-stack application.
Your responses must be helpful, accurate, and conversational while maintaining memory of previous interactions in the current session.

Core Behavior:
- Maintain context across messages using previous chat history.
- Respond in a natural, concise, and helpful manner.
- If a question depends on past messages, refer to that context before answering.
- Do not hallucinate facts outside the conversation or stored context.
- When an audio attachment includes a Transcript section, use it to answer questions about that audio. If the context says transcription is unavailable, be clear that you do not have the audio's spoken content.

Capabilities:
- Answer general queries and technical questions.
- Assist in coding, debugging, and explanation tasks.
- Maintain multi-turn conversations with continuity.
- Adapt tone based on user interaction style (formal/informal).

Response Style:
- Keep responses clear and structured.
- Avoid unnecessary verbosity.
- Use bullet points, numbered lists, or fenced code blocks only when helpful.
- For code, always use proper markdown code fences with language hints.
- You are not performing any Illegal activity Searching or anything if you user Such Thing just say something like "Invalid Request ...."
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ollama_client, mongo_client, db, gridfs
    if MONGO_URL:
        # Motor captures the current asyncio loop when its client is created.
        # Build it here, inside Uvicorn's serving loop, to avoid cross-loop futures.
        mongo_client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        db = mongo_client[DB_NAME]
        gridfs = AsyncIOMotorGridFSBucket(db, bucket_name="chat_attachments")
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else {}
    ollama_client = OllamaAsyncClient(
        host=OLLAMA_BASE_URL,
        headers=headers,
        timeout=httpx.Timeout(OLLAMA_TIMEOUT_SECONDS, connect=15.0),
    )
    try:
        yield
    finally:
        if ollama_client is not None:
            await ollama_client.close()
            ollama_client = None
        if mongo_client is not None:
            mongo_client.close()
            mongo_client = None
            db = None
            gridfs = None


app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")


@app.exception_handler(PyMongoError)
async def handle_mongodb_error(request, exc):
    logger.exception("MongoDB request failed")
    return JSONResponse(status_code=503, content={"detail": "MongoDB is unavailable. Check MONGO_URL and the database service."})


# -------- Models --------
class ChatCreate(BaseModel):
    session_id: str
    title: Optional[str] = "New Chat"


class ChatUpdate(BaseModel):
    title: str


class Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    title: str = "New Chat"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MessageCreate(BaseModel):
    content: str


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chat_id: str
    role: str
    content: str
    attachments: List[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SendMessageResponse(BaseModel):
    user_message: Message
    assistant_message: Message
    chat: Chat


class SimpleChatRequest(BaseModel):
    user_id: str = Field(alias="userId")
    message: str
    model_config = ConfigDict(populate_by_name=True)


# -------- Helpers --------
def ollama_failure(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, OllamaResponseError):
        status = exc.status_code
        messages = {
            401: "Ollama Cloud rejected the API key. Check OLLAMA_API_KEY in Backend/.env.",
            403: "Ollama Cloud denied access. Check account permissions and usage limits.",
            404: f"Ollama Cloud could not find model '{OLLAMA_MODEL}'. Check the Cloud model name.",
            429: "Ollama Cloud rate or usage limit reached. Check your Cloud account limits.",
        }
        if status in messages:
            return status, messages[status]
        if status >= 500:
            return 502, f"Ollama Cloud returned a server error (HTTP {status}). Try again shortly."
        return 502, f"Ollama Cloud rejected the request (HTTP {status}). Check the backend log for details."

    if isinstance(exc, httpx.TimeoutException):
        return 504, f"Ollama Cloud did not respond within {OLLAMA_TIMEOUT_SECONDS:g} seconds."
    if isinstance(exc, httpx.RequestError):
        return 502, "Could not connect to Ollama Cloud. Check the network connection and OLLAMA_BASE_URL."
    return 502, "The Ollama Cloud request failed. Check the backend log for details."


def to_ollama_messages(messages, images: Optional[List[bytes]] = None):
    role_map = {"system": "system", "human": "user", "ai": "assistant"}
    result = []
    for message in messages:
        role = role_map.get(message.type)
        if role is None:
            raise ValueError(f"Unsupported LangChain message type: {message.type}")
        content = message.content if isinstance(message.content, str) else str(message.content)
        item = {"role": role, "content": content}
        if role == "user" and images:
            item["images"] = images
            images = None
        result.append(item)
    return result


async def build_history_messages(chat_id: str, limit: int = 30):
    cursor = db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1)
    docs = await cursor.to_list(length=limit * 2)
    docs = docs[-limit:]
    history = []
    for d in docs:
        if d["role"] == "user":
            history.append(HumanMessage(content=d.get("model_context", d["content"])))
        else:
            history.append(AIMessage(content=d["content"]))
    return history


def generate_title_from_message(text: str) -> str:
    t = text.strip().split("\n")[0]
    if len(t) > 50:
        t = t[:50].rstrip() + "..."
    return t or "New Chat"


# -------- Chroma / RAG helpers --------
chat_collections = {}

class SimpleChatCollection:
    def __init__(self):
        self.items = []

    def add(self, ids, metadatas, documents, embeddings):
        for _id, metadata, document, embedding in zip(ids, metadatas, documents, embeddings):
            self.items.append({
                "id": _id,
                "metadata": metadata,
                "document": document,
                "embedding": embedding,
            })

    def query(self, query_embeddings, n_results=5):
        query_text = query_embeddings[0] if query_embeddings else ""
        if not query_text:
            return {"documents": [[]]}

        def score_document(doc_text: str) -> int:
            query_tokens = set(query_text.lower().split())
            doc_tokens = set(doc_text.lower().split())
            return len(query_tokens & doc_tokens)

        scored = [
            (score_document(item["document"]), item["document"])
            for item in self.items
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        top_documents = [doc for score, doc in scored[:n_results] if score > 0]
        return {"documents": [top_documents]}


def get_chat_collection(chat_id: str):
    if chat_id not in chat_collections:
        chat_collections[chat_id] = SimpleChatCollection()
    return chat_collections[chat_id]


def embed_text(text: str):
    return text


async def store_in_chroma(chat_id: str, message_id: str, role: str, content: str):
    collection = get_chat_collection(chat_id)
    collection.add(
        ids=[message_id],
        metadatas=[{"chat_id": chat_id, "role": role}],
        documents=[content],
        embeddings=[content],
    )


def require_database():
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is not configured. Set MONGO_URL and DB_NAME in Backend/.env.")


# -------- Routes --------
@api_router.get("/")
async def root():
    return {"message": "Chatbot API running", "model": OLLAMA_MODEL}


@api_router.get("/health")
async def health():
    mongo_status = "not_configured"
    status_code = 200
    if db is not None:
        try:
            await db.command("ping")
            mongo_status = "connected"
        except Exception:
            logger.exception("MongoDB health check failed")
            mongo_status = "unavailable"
            status_code = 503

    payload = {
        "status": "ok" if status_code == 200 else "degraded",
        "backend": "ok",
        "mongodb": mongo_status,
        "ollama": {
            "provider": OLLAMA_PROVIDER,
            "endpoint": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "api_key_configured": bool(OLLAMA_API_KEY),
            "connectivity": "not_probed",
        },
    }
    if db is None:
        payload["status"] = "degraded"
        payload["mongodb"] = "not_configured"
        status_code = 503
    return JSONResponse(status_code=status_code, content=payload)


@api_router.get("/chats", response_model=List[Chat])
async def list_chats(session_id: str):
    require_database()
    cursor = db.chats.find({"session_id": session_id}, {"_id": 0}).sort("updated_at", -1)
    chats = await cursor.to_list(length=500)
    return chats


@api_router.post("/chats", response_model=Chat)
async def create_chat(payload: ChatCreate):
    require_database()
    chat = Chat(session_id=payload.session_id, title=payload.title or "New Chat")
    await db.chats.insert_one(chat.model_dump())
    return chat


@api_router.get("/chats/{chat_id}")
async def get_chat(chat_id: str):
    require_database()
    chat = await db.chats.find_one({"id": chat_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = await db.messages.find({"chat_id": chat_id}, {"_id": 0, "model_context": 0}).sort("created_at", 1).to_list(length=None)
    return {"chat": chat, "messages": messages}


@api_router.patch("/chats/{chat_id}", response_model=Chat)
async def rename_chat(chat_id: str, payload: ChatUpdate):
    require_database()
    now = datetime.now(timezone.utc).isoformat()
    res = await db.chats.find_one_and_update(
        {"id": chat_id},
        {"$set": {"title": payload.title, "updated_at": now}},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise HTTPException(status_code=404, detail="Chat not found")
    return res


@api_router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    require_database()
    chat = await db.chats.find_one({"id": chat_id})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if gridfs is not None:
        async for message in db.messages.find({"chat_id": chat_id}, {"attachments.file_id": 1}):
            for attachment in message.get("attachments", []):
                file_id = attachment.get("file_id")
                if ObjectId.is_valid(file_id):
                    try:
                        await gridfs.delete(ObjectId(file_id))
                    except Exception:
                        logger.exception("Could not delete stored attachment %s", file_id)
    await db.messages.delete_many({"chat_id": chat_id})
    await db.chats.delete_one({"id": chat_id})
    return {"success": True}


async def get_latest_session_chat(user_id: str):
    require_database()
    chats = await db.chats.find({"session_id": user_id}, {"_id": 0}).sort(
        "updated_at", -1
    ).to_list(length=1)
    if chats:
        return chats[0]

    chat = Chat(session_id=user_id)
    await db.chats.insert_one(chat.model_dump())
    return chat.model_dump()


@api_router.get("/history")
async def get_session_history(userId: str):
    chats = await db.chats.find({"session_id": userId}, {"_id": 0}).sort(
        "updated_at", -1
    ).to_list(length=1)
    if not chats:
        return {"history": []}

    history = await db.messages.find(
        {"chat_id": chats[0]["id"]}, {"_id": 0, "role": 1, "content": 1}
    ).sort("created_at", 1).to_list(length=1000)
    return {"history": history}


@api_router.get("/files/{file_id}")
async def download_attachment(file_id: str, chat_id: str):
    require_database()
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=404, detail="Attachment not found")
    reference = await db.messages.find_one({"chat_id": chat_id, "attachments.file_id": file_id}, {"_id": 0, "model_context": 0})
    if not reference or gridfs is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    attachment = next((item for item in reference.get("attachments", []) if item.get("file_id") == file_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        stream = await gridfs.open_download_stream(ObjectId(file_id))
        data = await stream.read()
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Attachment data is unavailable") from exc
    filename = re.sub(r'[\\r\\n"]', "_", attachment.get("filename", "attachment"))
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(data), media_type=attachment.get("content_type", "application/octet-stream"), headers=headers)


async def prepare_upload(upload: UploadFile) -> tuple[ProcessedUpload, bytes]:
    data = await upload.read(MAX_UPLOAD_SIZE + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'Attachment'} is empty.")
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"Each attachment must be {MAX_UPLOAD_SIZE // (1024 * 1024)} MB or smaller.")
    try:
        processed = await asyncio.to_thread(process_upload, upload.filename or "attachment", upload.content_type or "", data)
        if processed.audio_payload:
            try:
                transcript, transcript_metadata = await asyncio.to_thread(transcribe_audio, processed.audio_payload)
                processed.metadata.update(transcript_metadata)
                processed.metadata["transcription_available"] = bool(transcript.strip())
                if transcript.strip():
                    processed.extracted_text = f"{processed.extracted_text}\nTranscript:\n{transcript}"
            except FileProcessingError as exc:
                # Keep a valid audio attachment usable even when the optional local
                # transcription model cannot be downloaded or loaded.
                processed.metadata["transcription_available"] = False
                processed.metadata["transcription_error"] = "Local speech transcription is unavailable; the audio is attached without a transcript."
                processed.extracted_text += "\nTranscript unavailable: local speech transcription failed."
                logger.warning("Could not transcribe audio attachment %s: %s", upload.filename, exc)
        return processed, data
    except FileProcessingError as exc:
        raise HTTPException(status_code=422, detail=f"Could not read {upload.filename}: {exc}") from exc


async def store_uploads(uploads: list[tuple[ProcessedUpload, bytes]]) -> list[dict]:
    if not uploads:
        return []
    require_database()
    if gridfs is None:
        raise HTTPException(status_code=503, detail="File storage is unavailable. Check the MongoDB connection.")
    stored = []
    try:
        for item, raw in uploads:
            file_id = ObjectId()
            await gridfs.upload_from_stream_with_id(
                file_id,
                item.filename,
                io.BytesIO(raw),
                metadata={"content_type": item.content_type, "chat_category": item.category, "sha256": item.sha256},
            )
            stored.append({
                "file_id": str(file_id),
                "filename": item.filename,
                "content_type": item.content_type,
                "size": item.size,
                "sha256": item.sha256,
                "category": item.category,
                "metadata": item.metadata,
            })
    except Exception:
        for attachment in stored:
            try:
                await gridfs.delete(ObjectId(attachment["file_id"]))
            except Exception:
                logger.exception("Could not clean up an incomplete attachment upload")
        raise
    return stored


@api_router.post("/chat")
async def chat_with_session(payload: SimpleChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    chat = await get_latest_session_chat(payload.user_id)
    response = await send_message(
        chat_id=chat["id"],
        content=payload.message,
        files=[],
    )
    return {"response": response.assistant_message.content}


@api_router.post("/chats/{chat_id}/messages", response_model=SendMessageResponse)
async def send_message(
    chat_id: str,
    content: str = Form(""),
    file: Optional[UploadFile] = File(None),
    files: List[UploadFile] = File(default=[]),
):
    require_database()
    chat_doc = await db.chats.find_one({"id": chat_id}, {"_id": 0})
    if not chat_doc:
        raise HTTPException(status_code=404, detail="Chat not found")

    uploads = list(files)
    if file is not None:
        uploads.insert(0, file)
    if len(uploads) > MAX_FILES_PER_MESSAGE:
        raise HTTPException(status_code=413, detail=f"You can attach up to {MAX_FILES_PER_MESSAGE} files per message.")

    if not content.strip() and not uploads:
        raise HTTPException(status_code=400, detail="Message content or file is required")

    if OLLAMA_PROVIDER != "cloud":
        raise HTTPException(status_code=503, detail="This backend is configured for Ollama Cloud only. Set OLLAMA_PROVIDER=cloud.")
    if not OLLAMA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Ollama Cloud is not configured. Add OLLAMA_API_KEY to Backend/.env and restart the backend.",
        )
    if not OLLAMA_BASE_URL.startswith("https://"):
        raise HTTPException(status_code=503, detail="Ollama Cloud requires an HTTPS OLLAMA_BASE_URL, normally https://ollama.com.")
    if not OLLAMA_MODEL:
        raise HTTPException(status_code=503, detail="Set OLLAMA_MODEL to an available Ollama Cloud model in Backend/.env.")

    processed_uploads = []
    for upload in uploads:
        processed_uploads.append(await prepare_upload(upload))

    extracted_parts = []
    image_payloads: list[bytes] = []
    for processed, _ in processed_uploads:
        extracted_parts.append(
            f"[Attachment: {processed.filename}; type={processed.category}; "
            f"metadata={json.dumps(processed.metadata, ensure_ascii=False)}]\n{processed.extracted_text}"
        )
        image_payloads.extend(processed.model_images)
    model_context = content.strip()
    if extracted_parts:
        model_context = "\n\n".join(part for part in [model_context, *extracted_parts] if part)
    # Keep prompt growth bounded even when several large documents are attached.
    model_context = model_context[:100_000]

    # Prepare the user message, but persist it only after generation succeeds.
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=content,
    )

    # Retrieve relevant context from previous messages.
    collection = get_chat_collection(chat_id)

    results = collection.query(
        query_embeddings=[embed_text(model_context)],
        n_results=5
    )

    rag_context = ""
    if results and results.get("documents"):
        rag_context = "\n".join(results["documents"][0])

    # Keep LangChain for prompt templates and message/history handling.
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\nContext:\n{context}"),
        MessagesPlaceholder(variable_name="history"),
    ])

    history = await build_history_messages(chat_id)
    history.append(HumanMessage(content=model_context))
    prompt_messages = prompt.format_messages(context=rag_context, history=history)
    ollama_messages = to_ollama_messages(prompt_messages, image_payloads)

    logger.info("Calling Ollama Cloud model %s for chat_id %s", OLLAMA_MODEL, chat_id)
    try:
        if ollama_client is None:
            raise RuntimeError("Ollama client was not initialized. Start the app with its FastAPI lifespan.")
        ai_response = await ollama_client.chat(
            model=OLLAMA_MODEL,
            messages=ollama_messages,
            stream=False,
            options={"temperature": 0.7, "num_predict": 1024},
        )
        assistant_text = ai_response.message.content
        if not assistant_text:
            raise RuntimeError("Ollama Cloud returned an empty response.")
    except Exception as exc:
        logger.exception("Ollama Cloud request failed for chat_id %s", chat_id)
        status_code, failure_detail = ollama_failure(exc)
        raise HTTPException(
            status_code=status_code,
            detail=f"{failure_detail} (model: {OLLAMA_MODEL})",
        ) from exc

    # Persist both messages only after a successful model response.
    attachments = await store_uploads(processed_uploads)
    user_msg.attachments = attachments
    user_doc = user_msg.model_dump()
    user_doc["model_context"] = model_context
    await db.messages.insert_one(user_doc)
    await store_in_chroma(chat_id, user_msg.id, "user", model_context)

    assistant_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=assistant_text
    )
    await db.messages.insert_one(assistant_msg.model_dump())

    # Store the assistant message for future context retrieval.
    await store_in_chroma(
        chat_id,
        assistant_msg.id,
        "assistant",
        assistant_text
    )

    # Update the chat title and timestamp.
    now = datetime.now(timezone.utc).isoformat()
    update_doc = {"updated_at": now}

    if chat_doc.get("title", "New Chat") in {"New Chat", "New conversation"}:
        update_doc["title"] = generate_title_from_message(content or uploads[0].filename or "Attachment")

    await db.chats.update_one({"id": chat_id}, {"$set": update_doc})

    updated_chat = await db.chats.find_one({"id": chat_id}, {"_id": 0})

    return SendMessageResponse(
        user_message=user_msg,
        assistant_message=assistant_msg,
        chat=Chat(**updated_chat),
    )


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
