import { useState, useEffect } from 'react';
import { RepoInput } from './components/RepoInput';
import { ChatInterface } from './components/ChatInterface';
import { Auth } from './components/Auth';
import { RepoHistory } from './components/RepoHistory';
import './App.css';

interface User {
  id: number;
  username: string;
  email: string;
}

interface AnalysisProgress {
  status: string;
  message: string;
  current?: number;
  total?: number;
  stats?: any;
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [repository, setRepository] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [showRepoHistory, setShowRepoHistory] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');

  // Check for existing session on load
  useEffect(() => {
    const token = localStorage.getItem('session_token');
    const userData = localStorage.getItem('user_data');
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme) {
      setIsDarkMode(savedTheme === 'dark');
    }
    
    if (token && userData) {
      try {
        const user = JSON.parse(userData);
        setSessionToken(token);
        setUser(user);
      } catch (error) {
        // Invalid stored data, clear it
        localStorage.removeItem('session_token');
        localStorage.removeItem('user_data');
      }
    }
  }, []);

  useEffect(() => {
    document.body.className = isDarkMode ? 'dark' : 'light';
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  const handleLogin = (userData: User, token: string) => {
    setUser(userData);
    setSessionToken(token);
    localStorage.setItem('session_token', token);
    localStorage.setItem('user_data', JSON.stringify(userData));
  };

  const handleLogout = () => {
    setUser(null);
    setSessionToken(null);
    setRepository(null);
    setShowRepoHistory(false);
    localStorage.removeItem('session_token');
    localStorage.removeItem('user_data');
  };

  const handleBackToHome = () => {
    setRepository(null);
    setIsAnalyzing(false);
    setAnalysisProgress(null);
  };

  const handleSelectRepository = (repoName: string) => {
    setRepository(repoName);
  };

  const getAuthHeaders = () => ({
    'Content-Type': 'application/json',
    ...(sessionToken && { 'Authorization': `Bearer ${sessionToken}` }),
  });

  const handleAnalyzeRepository = async (url: string) => {
    setIsAnalyzing(true);
    setAnalysisProgress(null);
    setRepository(null);

    try {
      // Extract repository name from URL
      const repoMatch = url.match(/github\.com\/([^\/]+\/[^\/]+)/);
      const repoName = repoMatch ? repoMatch[1] : url;

      // Start repository analysis with auth headers
      const response = await fetch('/api/repos/analyze', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          handleLogout();
          return;
        }
        throw new Error('Failed to start repository analysis');
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response reader available');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              setAnalysisProgress(data);

              if (data.status === 'complete') {
                setRepository(repoName);
                setIsAnalyzing(false);
              } else if (data.status === 'error') {
                console.error('Analysis error:', data.message);
                setIsAnalyzing(false);
              }
            } catch (error) {
              console.error('Error parsing SSE data:', error);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error analyzing repository:', error);
      setIsAnalyzing(false);
      setAnalysisProgress({
        status: 'error',
        message: 'Failed to analyze repository. Please try again.'
      });
    }
  };

  // Show auth component if user is not logged in
  if (!user) {
    return <Auth onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      {/* Enhanced Header with Navigation */}
      <div className="top-bar">
        <div className="breadcrumb">
          {repository ? (
            <div className="navigation">
              <button 
                onClick={handleBackToHome}
                className="nav-button"
                title="Back to home"
              >
                ← Home
              </button>
              <span className="nav-separator">/</span>
              <span className="current-repo">{repository}</span>
              <div className="connection-status">
                <span className={`status-indicator status-${connectionStatus}`}></span>
                <span className="status-text">{connectionStatus}</span>
              </div>
            </div>
          ) : (
            <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: '600', color: 'hsl(var(--foreground))' }}>
              CompassChat
            </h1>
          )}
        </div>
        <div className="top-bar-actions">
          <span className="username-display">
            👤 {user.username}
          </span>
          <button 
            onClick={() => setIsDarkMode(!isDarkMode)}
            className="action-button"
            title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDarkMode ? '☀️' : '🌙'}
          </button>
          <button onClick={handleLogout} className="action-button">
            Logout
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="content-area">
        {!repository ? (
          <div className="repo-input-container" style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center', 
            height: '100%',
            padding: '2rem'
          }}>
            <RepoInput 
              onAnalyze={handleAnalyzeRepository}
              isAnalyzing={isAnalyzing}
              onShowHistory={() => setShowRepoHistory(true)}
            />
          </div>
        ) : (
          <div className="chat-container" style={{ 
            width: '100%', 
            height: '100%', 
            display: 'flex', 
            flexDirection: 'column'
          }}>
            <ChatInterface 
              repository={repository}
              analysisProgress={analysisProgress}
              isAnalyzing={isAnalyzing}
              authHeaders={getAuthHeaders}
              onConnectionStatusChange={setConnectionStatus}
            />
          </div>
        )}
      </div>
      
      {/* Repository History Modal */}
      {showRepoHistory && (
        <RepoHistory
          authHeaders={getAuthHeaders}
          onSelectRepository={handleSelectRepository}
          onClose={() => setShowRepoHistory(false)}
        />
      )}
      
      {analysisProgress && analysisProgress.status === 'error' && (
        <div className="error-overlay">
          <div className="error-dialog">
            <h3>Analysis Error</h3>
            <p>{analysisProgress.message}</p>
            <button 
              onClick={() => {
                setAnalysisProgress(null);
                setRepository(null);
                setIsAnalyzing(false);
              }}
              className="error-close-button"
            >
              Try Again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
