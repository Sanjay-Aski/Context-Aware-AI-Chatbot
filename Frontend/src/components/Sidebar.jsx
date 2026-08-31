import { useState } from "react";

function BrandMark() {
  return <div className="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></svg></div>;
}

export default function Sidebar({ chats, activeChat, onNewChat, onOpenChat, onDeleteChat, onExportChat, exportingChatId, isOpen, onClose }) {
  const [openMenuId, setOpenMenuId] = useState(null);

  return (
    <aside className={`sidebar ${isOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-brand">
        <BrandMark />
        <div><strong>GPT Chat</strong><span>Your AI workspace</span></div>
        <button className="icon-button close-sidebar" aria-label="Close conversation menu" onClick={onClose}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </div>

      <button className="new-chat-button" onClick={() => { onNewChat(); onClose(); }}>
        <span className="plus-icon">+</span> New conversation
      </button>

      <div className="history-heading"><span>RECENT</span><span>{chats.length}</span></div>
      <nav className="chat-history" aria-label="Recent conversations">
        {chats.length === 0 ? (
          <div className="empty-history"><span className="empty-history-icon">{"\u2197"}</span><p>Your conversations will show up here.</p></div>
        ) : chats.map((chat) => (
          <div className={`history-item-wrap ${activeChat === chat.id ? "history-item-wrap-active" : ""}`} key={chat.id}>
            <button onClick={() => { setOpenMenuId(null); onOpenChat(chat.id); onClose(); }} className={`history-item ${activeChat === chat.id ? "history-item-active" : ""}`} title={chat.title}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.7-3.4A7.5 7.5 0 1 1 20 11.5Z" /></svg>
              <span>{chat.title || "New conversation"}</span>
            </button>
            <button className="chat-more-button" type="button" aria-label={`More options for ${chat.title || "conversation"}`} aria-expanded={openMenuId === chat.id} onClick={() => setOpenMenuId((current) => current === chat.id ? null : chat.id)}>
              <span aria-hidden="true">···</span>
            </button>
            {openMenuId === chat.id && (
              <div className="chat-options-menu" role="menu">
                <button type="button" role="menuitem" disabled={exportingChatId === chat.id} onClick={() => { setOpenMenuId(null); onExportChat(chat.id); }}>
                  <span aria-hidden="true">↓</span>{exportingChatId === chat.id ? "Preparing JSON…" : "Export as JSON"}
                </button>
                <button type="button" role="menuitem" className="chat-delete-option" onClick={() => {
                  setOpenMenuId(null);
                  if (window.confirm(`Delete “${chat.title || "New conversation"}”? This also removes its uploaded files.`)) onDeleteChat(chat.id);
                }}>
                  <span aria-hidden="true">⌫</span>Delete conversation
                </button>
              </div>
            )}
          </div>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="profile-avatar">Y</div>
        <div className="profile-copy"><strong>Your account</strong><span>Personal workspace</span></div>
        <span className="profile-menu" aria-hidden="true">{"\u2022\u2022\u2022"}</span>
      </div>
    </aside>
  );
}
