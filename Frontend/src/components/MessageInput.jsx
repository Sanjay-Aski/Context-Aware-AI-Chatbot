import { useRef, useState } from "react";

export default function MessageInput({ onSend, loading, disabled }) {
  const [input, setInput] = useState("");
  const [files, setFiles] = useState([]);
  const fileInput = useRef(null);

  const handleSend = async () => {
    if (loading || disabled || (!input.trim() && files.length === 0)) return;
    const sent = await onSend(input.trim(), files);
    if (sent === false) return;
    setInput("");
    setFiles([]);
    if (fileInput.current) fileInput.current.value = "";
  };

  const addFiles = (selected) => {
    setFiles((current) => {
      const next = [...current];
      for (const item of selected) {
        if (!next.some((existing) => existing.name === item.name && existing.size === item.size && existing.lastModified === item.lastModified)) next.push(item);
      }
      return next.slice(0, 8);
    });
    if (fileInput.current) fileInput.current.value = "";
  };

  const removeFile = (index) => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index));

  return (
    <div className={`composer ${disabled ? "composer-disabled" : ""}`}>
      {files.length > 0 && <div className="composer-attachments" aria-label="Selected attachments">{files.map((file, index) => <div className="attachment-chip" key={`${file.name}-${file.size}-${file.lastModified}`}><span className="attachment-file-icon" aria-hidden="true">{file.type.startsWith("image/") ? "▧" : "↗"}</span><span title={file.name}>{file.name}<small>{formatSize(file.size)}</small></span><button onClick={() => removeFile(index)} aria-label={`Remove ${file.name}`}>×</button></div>)}</div>}
      <textarea
        rows={2}
        value={input}
        disabled={disabled || loading}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); handleSend(); } }}
        placeholder={disabled ? "Start a conversation to begin writing" : "Message your assistant..."}
        aria-label="Message"
      />
      <div className="composer-toolbar">
        <div className="composer-hint"><kbd>Enter</kbd> to send <span>·</span> <kbd>Shift + Enter</kbd> for a new line</div>
        <div className="composer-actions">
          <button className="attach-button" onClick={() => fileInput.current?.click()} disabled={disabled || loading || files.length >= 8} aria-label="Attach files" title="Attach files">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8.5 12.5 6.6-6.6a3.2 3.2 0 0 1 4.5 4.5l-8.8 8.8a5 5 0 0 1-7.1-7.1l8.5-8.5" /></svg>
          </button>
          <input ref={fileInput} type="file" multiple className="visually-hidden" onChange={(event) => addFiles(Array.from(event.target.files || []))} />
          <button className="send-button" onClick={handleSend} disabled={disabled || loading || (!input.trim() && files.length === 0)} aria-label="Send message">
            {loading ? <span className="send-spinner" /> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
