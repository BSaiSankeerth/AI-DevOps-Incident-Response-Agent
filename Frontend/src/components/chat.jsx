import { useEffect, useRef, useState } from 'react';
import '../App.css';
import { api } from '../../api';

// Turn stored rows [{role, content}, ...] into question/answer groups.
function toGroups(rows) {
    const groups = [];
    for (const row of rows) {
        if (row.role === 'user') {
            groups.push({ id: `m${row.id}`, text: row.content, files: [], answer: '', status: '', tools: [] });
        } else if (groups.length) {
            const last = groups[groups.length - 1];
            last.answer = row.content;
            last.tools = row.tools_used || [];
        }
    }
    return groups;
}

function FileChip({ file, icon, onDelete }) {
    return (
        <span className="file-chip">
            {icon} {file.filename}
            <button type="button" onClick={() => onDelete(file.id)} aria-label={`Delete ${file.filename}`}>×</button>
        </span>
    );
}

export default function Chat({ conversationId, onChanged }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [files, setFiles] = useState([]);
    const [busy, setBusy] = useState(false);
    const [loadError, setLoadError] = useState('');
    const [serverFiles, setServerFiles] = useState({ documents: [], logs: [], metrics: [] });
    const endRef = useRef(null);

    async function loadFiles() {
        try {
            setServerFiles(await api(`/conversations/${conversationId}/files`));
        } catch (error) {
            setLoadError(error.message);
        }
    }

    // load saved messages + files when a conversation is opened
    useEffect(() => {
        let cancelled = false;
        api(`/conversations/${conversationId}/messages`)
            .then((rows) => { if (!cancelled) setMessages(toGroups(rows)); })
            .catch((error) => { if (!cancelled) setLoadError(error.message); });
        loadFiles();
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conversationId]);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages]);

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
            tools: [],
        }]);

        const notes = [];
        let tools = [];
        let answer = '';
        try {
            for (const file of selectedFiles) {
                try {
                    const body = new FormData();
                    body.append('file', file);
                    const result = await api(`/conversations/${conversationId}/upload`, { method: 'POST', form: body });
                    notes.push(`Uploaded ${result.filename} [${result.kind}: ${result.detail}]`);
                } catch (error) {
                    notes.push(`Could not upload ${file.name}: ${error.message}`);
                }
            }
            if (selectedFiles.length) await loadFiles();

            if (question) {
                const result = await api(`/conversations/${conversationId}/chat`, {
                    method: 'POST',
                    json: { message: question },
                });
                answer = result.answer;
                tools = result.tools_used || [];
            }
            const prefix = notes.length ? `${notes.join('\n')}\n\n` : '';
            setMessages((previous) => previous.map((m) =>
                m.id === messageId ? { ...m, answer: prefix + answer, tools, status: '' } : m
            ));
        } catch (error) {
            setMessages((previous) => previous.map((m) =>
                m.id === messageId ? { ...m, status: '', answer: `Error: ${error.message}` } : m
            ));
        } finally {
            setBusy(false);
            onChanged?.();
        }
    }

    async function handleDeleteFile(fileId) {
        try {
            await api(`/files/${fileId}`, { method: 'DELETE' });
            await loadFiles();
            onChanged?.();
        } catch (error) {
            setLoadError(error.message);
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

    const chatFiles = [...serverFiles.logs, ...serverFiles.metrics];
    const nothingUploaded = serverFiles.documents.length === 0 && chatFiles.length === 0;

    return (
        <main>
            <div className="files-bar">
                {nothingUploaded && (
                    <span className="files-empty">No files yet. Attach runbooks, logs or metrics with the + button.</span>
                )}
                {serverFiles.documents.length > 0 && (
                    <div className="files-group">
                        <span className="files-label">Your runbooks (all chats):</span>
                        {serverFiles.documents.map((f) => <FileChip key={f.id} file={f} icon="📘" onDelete={handleDeleteFile} />)}
                    </div>
                )}
                {chatFiles.length > 0 && (
                    <div className="files-group">
                        <span className="files-label">This chat:</span>
                        {serverFiles.logs.map((f) => <FileChip key={f.id} file={f} icon="📜" onDelete={handleDeleteFile} />)}
                        {serverFiles.metrics.map((f) => <FileChip key={f.id} file={f} icon="📈" onDelete={handleDeleteFile} />)}
                    </div>
                )}
                {loadError && <div className="auth-error">{loadError}</div>}
            </div>

            {messages.length === 0 ? (
                <div className="chat">
                    <h2>How can I help?</h2>
                    <p>Attach runbooks (PDF), logs (.log) or metrics (.json / .csv) with the + button, then ask about your incident.</p>
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
                            {message.tools?.length > 0 && !message.status && (
                                <div className="tools-used">Tools used: {message.tools.join(', ')}</div>
                            )}
                        </div>
                    ))}
                    <div ref={endRef} />
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
                    <input type="file" accept=".pdf,.md,.txt,.log,.jsonl,.json,.csv" id="pdf-upload" hidden multiple onChange={handleFileChange} />
                    <label htmlFor="pdf-upload" className="upload-button" title="Attach runbooks (PDF/MD), logs (.log/.txt) or metrics (.json/.csv)" aria-label="Attach files">+</label>
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
