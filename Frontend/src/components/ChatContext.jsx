import { createContext, useContext, useState, useEffect } from "react";
import {
  getChats,
  createChat,
  getChatById,
  sendMessage,
} from "../api/chatApi";

const ChatContext = createContext();

export function ChatProvider({ children }) {
  const [sessionId] = useState(() => {
    const stored = localStorage.getItem("sessionId");
    if (stored) return stored;
    const newId = `user-${Date.now()}`;
    localStorage.setItem("sessionId", newId);
    return newId;
  });

  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadChats();
  }, []);

  const loadChats = async () => {
    const res = await getChats(sessionId);
    setChats(res.data);
  };

  const handleCreateChat = async () => {
    const res = await createChat({
      session_id: sessionId,
      title: "New Chat",
    });

    setChats((prev) => [res.data, ...prev]);
    setActiveChat(res.data.id);
    setMessages([]);
  };

  const handleOpenChat = async (chatId) => {
    setActiveChat(chatId);
    const res = await getChatById(chatId);
    setMessages(res.data.messages || []);
  };

  const handleSendMessage = async (input, file) => {
    if (!activeChat) return;

    setLoading(true);

    const formData = new FormData();
    formData.append("content", input);
    if (file) formData.append("file", file);

    const res = await sendMessage(activeChat, formData);

    setMessages((prev) => [
      ...prev,
      res.data.user_message,
      res.data.assistant_message,
    ]);

    setLoading(false);
  };

  return (
    <ChatContext.Provider
      value={{
        chats,
        activeChat,
        messages,
        loading,
        handleCreateChat,
        handleOpenChat,
        handleSendMessage,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export const useChatContext = () => useContext(ChatContext);