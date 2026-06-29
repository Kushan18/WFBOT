import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import MessageBubble from './MessageBubble.jsx';
import ChipRow from './ChipRow.jsx';
import './Chat.css';

const API = import.meta.env.VITE_API_URL || (window.location.hostname === 'localhost' ? 'http://localhost:8000' : '');

const svgIcon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="45" fill="url(#grad)" />
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#8b5cf6;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#6366f1;stop-opacity:1" />
    </linearGradient>
  </defs>
  <text x="50" y="65" font-size="50" font-weight="bold" fill="white" text-anchor="middle" font-family="Arial">?</text>
</svg>`;
const questionMarkIcon = `data:image/svg+xml,${encodeURIComponent(svgIcon)}`;

const WELCOME = {
  id: 'w', role: 'bot',
  text: "Welcome to WelfareBot! We help Indian citizens discover government welfare schemes they may be eligible for.\n\nTo get started, what is your name?",
  chips: [], timestamp: new Date()
};

const SESSION_KEY = 'welfarebot_session';
const SESSION_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours

export default function Chat({ sessionId, userName, onNameCapture, onOpenForm }) {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [isListeningSupported, setIsListeningSupported] = useState(false);
  const [langPreference, setLangPreference] = useState('en');
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);
  const msgCount = useRef(1);

  // Check for speech recognition support
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      setIsListeningSupported(true);
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-IN';

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
        setIsRecording(false);
        // Auto-submit after a short delay
        setTimeout(() => {
          if (transcript.trim()) {
            sendMessage(transcript);
          }
        }, 500);
      };

      recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsRecording(false);
      };

      recognition.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = recognition;
    }
  }, []);

  const startRecording = useCallback(() => {
    if (recognitionRef.current && !isRecording) {
      try {
        const langMap = {
          'en': 'en-IN',
          'hi': 'hi-IN',
          'te': 'te-IN',
          'ta': 'ta-IN',
          'kn': 'kn-IN'
        };
        recognitionRef.current.lang = langMap[langPreference] || 'en-IN';
        recognitionRef.current.start();
        setIsRecording(true);
      } catch (err) {
        console.error('Failed to start recording:', err);
      }
    }
  }, [isRecording, langPreference]);

  const stopRecording = useCallback(() => {
    if (recognitionRef.current && isRecording) {
      recognitionRef.current.stop();
      setIsRecording(false);
    }
  }, [isRecording]);

  // Load session from localStorage on mount
  useEffect(() => {
    try {
      const savedSession = localStorage.getItem(SESSION_KEY);
      if (savedSession) {
        const session = JSON.parse(savedSession);
        const now = Date.now();
        // Check if session is expired
        if (now - session.timestamp < SESSION_EXPIRY) {
          setMessages(session.messages);
          msgCount.current = session.msgCount || 1;
          if (session.userName) onNameCapture(session.userName);
          if (session.langPreference) setLangPreference(session.langPreference);
        } else {
          // Clear expired session
          localStorage.removeItem(SESSION_KEY);
        }
      }
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  }, [onNameCapture]);

  // Save session to localStorage whenever messages or state changes
  useEffect(() => {
    try {
      const session = {
        messages,
        msgCount: msgCount.current,
        userName,
        langPreference,
        timestamp: Date.now()
      };
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (err) {
      console.error('Failed to save session:', err);
    }
  }, [messages, userName, langPreference]);

  useEffect(() => { axios.get(API + '/health').then(() => setIsOnline(true)).catch(() => setIsOnline(false)); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  const addMsg = useCallback((role, text, chips = [], confidenceScore = null) => {
    setMessages(prev => [...prev, { 
      id: Date.now() + Math.random(), 
      role,
      text,
      chips,
      confidence_score: confidenceScore,
      timestamp: new Date() 
    }]);
  }, []);

  const sendMessage = useCallback(async (text) => {
    const t = text.trim();
    if (!t || loading) return;
    addMsg('user', t);
    setInput('');
    setLoading(true);
    msgCount.current += 1;
    try {
      const res = await axios.post(API + '/chat', { session_id: sessionId, message: t }, { timeout: 30000 });
      const { reply, show_form_choice, chips, user_name, language_preference, confidence_score } = res.data;
      addMsg('bot', reply, chips || [], confidence_score);
      if (user_name) onNameCapture(user_name);
      if (language_preference) setLangPreference(language_preference);
      if (show_form_choice) onOpenForm(user_name || userName || t);
    } catch (err) {
      const msg = err.code === 'ECONNABORTED' ? 'Request timed out - please try again.' : 'Something went wrong. Is the backend running?';
      addMsg('bot', msg);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [loading, sessionId, userName, addMsg, onNameCapture, onOpenForm]);

  const clearSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem('wb_user_name');
    setMessages([WELCOME]);
    msgCount.current = 1;
    setInput('');
    onNameCapture('');
    setLangPreference('en');
  }, [onNameCapture]);

  const lastChips = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'bot' && messages[i].chips?.length > 0) return { idx: i, chips: messages[i].chips };
    }
    return null;
  })();

  return (
    <div className='chat-root'>
      <header className='chat-header'>
        <div className='chat-header-left'>
          <div className='bot-avatar'><img src={questionMarkIcon} alt="Bot" /></div>
          <div>
            <div className='bot-name'>WelfareBot</div>
            <div className='bot-status'>
              <span className='status-dot' />{isOnline ? 'Online' : 'Offline - start backend'}
            </div>
          </div>
        </div>
        <button 
          onClick={clearSession}
          className='modal-close'
          title='Clear conversation'
          style={{ fontSize: '16px' }}
        >
          🗑️
        </button>
      </header>
      <div className='chat-messages'>
        {messages.map((msg, idx) => (
          <React.Fragment key={msg.id}>
            <MessageBubble message={msg} />
            {lastChips && lastChips.idx === idx && (
              <ChipRow chips={lastChips.chips} onChipClick={(c) => { 
                if (c.includes('Fill Form')) onOpenForm(userName);
                else if (c.includes('Start Over')) {
                  clearSession();
                } else sendMessage(c);
              }} disabled={loading} />
            )}
          </React.Fragment>
        ))}
        {loading && <div className='typing-indicator'><span /><span /><span /></div>}
        <div ref={bottomRef} />
      </div>
      <form className='chat-input-bar' onSubmit={e => { e.preventDefault(); sendMessage(input); }}>
        {isListeningSupported && (
          <button 
            type='button' 
            onClick={isRecording ? stopRecording : startRecording}
            className={isRecording ? 'btn-mic recording' : 'btn-mic'}
            disabled={loading}
            title={isRecording ? 'Stop recording' : 'Start voice input'}
          >
            <svg width='20' height='20' viewBox='0 0 24 24' fill='none'>
              <path d='M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
              <path d='M19 10v2a7 7 0 0 1-14 0v-2' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
              <line x1='12' y1='19' x2='12' y2='23' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
              <line x1='8' y1='23' x2='16' y2='23' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
            </svg>
          </button>
        )}
        <input ref={inputRef} className='chat-input' type='text' value={input} onChange={e => setInput(e.target.value)} placeholder={isRecording ? 'Listening...' : loading ? 'WelfareBot is typing...' : 'Type a message...'} disabled={loading} autoComplete='off' />
        <button className='btn-send' type='submit' disabled={loading || !input.trim()}>
          <svg width='20' height='20' viewBox='0 0 24 24' fill='none'>
            <path d='M22 2L11 13' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
            <path d='M22 2L15 22L11 13L2 9L22 2Z' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
          </svg>
        </button>
      </form>
    </div>
  );
}
