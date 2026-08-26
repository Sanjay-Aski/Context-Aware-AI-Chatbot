export default function Sidebar({ chats, activeChat, onNewChat, onOpenChat }) {
  return (
    <div className="w-full max-w-[320px] shrink-0 bg-slate-950 border-r border-slate-800 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">GPT Chat</p>
          <h2 className="mt-1 text-lg font-semibold text-white">Conversations</h2>
        </div>
        <button
          onClick={onNewChat}
          className="rounded-full border border-blue-500 bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500"
        >
          + New
        </button>
      </div>

      <div className="mt-5 space-y-3">
        {chats.length === 0 && (
          <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-900 px-4 py-6 text-sm text-slate-400">
            No conversations yet.
          </div>
        )}

        {chats.map((c) => (
          <button
            key={c.id}
            onClick={() => onOpenChat(c.id)}
            className={`w-full rounded-3xl px-4 py-3 text-left text-sm transition ${
              activeChat === c.id
                ? "border border-blue-500 bg-blue-600 text-white"
                : "border border-transparent bg-slate-900 text-slate-200 hover:border-slate-700 hover:bg-slate-900"
            }`}
          >
            {c.title}
          </button>
        ))}
      </div>
    </div>
  );
}