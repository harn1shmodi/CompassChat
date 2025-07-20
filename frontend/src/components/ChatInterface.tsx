import React, { useState, useEffect, useRef } from 'react';
import { CodeSnippet } from './CodeSnippet';
import { MarkdownRenderer } from './MarkdownRenderer';
import './ChatInterface.css';

interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  timestamp: Date;
}

interface Source {
  file_path: string;
  chunk_name: string;
  chunk_type: string;
  language: string;
  summary: string;
  score: number;
  content_preview: string;
}

interface AnalysisProgress {
  status: string;
  message: string;
  current?: number;
  total?: number;
  stats?: any;
}

interface ChatInterfaceProps {
  repository: string | null;
  analysisProgress: AnalysisProgress | null;
  isAnalyzing: boolean;
  authHeaders?: () => { [key: string]: string };
  onConnectionStatusChange?: (status: 'disconnected' | 'connecting' | 'connected') => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  repository,
  analysisProgress,
  isAnalyzing,
  authHeaders: _authHeaders,
  onConnectionStatusChange
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');

  // Notify parent of connection status changes
  useEffect(() => {
    if (onConnectionStatusChange) {
      onConnectionStatusChange(connectionStatus);
    }
  }, [connectionStatus, onConnectionStatusChange]);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };


  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (repository && !isAnalyzing) {
      connectWebSocket();
      
      // Add welcome message for existing repositories (only if no messages yet)
      if (messages.length === 0) {
        setMessages([{
          id: 'welcome',
          type: 'assistant',
          content: `Welcome back! I'm ready to help you explore the **${repository}** repository. Ask me about the code, functions, classes, or any specific implementation details you'd like to understand.`,
          timestamp: new Date()
        }]);
      }
    }
    
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [repository, isAnalyzing]);

  const connectWebSocket = () => {
    try {
      setConnectionStatus('connecting');
      
      // In development, use the proxied WebSocket URL
      // In production, use the same host as the current page
      const isDevelopment = window.location.port === '5173';
      let wsUrl;
      
      if (isDevelopment) {
        // Development: Use Vite proxy to backend
        wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/chat/ws`;
      } else {
        // Production: Use same host as the page
        wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/chat/ws`;
      }
      
      console.log('Connecting to WebSocket:', wsUrl);
      const websocket = new WebSocket(wsUrl);

      websocket.onopen = () => {
        setConnectionStatus('connected');
        setWs(websocket);
        console.log('WebSocket connected');
      };

      websocket.onclose = () => {
        setConnectionStatus('disconnected');
        setWs(null);
        console.log('WebSocket disconnected');
      };

      websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus('disconnected');
      };

      websocket.onmessage = handleWebSocketMessage;

    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      setConnectionStatus('disconnected');
    }
  };

  const handleWebSocketMessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'status':
          // Handle status updates (could show in UI)
          break;
          
        case 'answer_chunk':
          // Stream response chunks - accumulate content properly
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.type === 'assistant' && !lastMessage.sources) {
              // Update the last assistant message by appending content
              const updatedContent = lastMessage.content === '...' 
                ? data.content 
                : lastMessage.content + data.content;
              
              return prev.map((msg, index) => 
                index === prev.length - 1 
                  ? { ...msg, content: updatedContent }
                  : msg
              );
            } else {
              // Create new assistant message
              return [...prev, {
                id: Date.now().toString(),
                type: 'assistant',
                content: data.content,
                timestamp: new Date()
              }];
            }
          });
          break;
          
        case 'sources':
          // Add sources to the last assistant message
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.type === 'assistant') {
              return prev.map((msg, index) => 
                index === prev.length - 1 
                  ? { ...msg, sources: data.sources }
                  : msg
              );
            }
            return prev;
          });
          break;
          
        case 'complete':
          setIsLoading(false);
          break;
          
        case 'error':
          setIsLoading(false);
          addMessage('assistant', `Error: ${data.message}`);
          break;
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  };

  const addMessage = (type: 'user' | 'assistant', content: string, sources?: Source[]) => {
    const newMessage: Message = {
      id: Date.now().toString(),
      type,
      content,
      sources,
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, newMessage]);
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading || !ws || connectionStatus !== 'connected') {
      return;
    }

    const userMessage = inputMessage.trim();
    setInputMessage('');
    setIsLoading(true);

    // Add user message
    addMessage('user', userMessage);

    // Add loading indicator for assistant
    addMessage('assistant', '...');

    // Send message via WebSocket
    try {
      ws.send(JSON.stringify({
        question: userMessage,
        repository,
        max_results: 10
      }));
    } catch (error) {
      console.error('Error sending message:', error);
      setIsLoading(false);
      addMessage('assistant', 'Sorry, I encountered an error while processing your message.');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const renderAnalysisProgress = () => {
    if (!analysisProgress) return null;

    return (
      <div className="analysis-progress">
        <div className="progress-header">
          <h3>Repository Analysis</h3>
          <div className={`status-indicator ${analysisProgress.status}`}>
            {analysisProgress.status}
          </div>
        </div>
        
        <div className="progress-message">
          {analysisProgress.message}
        </div>
        
        {analysisProgress.current && analysisProgress.total && (
          <div className="progress-bar">
            <div 
              className="progress-fill"
              style={{ 
                width: `${(analysisProgress.current / analysisProgress.total) * 100}%` 
              }}
            />
            <span className="progress-text">
              {analysisProgress.current} / {analysisProgress.total}
            </span>
          </div>
        )}
        
        {analysisProgress.stats && (
          <div className="analysis-stats">
            <div className="stat">
              <span className="stat-label">Files:</span>
              <span className="stat-value">{analysisProgress.stats.files}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Functions:</span>
              <span className="stat-value">{analysisProgress.stats.functions}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Classes:</span>
              <span className="stat-value">{analysisProgress.stats.classes}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Chunks:</span>
              <span className="stat-value">{analysisProgress.stats.chunks}</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  if (!repository) {
    return (
      <div className="chat-interface-placeholder">
        <div className="placeholder-content">
          <h2>Welcome to CompassChat</h2>
          <p>Analyze a GitHub repository to start chatting with the code!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      {isAnalyzing && renderAnalysisProgress()}

      <div className="chat-messages">
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.type}`}>
            <div className="message-content">
              {message.type === 'assistant' ? (
                <MarkdownRenderer content={message.content} />
              ) : (
                message.content
              )}
            </div>
            
            {message.sources && message.sources.length > 0 && (
              <div className="message-sources">
                <h4>Related Code ({message.sources.length} sources):</h4>
                {message.sources.map((source, index) => (
                  <div key={index} className="source-item">
                    <div className="source-header">
                      <span className="source-file">{source.file_path}</span>
                      <span className="source-type">{source.chunk_type}</span>
                      <span className="source-score">Score: {source.score}</span>
                    </div>
                    <div className="source-summary">{source.summary}</div>
                    <CodeSnippet
                      code={source.content_preview}
                      language={source.language}
                      fileName={source.file_path}
                    />
                  </div>
                ))}
              </div>
            )}
            
            <div className="message-timestamp">
              {message.timestamp.toLocaleTimeString()}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <div className="chat-input-form">
          <div className="chat-input-wrapper">
            <textarea
              ref={inputRef}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={
                isAnalyzing 
                  ? "Please wait for analysis to complete..." 
                  : connectionStatus !== 'connected'
                  ? "Connecting to chat..."
                  : "Ask about the code..."
              }
              disabled={isLoading || isAnalyzing || connectionStatus !== 'connected'}
              className="chat-input"
              rows={1}
            />
          </div>
          <button
            onClick={sendMessage}
            disabled={!inputMessage.trim() || isLoading || isAnalyzing || connectionStatus !== 'connected'}
            className="send-button"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
};
