import { useState } from "react";

export default function MessageInput({ onSend, loading }) {
  const [input, setInput] = useState("");
  const [file, setFile] = useState(null);

  const handleSend = async () => {
    if (!input.trim() && !file) return;
    await onSend(input, file);
    setInput("");
    setFile(null);
  };

  return (
    <div className="mt-3 border-t border-slate-800 pt-3 flex flex-col gap-3 md:flex-row md:items-center">
      <div className="flex-1 min-w-0">
        <textarea
          rows={2}
          className="w-full resize-none rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white outline-none transition focus:border-blue-500"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Type your message..."
        />
      </div>

      <div className="flex flex-col gap-2 md:flex-row md:items-center">
        <label className="inline-flex cursor-pointer items-center rounded-full border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-800">
          Attach
          <input
            type="file"
            onChange={(e) => setFile(e.target.files[0])}
            className="hidden"
          />
        </label>
        <button
          onClick={handleSend}
          disabled={loading || (!input.trim() && !file)}
          className="rounded-full bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-50 hover:bg-blue-500"
        >
          Send
        </button>
      </div>

      {file && (
        <div className="text-xs text-slate-400">
          Attached: {file.name}
        </div>
      )}
    </div>
  );
}