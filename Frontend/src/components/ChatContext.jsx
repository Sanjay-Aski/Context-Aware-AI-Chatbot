import { useState, useEffect } from "react";
import { ChatContext } from "./ChatContextBase";
import {
  getChats,
  createChat,
  getChatById,
  getAttachmentBlob,
  removeChat,
  sendMessage,
} from "../api/chatApi";

async function blobToBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const chunks = [];
  const chunkSize = 24_576;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    chunks.push(btoa(String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))));
  }
  return chunks.join("");
}

function downloadJson(data, title) {
  const safeTitle = (title || "conversation").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-|-$/g, "") || "conversation";
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeTitle}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ChatProvider({ children }) {
  const [sessionId] = useState(() => {
    const stored = localStorage.getItem("chatbot-user-id");
    if (stored) return stored;
    localStorage.setItem("chatbot-user-id", "default");
    return "default";
  });

  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportingChatId, setExportingChatId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function loadChats() {
      try {
        const res = await getChats(sessionId);
        if (cancelled) return;
        const loadedChats = res.data || [];
        setChats(loadedChats);
        if (loadedChats.length > 0) {
          const latestChat = loadedChats[0];
          const chatRes = await getChatById(latestChat.id);
          if (cancelled) return;
          setActiveChat(latestChat.id);
          setMessages(chatRes.data.messages || []);
        }
      } catch (requestError) {
        if (cancelled) return;
        const detail = requestError.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Your conversations could not be loaded. Check that the backend is running.");
      }
    }
    void loadChats();
    return () => { cancelled = true; };
  }, [sessionId]);

  const handleCreateChat = async () => {
    setError("");
    try {
      const res = await createChat({
        session_id: sessionId,
        title: "New conversation",
      });
      setChats((prev) => [res.data, ...prev]);
      setActiveChat(res.data.id);
      setMessages([]);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "A new conversation could not be created.");
    }
  };

  const handleOpenChat = async (chatId) => {
    setActiveChat(chatId);
    setError("");
    try {
      const res = await getChatById(chatId);
      setMessages(res.data.messages || []);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That conversation could not be loaded.");
    }
  };

  const handleDeleteChat = async (chatId) => {
    setError("");
    try {
      await removeChat(chatId);
      const remainingChats = chats.filter((chat) => chat.id !== chatId);
      setChats(remainingChats);
      if (activeChat === chatId) {
        setMessages([]);
        setActiveChat(null);
        if (remainingChats.length > 0) await handleOpenChat(remainingChats[0].id);
      }
    } catch (requestError) {
      const detail = requestError.response?.data?.detail || requestError.message;
      setError(typeof detail === "string" ? detail : "That conversation could not be deleted.");
    }
  };

  const handleExportChat = async (chatId) => {
    setExportingChatId(chatId);
    setError("");
    try {
      const response = await getChatById(chatId);
      const { chat, messages: history } = response.data;
      const exportedMessages = await Promise.all((history || []).map(async (message) => ({
        ...message,
        attachments: await Promise.all((message.attachments || []).map(async (attachment) => ({
          ...attachment,
          content_encoding: "base64",
          data_base64: await blobToBase64(await getAttachmentBlob(chatId, attachment.file_id)),
        }))),
      })));
      downloadJson({
        format: "chatmodel.conversation",
        version: 1,
        exported_at: new Date().toISOString(),
        chat,
        messages: exportedMessages,
      }, chat.title);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail || requestError.message;
      setError(typeof detail === "string" ? detail : "That conversation could not be exported.");
    } finally {
      setExportingChatId(null);
    }
  };

  const handleSendMessage = async (input, files = []) => {
    if (!activeChat) return;

    setLoading(true);
    setError("");

    const formData = new FormData();
    formData.append("content", input);
    for (const file of files) formData.append("files", file);

    try {
      const res = await sendMessage(activeChat, formData);
      setMessages((prev) => [
        ...prev,
        res.data.user_message,
        res.data.assistant_message,
      ]);
      return true;
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Your message could not be sent. Check that the backend is running, then try again.");
      return false;
    } finally {
      setLoading(false);
    }
  };

  return (
    <ChatContext.Provider
      value={{
        chats,
        activeChat,
        messages,
        loading,
        error,
        exportingChatId,
        clearError: () => setError(""),
        handleCreateChat,
        handleOpenChat,
        handleDeleteChat,
        handleExportChat,
        handleSendMessage,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}
