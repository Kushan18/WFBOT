import React, { useState, useEffect } from 'react';
import Chat from './components/Chat.jsx';
import ProfileModal from './components/ProfileModal.jsx';
import AdminDashboard from './components/AdminDashboard.jsx';

function genSession() { return 'sess_' + Math.random().toString(36).substring(2, 15); }

export default function App() {
  const [sessionId] = useState(() => {
    const existing = localStorage.getItem('wb_session_id');
    if (existing) return existing;
    const id = genSession();
    localStorage.setItem('wb_session_id', id);
    return id;
  });
  const [userName, setUserName] = useState(() => localStorage.getItem('wb_user_name') || '');
  const [showModal, setShowModal] = useState(false);
  const [prefillName, setPrefillName] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => { if (userName) localStorage.setItem('wb_user_name', userName); }, [userName]);

  const handleOpenForm = (name) => { setPrefillName(name || userName); setShowModal(true); };

  // Simple admin toggle (in production, use proper authentication)
  const toggleAdmin = () => setIsAdmin(!isAdmin);

  return (
    <div style={{ height: '100%' }}>
      {isAdmin ? (
        <div>
          <AdminDashboard />
          <button 
            onClick={toggleAdmin}
            style={{
              position: 'fixed',
              top: '20px',
              right: '20px',
              padding: '10px 20px',
              background: 'var(--accent-gradient)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              zIndex: 1000
            }}
          >
            Back to Chat
          </button>
        </div>
      ) : (
        <div style={{ height: '100%' }}>
          <Chat sessionId={sessionId} userName={userName} onNameCapture={setUserName} onOpenForm={handleOpenForm} />
          {showModal && <ProfileModal sessionId={sessionId} prefillName={prefillName} onClose={() => setShowModal(false)} />}
          <button 
            onClick={toggleAdmin}
            style={{
              position: 'fixed',
              bottom: '20px',
              right: '20px',
              padding: '10px 20px',
              background: 'var(--bg-tertiary)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border-medium)',
              borderRadius: '8px',
              cursor: 'pointer',
              zIndex: 1000,
              fontSize: '12px'
            }}
          >
            Admin
          </button>
        </div>
      )}
    </div>
  );
}
