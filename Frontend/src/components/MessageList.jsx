import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function SparkMark() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Z" /></svg>;
}

function formatSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function AttachmentCards({ attachments = [], chatId }) {
  if (!attachments.length) return null;
  return (
    <div className="message-attachments">
      {attachments.map((attachment) => {
        const href = `/api/files/${encodeURIComponent(attachment.file_id)}?chat_id=${encodeURIComponent(chatId || "")}`;
        const isImage = attachment.category === "image";
        return (
          <a className="message-attachment-card" href={href} key={attachment.file_id} target="_blank" rel="noreferrer" download={attachment.filename}>
            {isImage ? <img src={href} alt="" className="attachment-thumbnail" /> : <span className={`attachment-kind attachment-kind-${attachment.category || "file"}`}>{(attachment.category || "file").slice(0, 3).toUpperCase()}</span>}
            <span className="attachment-card-copy"><strong title={attachment.filename}>{attachment.filename}</strong><small>{formatSize(attachment.size)} · {(attachment.category || "file").toUpperCase()}</small></span>
            <span className="attachment-download" aria-hidden="true">↓</span>
          </a>
        );
      })}
    </div>
  );
}

export default function MessageList({ messages, loading }) {
  return (
    <div className="message-list">
      {messages.map((message, index) => {
        const isUser = message.role === "user";
        return (
          <article key={message.id || `${message.role}-${index}`} className={`message-row ${isUser ? "message-row-user" : "message-row-assistant"}`}>
            {!isUser && <div className="assistant-avatar"><SparkMark /></div>}
            <div className="message-content">
              <div className="message-author">{isUser ? "You" : "Assistant"}</div>
              <div className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}>
                {message.content && (isUser
                  ? <div>{message.content}</div>
                  : <div className="message-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: ({ children }) => <div className="markdown-table-wrap"><table>{children}</table></div>, a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a> }}>{message.content}</ReactMarkdown></div>)}
                <AttachmentCards attachments={message.attachments} chatId={message.chat_id} />
              </div>
            </div>
          </article>
        );
      })}
      {loading && (
        <article className="message-row message-row-assistant" aria-live="polite">
          <div className="assistant-avatar"><SparkMark /></div>
          <div className="message-content"><div className="message-author">Assistant</div><div className="thinking-bubble"><span /><span /><span /><em>Thinking</em></div></div>
        </article>
      )}
    </div>
  );
}
