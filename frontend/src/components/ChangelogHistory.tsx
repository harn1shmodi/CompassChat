import React, { useState, useEffect } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { 
  History, 
  AlertTriangle, 
  ExternalLink, 
  RefreshCw, 
  FileText, 
  X,
  BarChart3,
  Users,
  Loader2 
} from 'lucide-react';
import './ChangelogHistory.css';

interface ChangelogEntry {
  version: string;
  date: string;
  content: string;
  target_audience: string;
  format: string;
  metadata: {
    commits_analyzed: number;
    breaking_changes: string[];
    commit_types: { [key: string]: number };
  };
}

interface ChangelogHistoryProps {
  repository: string | null;
  authHeaders?: () => { [key: string]: string };
}

export const ChangelogHistory: React.FC<ChangelogHistoryProps> = ({
  repository,
  authHeaders
}) => {
  const [history, setHistory] = useState<ChangelogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<ChangelogEntry | null>(null);

  useEffect(() => {
    if (repository) {
      loadHistory();
    }
  }, [repository]);

  const loadHistory = async () => {
    if (!repository) return;

    setLoading(true);
    setError(null);

    try {
      const [repoOwner, repoName] = repository.split('/');
      const response = await fetch(`/api/changelog/history/${repoOwner}/${repoName}`, {
        headers: authHeaders ? authHeaders() : {}
      });

      if (response.ok) {
        const data = await response.json();
        setHistory(data.history || []);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to load changelog history');
      }
    } catch (error) {
      console.error('Error loading changelog history:', error);
      setError('An error occurred while loading changelog history');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string): string => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch {
      return dateString;
    }
  };

  const getVersionColor = (version: string): string => {
    if (version.includes('beta') || version.includes('alpha')) {
      return 'version-prerelease';
    }
    
    const versionParts = version.replace('v', '').split('.');
    const majorVersion = parseInt(versionParts[0]);
    
    if (majorVersion >= 2) {
      return 'version-major';
    } else if (majorVersion >= 1) {
      return 'version-stable';
    } else {
      return 'version-minor';
    }
  };

  const openPublicChangelog = () => {
    if (!repository) return;
    
    const [repoOwner, repoName] = repository.split('/');
    const publicUrl = `/api/changelog/public/${repoOwner}/${repoName}`;
    window.open(publicUrl, '_blank');
  };

  if (!repository) {
    return (
      <div className="changelog-history-placeholder">
        <div className="placeholder-content">
          <h2><History size={20} /> Changelog History</h2>
          <p>Select a repository to view its changelog history</p>
        </div>
      </div>
    );
  }

  return (
    <div className="changelog-history">
      <div className="changelog-history-header">
        <h2><History size={20} /> Changelog History</h2>
        <p>Past changelog entries for <strong>{repository}</strong></p>
        <div className="header-actions">
          <button
            onClick={openPublicChangelog}
            className="btn btn-outline btn-sm"
          >
            <ExternalLink size={16} /> View Public Changelog
          </button>
          <button
            onClick={loadHistory}
            disabled={loading}
            className="btn btn-secondary btn-sm"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="changelog-history-content">
        {loading && (
          <div className="loading-state">
            <div className="loading-spinner">
              <Loader2 size={40} className="animate-spin" />
              <p>Loading changelog history...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="error-state">
            <div className="error-icon"><AlertTriangle size={32} /></div>
            <div className="error-content">
              <h3>Error Loading History</h3>
              <p>{error}</p>
              <button onClick={loadHistory} className="btn btn-primary btn-sm">
                Try Again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && history.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><FileText size={48} /></div>
            <h3>No Changelog History</h3>
            <p>This repository doesn't have any changelog entries yet.</p>
            <p>Generate your first changelog to get started!</p>
          </div>
        )}

        {!loading && !error && history.length > 0 && (
          <div className="changelog-entries">
            <div className="entries-list">
              {history.map((entry, index) => (
                <div
                  key={`${entry.version}-${index}`}
                  className={`changelog-entry ${selectedEntry === entry ? 'selected' : ''}`}
                  onClick={() => setSelectedEntry(entry)}
                >
                  <div className="entry-header">
                    <div className={`version-badge ${getVersionColor(entry.version)}`}>
                      {entry.version}
                    </div>
                    <div className="entry-date">
                      {formatDate(entry.date)}
                    </div>
                  </div>
                  
                  <div className="entry-meta">
                    <div className="meta-item">
                      <span className="meta-label">Audience:</span>
                      <span className="meta-value">{entry.target_audience}</span>
                    </div>
                    <div className="meta-item">
                      <span className="meta-label">Format:</span>
                      <span className="meta-value">{entry.format}</span>
                    </div>
                    {entry.metadata.commits_analyzed && (
                      <div className="meta-item">
                        <span className="meta-label">Commits:</span>
                        <span className="meta-value">{entry.metadata.commits_analyzed}</span>
                      </div>
                    )}
                  </div>

                  {entry.metadata.breaking_changes && entry.metadata.breaking_changes.length > 0 && (
                    <div className="breaking-changes-indicator">
                      <AlertTriangle size={14} /> {entry.metadata.breaking_changes.length} breaking change(s)
                    </div>
                  )}

                  <div className="entry-preview">
                    {entry.content.split('\n').slice(0, 3).join('\n')}
                    {entry.content.split('\n').length > 3 && '...'}
                  </div>
                </div>
              ))}
            </div>

            {selectedEntry && (
              <div className="entry-details">
                <div className="details-header">
                  <h3>
                    <span className={`version-badge ${getVersionColor(selectedEntry.version)}`}>
                      {selectedEntry.version}
                    </span>
                    {formatDate(selectedEntry.date)}
                  </h3>
                  <button
                    onClick={() => setSelectedEntry(null)}
                    className="btn btn-outline btn-sm"
                  >
                    <X size={16} /> Close
                  </button>
                </div>

                <div className="details-metadata">
                  <div className="metadata-grid">
                    <div className="metadata-item">
                      <strong>Target Audience:</strong> {selectedEntry.target_audience}
                    </div>
                    <div className="metadata-item">
                      <strong>Format:</strong> {selectedEntry.format}
                    </div>
                    {selectedEntry.metadata.commits_analyzed && (
                      <div className="metadata-item">
                        <strong>Commits Analyzed:</strong> {selectedEntry.metadata.commits_analyzed}
                      </div>
                    )}
                  </div>

                  {selectedEntry.metadata.breaking_changes && selectedEntry.metadata.breaking_changes.length > 0 && (
                    <div className="breaking-changes-section">
                      <h4><AlertTriangle size={16} /> Breaking Changes</h4>
                      <ul>
                        {selectedEntry.metadata.breaking_changes.map((change, index) => (
                          <li key={index}>{change}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {selectedEntry.metadata.commit_types && (
                    <div className="commit-types-section">
                      <h4><BarChart3 size={16} /> Commit Types</h4>
                      <div className="commit-types-grid">
                        {Object.entries(selectedEntry.metadata.commit_types).map(([type, count]) => (
                          <div key={type} className="commit-type-item">
                            <span className="commit-type">{type}</span>
                            <span className="commit-count">{count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="details-content">
                  <h4><FileText size={16} /> Content</h4>
                  <div className="content-container">
                    {selectedEntry.format === 'markdown' ? (
                      <MarkdownRenderer content={selectedEntry.content} />
                    ) : (
                      <pre className="content-raw">{selectedEntry.content}</pre>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};