import axios from "axios";

const API = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

export const getChats = (sessionId) =>
  axios.get(`${API}/api/chats?session_id=${sessionId}`);

export const createChat = (data) =>
  axios.post(`${API}/api/chats`, data);

export const getChatById = (chatId) =>
  axios.get(`${API}/api/chats/${chatId}`);

export const sendMessage = (chatId, formData) =>
  axios.post(`${API}/api/chats/${chatId}/messages`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });