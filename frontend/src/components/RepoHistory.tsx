import React, { useState, useEffect } from 'react';
import './RepoHistory.css';

interface Repository {
  id: string;
  name: string;
  url: string;
  last_analyzed: string;
  total_files: number;
  total_chunks: number;
}

interface RepoHistoryProps {
  authHeaders: () => { [key: string]: string };
  onSelectRepository: (repoName: string) => void;
  onClose: () => void;
}

export const RepoHistory: React.FC<RepoHistoryProps> = ({
  authHeaders,
  onSelectRepository,
  onClose
}) => {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRepositories();
  }, []);

  const fetchRepositories = async () => {
    try {
      setLoading(true);
      setError(null);
      
      console.log('Fetching user repositories...');
      const response = await fetch('/api/repos/user', {
        headers: authHeaders(),
      });

      console.log('Response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('API Error:', errorText);
        throw new Error(`Failed to fetch repositories: ${response.status} ${errorText}`);
      }

      const data = await response.json();
      console.log('Repository data received:', data);
      
      setRepositories(data.repositories || []);
    } catch (err) {
      console.error('Error fetching repositories:', err);
      setError(err instanceof Error ? err.message : 'Failed to load repositories');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return 'Unknown';
    }
  };

  const extractRepoName = (url: string) => {
    const match = url.match(/github\.com\/([^\/]+\/[^\/]+)/);
    return match ? match[1] : url;
  };

  if (loading) {
    return (
      <div className="repo-history-overlay">
        <div className="repo-history-modal">
          <div className="repo-history-header">
            <h2>Your Repositories</h2>
            <button onClick={onClose} className="close-button">×</button>
          </div>
          <div className="repo-history-content">
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading repositories...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="repo-history-overlay">
        <div className="repo-history-modal">
          <div className="repo-history-header">
            <h2>Your Repositories</h2>
            <button onClick={onClose} className="close-button">×</button>
          </div>
          <div className="repo-history-content">
            <div className="error-state">
              <p>Error: {error}</p>
              <button onClick={fetchRepositories} className="retry-button">
                Try Again
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="repo-history-overlay">
      <div className="repo-history-modal">
        <div className="repo-history-header">
          <h2>Your Repositories</h2>
          <button onClick={onClose} className="close-button">×</button>
        </div>
        <div className="repo-history-content">
          {repositories.length === 0 ? (
            <div className="empty-state">
              <p>No repositories found in your history.</p>
              <p>This might happen if:</p>
              <ul style={{ textAlign: 'left', marginTop: '1rem' }}>
                <li>You're a new user who hasn't analyzed any repositories yet</li>
                <li>You're an existing user from before the history feature was added</li>
                <li>The repositories you analyzed haven't finished processing</li>
              </ul>
              <button onClick={fetchRepositories} className="retry-button" style={{ marginTop: '1rem' }}>
                Refresh History
              </button>
            </div>
          ) : (
            <div className="repo-list">
              {repositories.map((repo) => (
                <div
                  key={repo.id}
                  className="repo-item"
                  onClick={() => {
                    const repoName = extractRepoName(repo.url);
                    onSelectRepository(repoName);
                    onClose();
                  }}
                >
                  <div className="repo-info">
                    <h3 className="repo-name">{extractRepoName(repo.url)}</h3>
                    <p className="repo-url">{repo.url}</p>
                    <div className="repo-stats">
                      <span className="stat">
                        📁 {repo.total_files} files
                      </span>
                      <span className="stat">
                        🧩 {repo.total_chunks} chunks
                      </span>
                      <span className="stat">
                        📅 {formatDate(repo.last_analyzed)}
                      </span>
                    </div>
                  </div>
                  <div className="repo-action">
                    <span className="select-hint">Click to chat →</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
