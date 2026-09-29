import { useState } from 'react';
import '../App.css';

async function readResponse(response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.detail || payload.message || `Request failed (${response.status})`);
    }
    return payload;
}

export default function Chat() {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [files, setFiles] = useState([]);
    const [busy, setBusy] = useState(false);

    async function handleSend() {
        const question = input.trim();
        if (busy || (!question && files.length === 0)) return;

        const selectedFiles = [...files];
        const messageId = crypto.randomUUID();
        setInput('');
        setFiles([]);
        setBusy(true);
        setMessages((previous) => [...previous, {
            id: messageId,
            text: question,
            files: selectedFiles.map((file) => file.name),
            answer: '',
            status: 'Working…',
        }]);

        try {
            const uploaded = [];
            for (const file of selectedFiles) {
                const body = new FormData();
                body.append('file', file);
                const result = await readResponse(await fetch('/api/upload', {
                    method: 'POST',
                    body,
                }));
                uploaded.push(`${result.filename} (${result.chunks_added} chunks indexed)`);
            }

            let answer = '';
            if (question) {
                const result = await readResponse(await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: question }),
                }));
                answer = result.answer;
            } else {
                answer = uploaded.length ? `Uploaded and indexed: ${uploaded.join(', ')}.` : '';
            }

            setMessages((previous) => previous.map((message) =>
                message.id === messageId ? { ...message, answer, status: '' } : message
            ));
        } catch (error) {
            setMessages((previous) => previous.map((message) =>
                message.id === messageId
                    ? { ...message, status: '', answer: `Error: ${error.message}` }
                    : message
            ));
        } finally {
            setBusy(false);
        }
    }

    function handleFileChange(event) {
        const selectedFiles = Array.from(event.target.files || []);
        setFiles((previous) => [...previous, ...selectedFiles]);
        event.target.value = '';
    }

    function handleRemoveFile(indexToRemove) {
        setFiles((previous) => previous.filter((_, index) => index !== indexToRemove));
    }

    return (
        <main>
            {messages.length === 0 ? (
                <div className="chat">
                    <h2>How can I help?</h2>
                    <p>Ask a question about your DevOps incident, logs, or runbooks.</p>
                </div>
            ) : (
                <div className="conversation" aria-live="polite">
                    {messages.map((message) => (
                        <div className="message-group" key={message.id}>
                            {message.text && <div className="message">{message.text}</div>}
                            {message.files.map((file, index) => (
                                <div className="message-file" key={`${file}-${index}`}>📄 {file}</div>
                            ))}
                            {(message.status || message.answer) && (
                                <div className="assistant-message">
                                    {message.status || message.answer}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            <div className="chat-input">
                {files.length > 0 && (
                    <div className="file-preview-list">
                        {files.map((file, index) => (
                            <div className="file-preview" key={`${file.name}-${file.size}-${index}`}>
                                <span>📄 {file.name}</span>
                                <button type="button" onClick={() => handleRemoveFile(index)} aria-label={`Remove ${file.name}`}>×</button>
                            </div>
                        ))}
                    </div>
                )}
                <div className="input-row">
                    <input type="file" accept=".pdf,application/pdf" id="pdf-upload" hidden multiple onChange={handleFileChange} />
                    <label htmlFor="pdf-upload" className="upload-button" title="Attach PDF files" aria-label="Attach PDF files">+</label>
                    <input
                        type="text"
                        placeholder="Ask about your incident..."
                        value={input}
                        disabled={busy}
                        onChange={(event) => setInput(event.target.value)}
                        onKeyDown={(event) => { if (event.key === 'Enter') handleSend(); }}
                    />
                    <button type="button" onClick={handleSend} disabled={busy}>
                        {busy ? 'Sending…' : 'Send'}
                    </button>
                </div>
            </div>
        </main>
    );
}
