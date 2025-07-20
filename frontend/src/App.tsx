import { useState, useEffect } from 'react';
import { RepoInput } from './components/RepoInput';
import { ChatInterface } from './components/ChatInterface';
import { Auth } from './components/Auth';
import { RepoHistory } from './components/RepoHistory';
import { ChangelogGenerator } from './components/ChangelogGenerator';
import { ChangelogHistory } from './components/ChangelogHistory';
import { ProgressDialog } from './components/ProgressDialog';
import { User as UserIcon, Sun, Moon, MessageCircle, GitBranch, History } from 'lucide-react';
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

type TabType = 'chat' | 'changelog' | 'history';

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [repository, setRepository] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [showRepoHistory, setShowRepoHistory] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [activeTab, setActiveTab] = useState<TabType>('chat');
  const [currentAnalyzingRepo, setCurrentAnalyzingRepo] = useState<string>('');

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
    // Clear user session
    setUser(null);
    setSessionToken(null);
    setRepository(null);
    setShowRepoHistory(false);
    localStorage.removeItem('session_token');
    localStorage.removeItem('user_data');
    
    // Clear analysis state to prevent stale progress bars
    setIsAnalyzing(false);
    setAnalysisProgress(null);
    setCurrentAnalyzingRepo('');
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

  const refreshToken = async () => {
    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: getAuthHeaders(),
      });

      if (response.ok) {
        const data = await response.json();
        setSessionToken(data.session_token);
        localStorage.setItem('session_token', data.session_token);
        return data.session_token;
      }
    } catch (error) {
      console.error('Token refresh failed:', error);
    }
    return null;
  };

  const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const headers = { ...getAuthHeaders(), ...options.headers };
    
    let response = await fetch(url, { ...options, headers });
    
    // If 401, try to refresh token once
    if (response.status === 401 && sessionToken) {
      const newToken = await refreshToken();
      if (newToken) {
        const newHeaders = {
          ...headers,
          'Authorization': `Bearer ${newToken}`
        };
        response = await fetch(url, { ...options, headers: newHeaders });
      }
    }
    
    // If still 401, logout user
    if (response.status === 401) {
      handleLogout();
    }
    
    return response;
  };

  const handleCancelAnalysis = () => {
    setIsAnalyzing(false);
    setAnalysisProgress(null);
    setCurrentAnalyzingRepo('');
  };

  const handleAnalyzeRepository = async (url: string) => {
    setIsAnalyzing(true);
    setAnalysisProgress(null);
    setRepository(null);

    // Create AbortController for timeout handling
    const abortController = new AbortController();
    let timeoutId: number | null = null;

    try {
      // Extract repository name from URL
      const repoMatch = url.match(/github\.com\/([^\/]+\/[^\/]+)/);
      const repoName = repoMatch ? repoMatch[1] : url;
      setCurrentAnalyzingRepo(repoName);

      let isComplete = false;

      timeoutId = window.setTimeout(() => {
        abortController.abort();
      setAnalysisProgress({
          status: 'error',
          message: 'Analysis timed out after 6 minutes. Large repositories may require more time.'
        });

      // Start repository analysis with auth headers
      const response = await fetchWithAuth('/api/repos/analyze', {
        method: 'POST',
        body: JSON.stringify({ url }),
        signal: abortController.signal,
      });

      if (!response.ok) {
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
        if (done) {
          break;
        }

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
                isComplete = true;
                setRepository(repoName);
                setIsAnalyzing(false);
                setCurrentAnalyzingRepo('');
              } else if (data.status === 'error') {
                console.error('Analysis error:', data.message);
                setIsAnalyzing(false);
                setCurrentAnalyzingRepo('');
              }
            } catch (error) {
              console.error('Error parsing SSE data:', error);
            }
          }
        }
      }
      
      // Clear timeout on successful completion
      if (timeoutId) clearTimeout(timeoutId);
      
      // If we reach here without getting a 'complete' status, the stream ended prematurely
      if (!isComplete) {
        console.warn('Analysis stream ended without completion signal');
        // Keep the progress dialog open - don't immediately show error
        // Let the user see the last progress state and decide to wait or cancel
        setAnalysisProgress(prev => ({
          ...prev,
          status: prev?.status || 'indexing',
          message: 'Analysis continuing... This may take a few more minutes for large repositories.'
        }));
      }
    } catch (error) {
      if (timeoutId) clearTimeout(timeoutId);
      console.error('Error analyzing repository:', error);
      
      if (error instanceof Error && error.name === 'AbortError') {
        setIsAnalyzing(false);
        setCurrentAnalyzingRepo('');
        setAnalysisProgress({
          status: 'error',
          message: 'Analysis timed out after 15 minutes. Large repositories may require more time.'
        });
      } else if (error instanceof Error && error.message.includes('Failed to start')) {
        // Authentication or server error - don't show error state, let logout handle it
        console.log('Analysis start failed, likely due to authentication issue');
      } else {
        setIsAnalyzing(false);
        setCurrentAnalyzingRepo('');
        setAnalysisProgress({
          status: 'error',
          message: 'Taking longer than expected. If it doesn\'t show up in history, please try again.'
        });
      }
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
            <UserIcon size={16} /> {user.username}
          </span>
          <button 
            onClick={() => setIsDarkMode(!isDarkMode)}
            className="action-button"
            title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDarkMode ? <Sun size={16} /> : <Moon size={16} />}
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
          <div className="main-container" style={{ 
            width: '100%', 
            height: '100%', 
            display: 'flex', 
            flexDirection: 'column'
          }}>
            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button 
                className={`tab-button ${activeTab === 'chat' ? 'active' : ''}`}
                onClick={() => setActiveTab('chat')}
              >
                <MessageCircle size={16} /> Chat
              </button>
              <button 
                className={`tab-button ${activeTab === 'changelog' ? 'active' : ''}`}
                onClick={() => setActiveTab('changelog')}
              >
                <GitBranch size={16} /> Generate Changelog
              </button>
              <button 
                className={`tab-button ${activeTab === 'history' ? 'active' : ''}`}
                onClick={() => setActiveTab('history')}
              >
                <History size={16} /> Changelog History
              </button>
            </div>

            {/* Tab Content */}
            <div className="tab-content">
              {activeTab === 'chat' && (
                <ChatInterface 
                  repository={repository}
                  analysisProgress={analysisProgress}
                  isAnalyzing={isAnalyzing}
                  authHeaders={getAuthHeaders}
                  onConnectionStatusChange={setConnectionStatus}
                />
              )}
              {activeTab === 'changelog' && (
                <ChangelogGenerator 
                  repository={repository}
                  authHeaders={getAuthHeaders}
                  fetchWithAuth={fetchWithAuth}
                />
              )}
              {activeTab === 'history' && (
                <ChangelogHistory 
                  repository={repository}
                  authHeaders={getAuthHeaders}
                  fetchWithAuth={fetchWithAuth}
                />
              )}
            </div>
          </div>
        )}
      </div>
      
      {/* Repository History Modal */}
      {showRepoHistory && (
        <RepoHistory
          fetchWithAuth={fetchWithAuth}
          onSelectRepository={handleSelectRepository}
          onClose={() => setShowRepoHistory(false)}
        />
      )}
      
      {/* Progress Dialog */}
      <ProgressDialog
        isOpen={isAnalyzing && currentAnalyzingRepo !== ''}
        repository={currentAnalyzingRepo}
        progress={analysisProgress}
        onCancel={handleCancelAnalysis}
      />
      
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
                setCurrentAnalyzingRepo('');
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
