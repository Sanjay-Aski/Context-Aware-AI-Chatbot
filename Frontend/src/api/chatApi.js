const API = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  let data;
  try {
    data = await response.json();
  } catch {
    data = { detail: `The server returned HTTP ${response.status}.` };
  }

  if (!response.ok) {
    const error = new Error(data.detail || `Request failed with HTTP ${response.status}.`);
    error.response = { status: response.status, data };
    throw error;
  }
  return { data };
}

export const getChats = (sessionId) =>
  request(`/api/chats?session_id=${encodeURIComponent(sessionId)}`);

export const createChat = (data) =>
  request("/api/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const getChatById = (chatId) =>
  request(`/api/chats/${encodeURIComponent(chatId)}`);

export const removeChat = (chatId) =>
  request(`/api/chats/${encodeURIComponent(chatId)}`, { method: "DELETE" });

export async function getAttachmentBlob(chatId, fileId) {
  const response = await fetch(`${API}/api/files/${encodeURIComponent(fileId)}?chat_id=${encodeURIComponent(chatId)}`);
  if (!response.ok) {
    let detail = `Attachment download failed with HTTP ${response.status}.`;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // Keep the status-based error if the server did not return JSON.
    }
    throw new Error(detail);
  }
  return response.blob();
}

export const sendMessage = (chatId, formData) =>
  request(`/api/chats/${encodeURIComponent(chatId)}/messages`, {
    method: "POST",
    body: formData,
  });
