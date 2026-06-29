import React from 'react';
import './MessageBubble.css';

function formatTime(d) { return new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }

const svgIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="45" fill="url(#grad)" />
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#8b5cf6;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#6366f1;stop-opacity:1" />
    </linearGradient>
  </defs>
  <text x="5" y="65" font-size="50" font-weight="bold" fill="white" text-anchor="middle" font-family="Arial">?</text>
</svg>`;
const questionMarkIcon = `data:image/svg+xml,${encodeURIComponent(svgIcon)}`;

export default function MessageBubble({ message }) {
  const isBot = message.role === 'bot';
  const roleClass = isBot ? 'bot' : 'user';
  return (
    <div className={`msg-row ${roleClass}`}>
      {isBot && <div className='msg-avatar'><img src={questionMarkIcon} alt="Bot" /></div>}
      <div className={`msg-bubble ${roleClass}`}>
        <div className='msg-text'>{message.text}</div>
        {isBot && message.confidence_score !== undefined && message.confidence_score !== null && (
          <div className="confidence-badge" style={{
            fontSize: '11px',
            color: 'var(--text-secondary)',
            marginTop: '6px',
            opacity: 0.8,
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontWeight: '600'
          }}>
            ⚡ Confidence: {Math.round(message.confidence_score)}%
          </div>
        )}
        <div className='msg-time'>{formatTime(message.timestamp)}</div>
      </div>
    </div>
  );
}
