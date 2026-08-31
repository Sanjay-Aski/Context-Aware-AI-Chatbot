import { useState } from "react";
import { useChatContext } from "./components/useChatContext";
import Sidebar from "./components/Sidebar";
import MessageList from "./components/MessageList";
import MessageInput from "./components/MessageInput";
import "./App.css";
import "./index.css";

function MenuIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>;
}

function SparkIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Z" /></svg>;
}

export default function App() {
  const {
    chats,
    activeChat,
    messages,
    loading,
    error,
    exportingChatId,
    clearError,
    handleCreateChat,
    handleOpenChat,
    handleDeleteChat,
    handleExportChat,
    handleSendMessage,
  } = useChatContext();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const activeChatTitle = chats.find((chat) => chat.id === activeChat)?.title || "New conversation";

  return (
    <main className="app-shell">
      <Sidebar
        chats={chats}
        activeChat={activeChat}
        onNewChat={handleCreateChat}
        onOpenChat={handleOpenChat}
        onDeleteChat={handleDeleteChat}
        onExportChat={handleExportChat}
        exportingChatId={exportingChatId}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      {sidebarOpen && <button className="sidebar-scrim" aria-label="Close conversation menu" onClick={() => setSidebarOpen(false)} />}

      <section className="chat-panel">
        <header className="topbar">
          <button className="icon-button menu-button" aria-label="Open conversation menu" onClick={() => setSidebarOpen(true)}>
            <MenuIcon />
          </button>
          <div className="topbar-title">
            <span className="eyebrow">OLLAMA CLOUD</span>
            <h1>{activeChatTitle}</h1>
          </div>
          <div className={`connection-status ${loading ? "connection-status-busy" : ""}`}>
            <span />{loading ? "Thinking" : "Ready to help"}
          </div>
        </header>

        <div className="conversation-area" aria-live="polite">
          {messages.length === 0 ? (
            <div className="welcome-state">
              <div className="welcome-icon"><SparkIcon /></div>
              <span className="eyebrow">YOUR AI WORKSPACE</span>
              <h2>What can I help<br className="desktop-break" /> you with today?</h2>
              <p>Ask a question, explore an idea, or get help turning a thought into a plan.</p>
              {!activeChat && <button className="primary-button welcome-button" onClick={handleCreateChat}>Start a conversation <span aria-hidden="true">{"\u2192"}</span></button>}
              <div className="suggestion-grid" aria-label="Things you can ask">
                <div className="suggestion-card"><span>{"\u2733"}</span><strong>Explore an idea</strong><small>Think through a topic or question</small></div>
                <div className="suggestion-card"><span>{"\u2318"}</span><strong>Get something done</strong><small>Draft, plan, explain, and more</small></div>
              </div>
            </div>
          ) : <MessageList messages={messages} loading={loading} />}
        </div>

        <footer className="composer-area">
          {error && <div className="request-error" role="alert"><span>{error}</span><button onClick={clearError} aria-label="Dismiss error">{"\u00d7"}</button></div>}
          <MessageInput onSend={handleSendMessage} loading={loading} disabled={!activeChat} />
          <p className="disclaimer">AI can make mistakes. Check important information.</p>
        </footer>
      </section>
    </main>
  );
}
