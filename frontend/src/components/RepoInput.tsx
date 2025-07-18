import React, { useState } from 'react';
import './RepoInput.css';

interface RepoInputProps {
  onAnalyze: (url: string) => void;
  isAnalyzing: boolean;
  onShowHistory?: () => void;
}

export const RepoInput: React.FC<RepoInputProps> = ({ onAnalyze, isAnalyzing, onShowHistory }) => {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!url.trim()) {
      setError('Please enter a GitHub repository URL');
      return;
    }

    // Basic GitHub URL validation
    const githubUrlPattern = /^https:\/\/github\.com\/[\w\-\.]+\/[\w\-\.]+\/?$/;
    if (!githubUrlPattern.test(url.trim())) {
      setError('Please enter a valid GitHub repository URL (e.g., https://github.com/owner/repo)');
      return;
    }

    onAnalyze(url.trim());
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUrl(e.target.value);
    if (error) setError('');
  };

  return (
    <div className="repo-input-container">
      <div className="repo-input-card">
        <h2>Analyze GitHub Repository</h2>
        <p>Enter a public GitHub repository URL to start chatting with the code</p>
        
        <form onSubmit={handleSubmit} className="repo-form">
          <div className="input-group">
            <input
              type="url"
              value={url}
              onChange={handleInputChange}
              placeholder="https://github.com/owner/repository"
              className={`repo-url-input ${error ? 'error' : ''}`}
              disabled={isAnalyzing}
            />
            <button
              type="submit"
              disabled={isAnalyzing || !url.trim()}
              className="analyze-button"
            >
              {isAnalyzing ? 'Analyzing...' : 'Analyze Repository'}
            </button>
          </div>
          
          {error && <div className="error-message">{error}</div>}
        </form>
        
        {onShowHistory && (
          <div className="history-section">
            <button 
              onClick={onShowHistory}
              className="history-button"
              title="View previous repositories"
            >
              📚 View Repository History
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
