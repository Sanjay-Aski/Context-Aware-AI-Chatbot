from fastapi import FastAPI, APIRouter, HTTPException, Form, UploadFile, File
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Ollama config
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")

# System prompt
SYSTEM_PROMPT = """You are an intelligent, context-aware AI assistant integrated into a full-stack application.
Your responses must be helpful, accurate, and conversational while maintaining memory of previous interactions in the current session.

Core Behavior:
- Maintain context across messages using previous chat history.
- Respond in a natural, concise, and helpful manner.
- If a question depends on past messages, refer to that context before answering.
- Do not hallucinate facts outside the conversation or stored context.

Capabilities:
- Answer general queries and technical questions.
- Assist in coding, debugging, and explanation tasks.
- Maintain multi-turn conversations with continuity.
- Adapt tone based on user interaction style (formal/informal).

Response Style:
- Keep responses clear and structured.
- Avoid unnecessary verbosity.
- Use bullet points, numbered lists, or fenced code blocks only when helpful.
- For code, always use proper markdown code fences with language hints."""

app = FastAPI()
api_router = APIRouter(prefix="/api")


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
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SendMessageResponse(BaseModel):
    user_message: Message
    assistant_message: Message
    chat: Chat


# -------- Helpers --------
def get_llm():
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.7,
    )


async def build_history_messages(chat_id: str, limit: int = 30):
    cursor = db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1)
    docs = await cursor.to_list(length=limit * 2)
    docs = docs[-limit:]
    history = []
    for d in docs:
        if d["role"] == "user":
            history.append(HumanMessage(content=d["content"]))
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


# -------- Routes --------
@api_router.get("/")
async def root():
    return {"message": "Chatbot API running", "model": OLLAMA_MODEL}


@api_router.get("/health")
async def health():
    return {"status": "ok", "ollama_base_url": OLLAMA_BASE_URL, "model": OLLAMA_MODEL}


@api_router.get("/chats", response_model=List[Chat])
async def list_chats(session_id: str):
    cursor = db.chats.find({"session_id": session_id}, {"_id": 0}).sort("updated_at", -1)
    chats = await cursor.to_list(length=500)
    return chats


@api_router.post("/chats", response_model=Chat)
async def create_chat(payload: ChatCreate):
    chat = Chat(session_id=payload.session_id, title=payload.title or "New Chat")
    await db.chats.insert_one(chat.model_dump())
    return chat


@api_router.get("/chats/{chat_id}")
async def get_chat(chat_id: str):
    chat = await db.chats.find_one({"id": chat_id}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = await db.messages.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", 1).to_list(length=1000)
    return {"chat": chat, "messages": messages}


@api_router.patch("/chats/{chat_id}", response_model=Chat)
async def rename_chat(chat_id: str, payload: ChatUpdate):
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
    chat = await db.chats.find_one({"id": chat_id})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    await db.messages.delete_many({"chat_id": chat_id})
    await db.chats.delete_one({"id": chat_id})
    return {"success": True}


@api_router.post("/chats/{chat_id}/messages", response_model=SendMessageResponse)
async def send_message(
    chat_id: str,
    content: str = Form(...),
    file: Optional[UploadFile] = File(None),
):
    chat_doc = await db.chats.find_one({"id": chat_id}, {"_id": 0})
    if not chat_doc:
        raise HTTPException(status_code=404, detail="Chat not found")

    if not content.strip() and file is None:
        raise HTTPException(status_code=400, detail="Message content or file is required")

    if file is not None:
        try:
            raw_bytes = await file.read()
            text = raw_bytes.decode("utf-8", errors="replace").strip()
            if text:
                content += f"\n\n[Attached file: {file.filename}]\n{text}"
            else:
                content += f"\n\n[Attached file: {file.filename}]"
        except Exception as exc:
            logger.warning("Unable to read uploaded file %s: %s", file.filename, exc)

    # 1. Save user message (MongoDB)
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=content
    )
    await db.messages.insert_one(user_msg.model_dump())

    # 2. Save user message to ChromaDB
    await store_in_chroma(
        chat_id,
        user_msg.id,
        "user",
        content
    )

    # 3. Retrieve relevant context from ChromaDB (RAG)
    collection = get_chat_collection(chat_id)

    results = collection.query(
        query_embeddings=[embed_text(content)],
        n_results=5
    )

    rag_context = ""
    if results and results.get("documents"):
        rag_context = "\n".join(results["documents"][0])

    # 4. Build LLM prompt with RAG context
    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\nContext:\n{context}"),
        MessagesPlaceholder(variable_name="history"),
    ])

    history = await build_history_messages(chat_id)

    chain = prompt | llm

    logger.info("Invoking LLM model %s for chat_id %s", OLLAMA_MODEL, chat_id)
    try:
        ai_response = await chain.ainvoke({
            "history": history,
            "context": rag_context
        })
    except Exception as exc:
        logger.exception("LLM invocation failed for chat_id %s", chat_id)
        raise HTTPException(status_code=500, detail="LLM invocation failed") from exc

    assistant_text = getattr(ai_response, "content", str(ai_response))

    # 5. Save assistant message (MongoDB)
    assistant_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=assistant_text
    )
    await db.messages.insert_one(assistant_msg.model_dump())

    # 6. Save assistant message to ChromaDB
    await store_in_chroma(
        chat_id,
        assistant_msg.id,
        "assistant",
        assistant_text
    )

    # 7. Update chat title
    now = datetime.now(timezone.utc).isoformat()
    update_doc = {"updated_at": now}

    if chat_doc.get("title", "New Chat") == "New Chat":
        update_doc["title"] = generate_title_from_message(content)

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
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
