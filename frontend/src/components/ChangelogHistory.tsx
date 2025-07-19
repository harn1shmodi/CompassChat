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
  Loader2,
  Share2,
  Check,
  Upload,
  Edit,
  Save
} from 'lucide-react';
import './ChangelogHistory.css';

interface ChangelogEntry {
  id: string;
  version: string;
  date: string;
  content: string;
  target_audience: string;
  format: string;
  is_published: boolean;
  metadata: {
    commits_analyzed: number;
    breaking_changes: string[];
    commit_types: { [key: string]: number };
  };
}

interface ChangelogHistoryProps {
  repository: string | null;
  authHeaders?: () => { [key: string]: string };
  fetchWithAuth?: (url: string, options?: RequestInit) => Promise<Response>;
}

export const ChangelogHistory: React.FC<ChangelogHistoryProps> = ({
  repository,
  authHeaders,
  fetchWithAuth
}) => {
  const [history, setHistory] = useState<ChangelogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<ChangelogEntry | null>(null);
  const [publishingVersions, setPublishingVersions] = useState<Set<string>>(new Set());
  const [publishMessage, setPublishMessage] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');

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

  const startEditing = () => {
    if (!selectedEntry) return;
    setEditedContent(selectedEntry.content);
    setIsEditing(true);
  };

  const saveEdits = async () => {
    if (!selectedEntry || !repository) return;

    try {
      const [repoOwner, repoName] = repository.split('/');
      
      const response = fetchWithAuth 
        ? await fetchWithAuth(`/api/changelog/update/${repoOwner}/${repoName}/${selectedEntry.id}`, {
            method: 'PUT',
            body: JSON.stringify({ content: editedContent })
          })
        : await fetch(`/api/changelog/update/${repoOwner}/${repoName}/${selectedEntry.id}`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              ...authHeaders ? authHeaders() : {}
            },
            body: JSON.stringify({ content: editedContent })
          });

      if (response.ok) {
        // Update local state with the new content
        setSelectedEntry({
          ...selectedEntry,
          content: editedContent
        });
        
        // Also update the history list
        setHistory(prevHistory => 
          prevHistory.map(entry => 
            entry.id === selectedEntry.id 
              ? { ...entry, content: editedContent }
              : entry
          )
        );
        
        setIsEditing(false);
        console.log('Changelog updated successfully');
      } else {
        const errorData = await response.json();
        console.error('Failed to update changelog:', errorData);
        // Could show an error toast here
      }
    } catch (error) {
      console.error('Error updating changelog:', error);
      // Could show an error toast here
    }
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setEditedContent('');
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

  const publishChangelog = async (version: string) => {
    if (!repository) return;

    setPublishingVersions(prev => new Set(prev).add(version));
    setPublishMessage(null);

    try {
      const [repoOwner, repoName] = repository.split('/');
      const response = await fetch(`/api/changelog/publish/${repoOwner}/${repoName}/${version}`, {
        method: 'POST',
        headers: authHeaders ? authHeaders() : {}
      });

      if (response.ok) {
        await response.json();
        setPublishMessage(`Successfully published changelog ${version}`);
        
        // Update the local state to reflect the published status
        setHistory(prevHistory => 
          prevHistory.map(entry => 
            entry.version === version 
              ? { ...entry, is_published: true }
              : entry
          )
        );
        
        // Clear success message after 3 seconds
        setTimeout(() => setPublishMessage(null), 3000);
      } else {
        const errorData = await response.json();
        setPublishMessage(`Failed to publish: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error publishing changelog:', error);
      setPublishMessage('An error occurred while publishing the changelog');
    } finally {
      setPublishingVersions(prev => {
        const newSet = new Set(prev);
        newSet.delete(version);
        return newSet;
      });
    }
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
        {publishMessage && (
          <div className={`publish-message ${publishMessage.includes('Successfully') ? 'success' : 'error'}`}>
            {publishMessage.includes('Successfully') ? <Check size={16} /> : <AlertTriangle size={16} />}
            {publishMessage}
          </div>
        )}
      </div>

      <div className={`changelog-history-content ${loading ? 'loading' : ''}`}>
        {loading ? (
          <div className="loading-state">
            <div className="loading-spinner">
              <Loader2 size={32} className="animate-spin" />
              <p>Loading changelog history...</p>
            </div>
          </div>
        ) : error ? (
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
        ) : history.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><FileText size={48} /></div>
            <h3>No Changelog History</h3>
            <p>This repository doesn't have any changelog entries yet.</p>
            <p>Generate your first changelog to get started!</p>
          </div>
        ) : (
          <div className="changelog-entries">
            <div className="entries-list">
              {history.map((entry, index) => (
                <div
                  key={`${entry.version}-${index}`}
                  className={`changelog-entry ${selectedEntry === entry ? 'selected' : ''}`}
                  onClick={() => setSelectedEntry(entry)}
                >
                  <div className="entry-header">
                    <div className="version-info">
                      <div className={`version-badge ${getVersionColor(entry.version)}`}>
                        {entry.version}
                      </div>
                      {entry.is_published && (
                        <div className="published-indicator">
                          <Share2 size={14} /> Published
                        </div>
                      )}
                    </div>
                    <div className="entry-actions">
                      <div className="entry-date">
                        {formatDate(entry.date)}
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          publishChangelog(entry.version);
                        }}
                        disabled={publishingVersions.has(entry.version)}
                        className={`btn btn-sm ${entry.is_published ? 'btn-outline' : 'btn-primary'}`}
                        title={entry.is_published ? 'Update public changelog' : 'Publish to public changelog'}
                      >
                        {publishingVersions.has(entry.version) ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : entry.is_published ? (
                          <Upload size={14} />
                        ) : (
                          <Share2 size={14} />
                        )}
                        {publishingVersions.has(entry.version) 
                          ? 'Publishing...' 
                          : entry.is_published 
                            ? 'Update' 
                            : 'Publish'
                        }
                      </button>
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
                  <div className="details-actions">
                    {isEditing ? (
                      <>
                        <button
                          onClick={saveEdits}
                          className="btn btn-primary btn-sm"
                          title="Save changes"
                        >
                          <Save size={16} /> Save
                        </button>
                        <button
                          onClick={cancelEditing}
                          className="btn btn-outline btn-sm"
                          title="Cancel editing"
                        >
                          <X size={16} /> Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={startEditing}
                          className="btn btn-outline btn-sm"
                          title="Edit changelog"
                        >
                          <Edit size={16} /> Edit
                        </button>
                        <button
                          onClick={() => {
                            setSelectedEntry(null);
                            setIsEditing(false);
                            setEditedContent('');
                          }}
                          className="btn btn-outline btn-sm"
                        >
                          <X size={16} /> Close
                        </button>
                      </>
                    )}
                  </div>
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
                  {isEditing ? (
                    <div className="content-editor">
                      <textarea
                        value={editedContent}
                        onChange={(e) => setEditedContent(e.target.value)}
                        className="content-textarea"
                        rows={20}
                        placeholder="Edit your changelog content..."
                      />
                    </div>
                  ) : (
                    <div className="content-container">
                      {selectedEntry.format === 'markdown' ? (
                        <MarkdownRenderer content={selectedEntry.content} />
                      ) : (
                        <pre className="content-raw">{selectedEntry.content}</pre>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};