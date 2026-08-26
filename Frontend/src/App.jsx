import { useChatContext } from "./components/ChatContext";
import Sidebar from "./components/Sidebar";
import MessageList from "./components/MessageList";
import MessageInput from "./components/MessageInput";
import "./App.css";
import "./index.css";

export default function App() {
  const {
    chats,
    activeChat,
    messages,
    loading,
    handleCreateChat,
    handleOpenChat,
    handleSendMessage,
  } = useChatContext();

  const activeChatTitle = chats.find((chat) => chat.id === activeChat)?.title || "New Conversation";

  return (
    <div className="h-screen flex bg-slate-950 text-white">
      <Sidebar
        chats={chats}
        activeChat={activeChat}
        onNewChat={handleCreateChat}
        onOpenChat={handleOpenChat}
      />

      <div className="flex flex-col flex-1">
        <div className="h-16 px-6 flex items-center justify-between border-b border-slate-800 bg-slate-900">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Live Chat</p>
            <h1 className="text-xl font-semibold text-white">{activeChatTitle}</h1>
          </div>
          <div className="text-sm text-slate-400">
            {activeChat ? "Connected" : "Create a chat to begin"}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6 bg-slate-950">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center gap-4 text-center text-slate-500">
              <p className="text-lg font-medium text-slate-200">Welcome to your AI assistant</p>
              <p className="max-w-xl text-sm text-slate-400">Start a new chat from the sidebar and ask anything. Your conversation will appear here instantly.</p>
            </div>
          ) : (
            <MessageList messages={messages} loading={loading} />
          )}
        </div>

        <div className="border-t border-slate-800 bg-slate-900 p-4">
          <MessageInput onSend={handleSendMessage} loading={loading} />
        </div>
      </div>
    </div>
  );
}