export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete }) {
    return (
        <aside className="sidebar">
            <button type="button" className="new-chat" onClick={onNew}>+ New chat</button>

            <div className="conversation-list">
                {conversations.map((c) => (
                    <div
                        key={c.id}
                        className={c.id === activeId ? 'conversation-item active' : 'conversation-item'}
                    >
                        <button
                            type="button"
                            className="conversation-title"
                            title={c.title}
                            onClick={() => onSelect(c.id)}
                        >
                            {c.title}
                        </button>
                        <button
                            type="button"
                            className="conversation-delete"
                            aria-label={`Delete chat ${c.title}`}
                            onClick={() => onDelete(c.id)}
                        >
                            ×
                        </button>
                    </div>
                ))}
            </div>
        </aside>
    );
}