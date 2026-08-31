import { useEffect, useState } from "react";
import { getChats, createChat, getChatById, sendMessage } from "../api/chatapi";

export default function useChats(sessionId) {
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadChats() {
      try {
        const res = await getChats(sessionId);
        if (!cancelled) setChats(res.data || []);
      } catch {
        if (!cancelled) setChats([]);
      }
    }
    void loadChats();
    return () => { cancelled = true; };
  }, [sessionId]);

  const handleCreateChat = async () => {
    const res = await createChat({ session_id: sessionId, title: "New conversation" });
    setChats((previous) => [res.data, ...previous]);
    setActiveChat(res.data.id);
    setMessages([]);
  };

  const handleOpenChat = async (chatId) => {
    setActiveChat(chatId);
    const res = await getChatById(chatId);
    setMessages(res.data.messages || []);
  };

  const handleSendMessage = async (input, file) => {
    if (!activeChat || (!input.trim() && !file)) return false;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("content", input);
      if (file) formData.append("file", file);
      const res = await sendMessage(activeChat, formData);
      setMessages((previous) => [...previous, res.data.user_message, res.data.assistant_message]);
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  };

  return { chats, activeChat, messages, loading, setMessages, handleCreateChat, handleOpenChat, handleSendMessage };
}
