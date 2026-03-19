import React, { useState, useRef, useEffect } from 'react';
import io from 'socket.io-client';

import Visualizer from './components/Visualizer';
import TopAudioBar from './components/TopAudioBar';
import CadWindow from './components/CadWindow';
import BrowserWindow from './components/BrowserWindow';
import ChatModule from './components/ChatModule';
import ToolsModule from './components/ToolsModule';
import { Mic, MicOff, Settings, X, Minus, Power, Video, VideoOff, Layout, Hand, Printer, Clock, MessageSquare, Globe, Cpu, Volume2, Send, LayoutGrid } from 'lucide-react';
import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';
import ConfirmationPopup from './components/ConfirmationPopup';
import AuthLock from './components/AuthLock';
import KasaWindow from './components/KasaWindow';
import PrinterWindow from './components/PrinterWindow';
import SettingsWindow from './components/SettingsWindow';

const socket = io('http://localhost:8000');
const { ipcRenderer } = window.require('electron');

const API_BASE = 'http://localhost:8000';

function WebChatView({ onClose }) {
    const [messages, setMessages] = useState([]);
    const [inputValue, setInputValue] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const [currentMode, setCurrentMode] = useState('astro');
    const [isListening, setIsListening] = useState(false);
    const [ttsEnabled, setTtsEnabled] = useState(false);
    const [activityLogs, setActivityLogs] = useState([]);
    const [showActivity, setShowActivity] = useState(true);
    const [showSearchResults, setShowSearchResults] = useState(false);
    const [searchResults, setSearchResults] = useState(null);

    const messagesEndRef = useRef(null);
    const recognitionRef = useRef(null);
    const currentAudioRef = useRef(null);

    useEffect(() => {
        initSpeechRecognition();
        updateGreeting();
    }, []);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const updateGreeting = () => {
        const hour = new Date().getHours();
        let greeting = 'Good evening';
        if (hour < 12) greeting = 'Good morning';
        else if (hour < 17) greeting = 'Good afternoon';
        setGreetingPrefix(greeting);
    };

    const [greetingPrefix, setGreetingPrefix] = useState('Good evening');

    const initSpeechRecognition = () => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = true;
            recognitionRef.current.interimResults = true;

            recognitionRef.current.onstart = () => {
                setIsListening(true);
            };

            recognitionRef.current.onresult = (event) => {
                let transcript = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    transcript += event.results[i][0].transcript;
                }
                setInputValue(transcript);
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
                if (inputValue.trim()) {
                    sendMessage();
                }
            };

            recognitionRef.current.onerror = () => {
                setIsListening(false);
            };
        }
    };

    const addActivityLog = (event, message) => {
        setActivityLogs(prev => [...prev.slice(-20), { event, message, time: new Date() }]);
    };

    const addMessage = (content, role = 'assistant') => {
        setMessages(prev => [...prev, { content, role, id: Date.now() }]);
    };

    const sendMessage = async () => {
        const message = inputValue.trim();
        if (!message || isStreaming) return;

        setIsStreaming(true);
        setInputValue('');
        addMessage(message, 'user');
        addActivityLog('query', message);

        try {
            const response = await fetch(`${API_BASE}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    session_id: sessionId,
                    mode: currentMode
                })
            });

            if (!response.ok) throw new Error('Request failed');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullResponse = '';

            addMessage('', 'assistant');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value);
                const lines = text.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.session_id && !sessionId) {
                                setSessionId(data.session_id);
                            }

                            if (data.chunk) {
                                fullResponse += data.chunk;
                                setMessages(prev => {
                                    const updated = [...prev];
                                    const lastIdx = updated.length - 1;
                                    if (updated[lastIdx]?.role === 'assistant') {
                                        updated[lastIdx] = { ...updated[lastIdx], content: fullResponse };
                                    }
                                    return updated;
                                });
                            }

                            if (data._activity) {
                                handleActivity(data._activity);
                            }

                            if (data._search_results) {
                                setSearchResults(data._search_results);
                                setShowSearchResults(true);
                            }

                            if (data.audio && ttsEnabled) {
                                playAudio(data.audio);
                            }

                            if (data.done) {
                                setIsStreaming(false);
                            }
                        } catch (e) {
                            console.error('Parse error:', e);
                        }
                    }
                }
            }
        } catch (error) {
            setIsStreaming(false);
            addMessage('Error: ' + error.message, 'assistant');
        }
    };

    const handleActivity = (activity) => {
        if (activity.event === 'query_detected') {
            addActivityLog('query', activity.message);
        } else if (activity.event === 'decision') {
            addActivityLog('decision', `${activity.query_type}: ${activity.reasoning || ''}`);
        } else if (activity.event === 'routing') {
            addActivityLog('routing', `Route: ${activity.route}`);
        } else if (activity.event === 'search_complete') {
            addActivityLog('search', `${activity.results_count} results found`);
        }
    };

    const playAudio = (audioBase64) => {
        if (!audioBase64) return;
        try {
            const audioData = atob(audioBase64);
            const arrayBuffer = new ArrayBuffer(audioData.length);
            const uint8Array = new Uint8Array(arrayBuffer);
            for (let i = 0; i < audioData.length; i++) {
                uint8Array[i] = audioData.charCodeAt(i);
            }
            const blob = new Blob([uint8Array], { type: 'audio/mp3' });
            const url = URL.createObjectURL(blob);
            if (currentAudioRef.current) currentAudioRef.current.pause();
            currentAudioRef.current = new Audio(url);
            currentAudioRef.current.play();
        } catch (e) {
            console.error('TTS play error:', e);
        }
    };

    const toggleListening = () => {
        if (isListening) {
            recognitionRef.current?.stop();
        } else {
            recognitionRef.current?.start();
        }
    };

    const toggleTTS = () => {
        setTtsEnabled(!ttsEnabled);
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    return (
        <div className="web-chat-view">
            <div className="web-chat-header">
                <div className="header-left">
                    <h2>Web Chat</h2>
                    <span className="mode-badge">{currentMode.toUpperCase()}</span>
                </div>
                <div className="header-center">
                    <div className="mode-switch">
                        <button 
                            className={`mode-btn ${currentMode === 'astro' ? 'active' : ''}`}
                            onClick={() => setCurrentMode('astro')}
                        >
                            <Cpu size={14} /> Auto
                        </button>
                        <button 
                            className={`mode-btn ${currentMode === 'general' ? 'active' : ''}`}
                            onClick={() => setCurrentMode('general')}
                        >
                            <MessageSquare size={14} /> General
                        </button>
                        <button 
                            className={`mode-btn ${currentMode === 'realtime' ? 'active' : ''}`}
                            onClick={() => setCurrentMode('realtime')}
                        >
                            <Globe size={14} /> Web
                        </button>
                    </div>
                </div>
                <div className="header-right">
                    <button 
                        className={`icon-btn ${showActivity ? 'active' : ''}`}
                        onClick={() => setShowActivity(!showActivity)}
                        title="Activity"
                    >
                        <Layout size={18} />
                    </button>
                    <button 
                        className={`icon-btn ${showSearchResults ? 'active' : ''}`}
                        onClick={() => setShowSearchResults(!showSearchResults)}
                        title="Search Results"
                    >
                        <Globe size={18} />
                    </button>
                    <button className="icon-btn" onClick={onClose} title="Close">
                        <X size={18} />
                    </button>
                </div>
            </div>

            <div className="web-chat-body">
                {showActivity && (
                    <div className="activity-panel">
                        <div className="panel-title">Activity</div>
                        <div className="activity-list">
                            {activityLogs.length === 0 ? (
                                <div className="empty-state">Send a message to see activity</div>
                            ) : (
                                activityLogs.map((log, idx) => (
                                    <div key={idx} className={`activity-item ${log.event}`}>
                                        <div className="activity-event">{log.event}</div>
                                        <div className="activity-message">{String(log.message).slice(0, 80)}</div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                )}

                <div className="chat-container">
                    <div className="messages-container">
                        {messages.length === 0 ? (
                            <div className="welcome-screen">
                                <div className="welcome-icon">
                                    <MessageSquare size={40} />
                                </div>
                                <h2>{greetingPrefix}.</h2>
                                <p>How may I assist you today?</p>
                                <div className="quick-chips">
                                    <button onClick={() => { setInputValue('What can you do?'); sendMessage(); }}>What can you do?</button>
                                    <button onClick={() => { setInputValue('Search latest AI news'); sendMessage(); }}>AI News</button>
                                    <button onClick={() => { setInputValue('Hello'); sendMessage(); }}>Say Hello</button>
                                </div>
                            </div>
                        ) : (
                            messages.map((msg) => (
                                <div key={msg.id} className={`message ${msg.role} ${isStreaming && msg.role === 'assistant' ? 'streaming' : ''}`}>
                                    <div className="message-avatar">
                                        {msg.role === 'assistant' ? <Cpu size={16} /> : <Mic size={16} />}
                                    </div>
                                    <div className="message-content" 
                                        dangerouslySetInnerHTML={{ __html: escapeHtml(msg.content) }}
                                    />
                                </div>
                            ))
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                </div>

                {showSearchResults && (
                    <div className="search-panel">
                        <div className="panel-title">Web Search</div>
                        <div className="search-content">
                            {!searchResults ? (
                                <div className="empty-state">Search results will appear here</div>
                            ) : (
                                <>
                                    {searchResults.answer && (
                                        <div className="search-answer" 
                                            dangerouslySetInnerHTML={{ __html: escapeHtml(searchResults.answer) }}
                                        />
                                    )}
                                    <div className="search-sources">
                                        {searchResults.results?.map((r, idx) => (
                                            <div key={idx} className="source-item" onClick={() => window.open(r.url, '_blank')}>
                                                <div className="source-title">{r.title}</div>
                                                <div className="source-url">{r.url}</div>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>

            <div className="web-chat-input">
                <div className="input-wrapper">
                    <textarea
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder="Ask anything..."
                        rows={1}
                        disabled={isStreaming}
                    />
                    <div className="input-actions">
                        <button 
                            className={`action-btn ${isListening ? 'active listening' : ''}`}
                            onClick={toggleListening}
                            title="Voice Input"
                        >
                            {isListening ? <MicOff size={18} /> : <Mic size={18} />}
                        </button>
                        <button 
                            className={`action-btn ${ttsEnabled ? 'active' : ''}`}
                            onClick={toggleTTS}
                            title="Text to Speech"
                        >
                            <Volume2 size={18} />
                        </button>
                        <button 
                            className="action-btn send"
                            onClick={sendMessage}
                            disabled={isStreaming || !inputValue.trim()}
                        >
                            <Send size={18} />
                        </button>
                    </div>
                </div>
            </div>

            <style>{`
                .web-chat-view {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: #0a0a0f;
                    z-index: 1000;
                    display: flex;
                    flex-direction: column;
                }

                .web-chat-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    padding: 12px 20px;
                    background: rgba(18, 18, 26, 0.95);
                    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                }

                .web-chat-header h2 {
                    font-size: 1.1rem;
                    font-weight: 600;
                    color: #fff;
                }

                .mode-badge {
                    font-size: 0.7rem;
                    padding: 2px 8px;
                    background: rgba(0, 212, 255, 0.2);
                    color: #00d4ff;
                    border-radius: 4px;
                    margin-left: 8px;
                }

                .mode-switch {
                    display: flex;
                    gap: 4px;
                    background: #1a1a25;
                    padding: 4px;
                    border-radius: 8px;
                }

                .mode-btn {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    padding: 6px 12px;
                    border: none;
                    background: transparent;
                    color: #9ca3af;
                    font-size: 0.8rem;
                    border-radius: 6px;
                    cursor: pointer;
                    transition: all 0.2s;
                }

                .mode-btn.active {
                    background: rgba(0, 212, 255, 0.15);
                    color: #00d4ff;
                }

                .icon-btn {
                    width: 36px;
                    height: 36px;
                    border: none;
                    background: #1a1a25;
                    color: #9ca3af;
                    border-radius: 8px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .icon-btn:hover, .icon-btn.active {
                    background: rgba(0, 212, 255, 0.15);
                    color: #00d4ff;
                }

                .web-chat-body {
                    flex: 1;
                    display: flex;
                    overflow: hidden;
                }

                .activity-panel, .search-panel {
                    width: 280px;
                    background: rgba(18, 18, 26, 0.9);
                    border-right: 1px solid rgba(255, 255, 255, 0.08);
                    display: flex;
                    flex-direction: column;
                }

                .search-panel {
                    border-right: none;
                    border-left: 1px solid rgba(255, 255, 255, 0.08);
                }

                .panel-title {
                    padding: 12px 16px;
                    font-size: 0.85rem;
                    font-weight: 600;
                    color: #9ca3af;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                }

                .activity-list, .search-content {
                    flex: 1;
                    overflow-y: auto;
                    padding: 12px;
                }

                .activity-item {
                    background: #1a1a25;
                    border-radius: 8px;
                    padding: 10px;
                    margin-bottom: 8px;
                    border-left: 3px solid #00d4ff;
                }

                .activity-item.decision {
                    border-left-color: #8b5cf6;
                }

                .activity-item.search {
                    border-left-color: #10b981;
                }

                .activity-event {
                    font-size: 0.7rem;
                    color: #6b7280;
                    text-transform: uppercase;
                    margin-bottom: 4px;
                }

                .activity-message {
                    font-size: 0.8rem;
                    color: #e5e7eb;
                }

                .chat-container {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }

                .messages-container {
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                }

                .welcome-screen {
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    text-align: center;
                }

                .welcome-icon {
                    width: 80px;
                    height: 80px;
                    background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(139, 92, 246, 0.15));
                    border-radius: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: #00d4ff;
                    margin-bottom: 20px;
                }

                .welcome-screen h2 {
                    font-size: 1.5rem;
                    margin-bottom: 8px;
                }

                .welcome-screen p {
                    color: #9ca3af;
                    margin-bottom: 20px;
                }

                .quick-chips {
                    display: flex;
                    gap: 8px;
                    flex-wrap: wrap;
                    justify-content: center;
                }

                .quick-chips button {
                    padding: 8px 16px;
                    background: #1a1a25;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    color: #9ca3af;
                    border-radius: 20px;
                    font-size: 0.85rem;
                    cursor: pointer;
                }

                .quick-chips button:hover {
                    background: rgba(0, 212, 255, 0.1);
                    color: #00d4ff;
                    border-color: #00d4ff;
                }

                .message {
                    display: flex;
                    gap: 12px;
                    margin-bottom: 16px;
                    max-width: 80%;
                }

                .message.user {
                    flex-direction: row-reverse;
                    align-self: flex-end;
                }

                .message-avatar {
                    width: 32px;
                    height: 32px;
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex-shrink: 0;
                }

                .message.assistant .message-avatar {
                    background: linear-gradient(135deg, #00d4ff, #8b5cf6);
                    color: white;
                }

                .message.user .message-avatar {
                    background: #1a1a25;
                    color: #9ca3af;
                }

                .message-content {
                    background: #1a1a25;
                    padding: 12px 16px;
                    border-radius: 12px;
                    font-size: 0.9rem;
                    line-height: 1.5;
                    white-space: pre-wrap;
                    word-break: break-word;
                }

                .message.user .message-content {
                    background: rgba(0, 212, 255, 0.1);
                    border: 1px solid rgba(0, 212, 255, 0.3);
                }

                .message.streaming .message-content::after {
                    content: '|';
                    animation: blink 0.7s infinite;
                    color: #00d4ff;
                }

                @keyframes blink {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0; }
                }

                .search-answer {
                    background: #1a1a25;
                    padding: 12px;
                    border-radius: 8px;
                    margin-bottom: 12px;
                    font-size: 0.85rem;
                    line-height: 1.5;
                    border-left: 3px solid #10b981;
                }

                .source-item {
                    background: #1a1a25;
                    padding: 10px;
                    border-radius: 8px;
                    margin-bottom: 8px;
                    cursor: pointer;
                }

                .source-item:hover {
                    background: rgba(0, 212, 255, 0.1);
                }

                .source-title {
                    font-size: 0.85rem;
                    color: #00d4ff;
                    margin-bottom: 4px;
                }

                .source-url {
                    font-size: 0.7rem;
                    color: #6b7280;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }

                .empty-state {
                    color: #6b7280;
                    font-size: 0.8rem;
                    text-align: center;
                    padding: 20px;
                }

                .web-chat-input {
                    padding: 16px 20px;
                    background: rgba(18, 18, 26, 0.95);
                    border-top: 1px solid rgba(255, 255, 255, 0.08);
                }

                .input-wrapper {
                    display: flex;
                    align-items: flex-end;
                    gap: 12px;
                    background: #1a1a25;
                    border-radius: 12px;
                    padding: 8px 12px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }

                .input-wrapper:focus-within {
                    border-color: #00d4ff;
                }

                .input-wrapper textarea {
                    flex: 1;
                    background: none;
                    border: none;
                    color: #fff;
                    font-size: 0.9rem;
                    resize: none;
                    max-height: 100px;
                    line-height: 1.5;
                    outline: none;
                }

                .input-actions {
                    display: flex;
                    gap: 8px;
                }

                .action-btn {
                    width: 36px;
                    height: 36px;
                    border: none;
                    background: transparent;
                    color: #9ca3af;
                    border-radius: 8px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .action-btn:hover {
                    background: rgba(0, 212, 255, 0.1);
                    color: #00d4ff;
                }

                .action-btn.active {
                    background: rgba(0, 212, 255, 0.15);
                    color: #00d4ff;
                }

                .action-btn.listening {
                    background: rgba(239, 68, 68, 0.2);
                    color: #ef4444;
                    animation: pulse 1s infinite;
                }

                @keyframes pulse {
                    0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
                    50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
                }

                .action-btn.send {
                    background: #00d4ff;
                    color: #0a0a0f;
                }

                .action-btn.send:hover {
                    background: #00b8e6;
                }

                .action-btn:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }
            `}</style>
        </div>
    );
}

function App() {
    const [status, setStatus] = useState('Disconnected');
    const [socketConnected, setSocketConnected] = useState(socket.connected);
    const [isAuthenticated, setIsAuthenticated] = useState(() => {
        return localStorage.getItem('face_auth_enabled') !== 'true';
    });

    const [isLockScreenVisible, setIsLockScreenVisible] = useState(() => {
        const saved = localStorage.getItem('face_auth_enabled');
        return saved === 'true';
    });

    const [faceAuthEnabled, setFaceAuthEnabled] = useState(() => {
        return localStorage.getItem('face_auth_enabled') === 'true';
    });

    const [isConnected, setIsConnected] = useState(true);
    const [isMuted, setIsMuted] = useState(true);
    const [isVideoOn, setIsVideoOn] = useState(false);
    const [messages, setMessages] = useState([]);
    const [inputValue, setInputValue] = useState('');
    const [cadData, setCadData] = useState(null);
    const [cadThoughts, setCadThoughts] = useState('');
    const [cadRetryInfo, setCadRetryInfo] = useState({ attempt: 1, maxAttempts: 3, error: null });
    const [browserData, setBrowserData] = useState({ image: null, logs: [] });
    const [confirmationRequest, setConfirmationRequest] = useState(null);
    const [kasaDevices, setKasaDevices] = useState([]);
    const [showKasaWindow, setShowKasaWindow] = useState(false);
    const [showPrinterWindow, setShowPrinterWindow] = useState(false);
    const [showCadWindow, setShowCadWindow] = useState(false);
    const [showBrowserWindow, setShowBrowserWindow] = useState(false);
    const [showWebChat, setShowWebChat] = useState(false);

    const [slicingStatus, setSlicingStatus] = useState({ active: false, percent: 0, message: '' });
    const [activePrintStatus, setActivePrintStatus] = useState(null);
    const [printerCount, setPrinterCount] = useState(0);
    const [currentTime, setCurrentTime] = useState(new Date());

    const [aiAudioData, setAiAudioData] = useState(new Array(64).fill(0));
    const [micAudioData, setMicAudioData] = useState(new Array(32).fill(0));
    const [fps, setFps] = useState(0);

    const [micDevices, setMicDevices] = useState([]);
    const [speakerDevices, setSpeakerDevices] = useState([]);
    const [webcamDevices, setWebcamDevices] = useState([]);

    const [selectedMicId, setSelectedMicId] = useState(() => localStorage.getItem('selectedMicId') || '');
    const [selectedSpeakerId, setSelectedSpeakerId] = useState(() => localStorage.getItem('selectedSpeakerId') || '');
    const [selectedWebcamId, setSelectedWebcamId] = useState(() => localStorage.getItem('selectedWebcamId') || '');
    const [showSettings, setShowSettings] = useState(false);
    const [currentProject, setCurrentProject] = useState('default');

    const [isModularMode, setIsModularMode] = useState(false);
    const [elementPositions, setElementPositions] = useState({
        video: { x: 40, y: 80 },
        visualizer: { x: window.innerWidth / 2, y: window.innerHeight / 2 - 150 },
        chat: { x: window.innerWidth / 2, y: window.innerHeight / 2 + 100 },
        cad: { x: window.innerWidth / 2 + 300, y: window.innerHeight / 2 },
        browser: { x: window.innerWidth / 2 - 300, y: window.innerHeight / 2 },
        kasa: { x: window.innerWidth / 2 + 350, y: window.innerHeight / 2 - 100 },
        printer: { x: window.innerWidth / 2 - 350, y: window.innerHeight / 2 - 100 },
        tools: { x: window.innerWidth / 2, y: window.innerHeight - 100 }
    });

    // WebChat state
    const [webChatMode, setWebChatMode] = useState('astro');

    return (
        <>
            {showWebChat && <WebChatView onClose={() => setShowWebChat(false)} />}
            
            {/* Rest of existing App.jsx content... */}
            {isLockScreenVisible && !isAuthenticated ? (
                <AuthLock onAuthenticate={() => {
                    setIsAuthenticated(true);
                    setIsLockScreenVisible(false);
                }} />
            ) : (
                <div className={`app-container ${isModularMode ? 'modular-mode' : ''}`}>
                    {/* Header */}
                    <header className="top-bar">
                        <div className="top-bar-left">
                            <h1 className="app-title">
                                <span className="ada-logo">A.D.A</span>
                                <span className="subtitle">Advanced Design Assistant</span>
                            </h1>
                        </div>
                        
                        <div className="top-bar-center">
                            <div className="mode-indicator">
                                <span className={`status-dot ${status === 'Listening' ? 'listening' : ''} ${isMuted ? 'muted' : ''}`}></span>
                                <span className="status-text">{status}</span>
                            </div>
                        </div>

                        <div className="top-bar-right">
                            <div className="toolbar-buttons">
                                <button 
                                    className={`toolbar-btn ${showWebChat ? 'active' : ''}`}
                                    onClick={() => setShowWebChat(!showWebChat)}
                                    title="Web Chat"
                                >
                                    <Globe size={18} />
                                </button>
                                <button 
                                    className={`toolbar-btn ${showCadWindow ? 'active' : ''}`}
                                    onClick={() => setShowCadWindow(!showCadWindow)}
                                    title="CAD"
                                >
                                    <Layout size={18} />
                                </button>
                                <button 
                                    className={`toolbar-btn ${showBrowserWindow ? 'active' : ''}`}
                                    onClick={() => setShowBrowserWindow(!showBrowserWindow)}
                                    title="Browser"
                                >
                                    <Globe size={18} />
                                </button>
                                <button 
                                    className={`toolbar-btn ${showKasaWindow ? 'active' : ''}`}
                                    onClick={() => setShowKasaWindow(!showKasaWindow)}
                                    title="Smart Home"
                                >
                                    <Power size={18} />
                                </button>
                                <button 
                                    className={`toolbar-btn ${showPrinterWindow ? 'active' : ''}`}
                                    onClick={() => setShowPrinterWindow(!showPrinterWindow)}
                                    title="3D Printer"
                                >
                                    <Printer size={18} />
                                </button>
                            </div>

                            <div className="window-controls">
                                <button 
                                    className="window-btn"
                                    onClick={() => ipcRenderer.send('minimize-window')}
                                >
                                    <Minus size={16} />
                                </button>
                                <button 
                                    className="window-btn power-btn"
                                    onClick={() => {
                                        setIsConnected(!isConnected);
                                        setStatus(isConnected ? 'Disconnected' : 'Ready');
                                    }}
                                >
                                    <Power size={16} />
                                </button>
                                <button 
                                    className="window-btn"
                                    onClick={() => ipcRenderer.send('close-window')}
                                >
                                    <X size={16} />
                                </button>
                            </div>
                        </div>
                    </header>

                    {/* Main Content */}
                    <main className="main-content">
                        {!isModularMode ? (
                            <div className="classic-layout">
                                {/* Video + Visualizer + Chat */}
                                <div className="center-section">
                                    {isVideoOn && (
                                        <div className="video-container">
                                            <video 
                                                id="webcam" 
                                                autoPlay 
                                                playsInline 
                                                muted 
                                                className="webcam-feed"
                                            />
                                        </div>
                                    )}
                                    
                                    <div className="visualizer-section">
                                        <Visualizer 
                                            aiAudioData={aiAudioData} 
                                            micAudioData={micAudioData}
                                            isMuted={isMuted}
                                        />
                                    </div>

                                    <div className="chat-section">
                                        <ChatModule 
                                            messages={messages}
                                            setMessages={setMessages}
                                            inputValue={inputValue}
                                            setInputValue={setInputValue}
                                        />
                                    </div>
                                </div>

                                {/* Tools Sidebar */}
                                <div className="tools-sidebar">
                                    <ToolsModule 
                                        isMuted={isMuted}
                                        setIsMuted={setIsMuted}
                                        isVideoOn={isVideoOn}
                                        setIsVideoOn={setIsVideoOn}
                                        showSettings={() => setShowSettings(true)}
                                        showCadWindow={() => setShowCadWindow(true)}
                                        showBrowserWindow={() => setShowBrowserWindow(true)}
                                        showKasaWindow={() => setShowKasaWindow(true)}
                                        showPrinterWindow={() => setShowPrinterWindow(true)}
                                        showWebChat={() => setShowWebChat(true)}
                                        isModularMode={isModularMode}
                                        setIsModularMode={setIsModularMode}
                                    />
                                </div>
                            </div>
                        ) : (
                            <div className="modular-layout">
                                {/* Draggable elements would go here */}
                            </div>
                        )}
                    </main>

                    {/* Windows */}
                    {showCadWindow && (
                        <CadWindow 
                            onClose={() => setShowCadWindow(false)}
                            cadData={cadData}
                            setCadData={setCadData}
                            thoughts={cadThoughts}
                            setThoughts={setCadThoughts}
                            retryInfo={cadRetryInfo}
                            setRetryInfo={setCadRetryInfo}
                        />
                    )}

                    {showBrowserWindow && (
                        <BrowserWindow 
                            onClose={() => setShowBrowserWindow(false)}
                            browserData={browserData}
                            setBrowserData={setBrowserData}
                        />
                    )}

                    {showKasaWindow && (
                        <KasaWindow 
                            onClose={() => setShowKasaWindow(false)}
                        />
                    )}

                    {showPrinterWindow && (
                        <PrinterWindow 
                            onClose={() => setShowPrinterWindow(false)}
                            slicingStatus={slicingStatus}
                            activePrintStatus={activePrintStatus}
                        />
                    )}

                    {showSettings && (
                        <SettingsWindow 
                            onClose={() => setShowSettings(false)}
                            faceAuthEnabled={faceAuthEnabled}
                            setFaceAuthEnabled={(enabled) => {
                                setFaceAuthEnabled(enabled);
                                localStorage.setItem('face_auth_enabled', String(enabled));
                                if (enabled) {
                                    setIsLockScreenVisible(true);
                                    setIsAuthenticated(false);
                                }
                            }}
                        />
                    )}

                    {confirmationRequest && (
                        <ConfirmationPopup 
                            request={confirmationRequest}
                            onConfirm={() => {
                                // Handle confirm
                                setConfirmationRequest(null);
                            }}
                            onCancel={() => setConfirmationRequest(null)}
                        />
                    )}
                </div>
            )}
        </>
    );
}

export default App;
