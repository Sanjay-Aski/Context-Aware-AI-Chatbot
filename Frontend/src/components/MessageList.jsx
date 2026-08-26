export default function MessageList({ messages, loading }) {
  return (
    <div className="space-y-4">
      {messages.map((m, i) => (
        <div
          key={i}
          className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[80%] space-y-2 rounded-[24px] px-4 py-3 text-sm leading-relaxed shadow-sm ${
              m.role === "user"
                ? "self-end bg-blue-600 text-white rounded-br-[18px] rounded-tl-[18px]"
                : "self-start bg-slate-800 text-slate-100 rounded-bl-[18px] rounded-tr-[18px]"
            }`}
          >
            <div className="text-[10px] uppercase tracking-[0.24em] text-slate-400">
              {m.role === "user" ? "You" : "Assistant"}
            </div>
            <div className="whitespace-pre-wrap break-words">{m.content}</div>
          </div>
        </div>
      ))}

      {loading && (
        <div className="rounded-[24px] bg-slate-900 px-4 py-3 text-sm text-slate-300 shadow-sm">
          AI is thinking...
        </div>
      )}
    </div>
  );
}