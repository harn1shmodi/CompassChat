import React, { useState, useEffect } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { 
  GitBranch, 
  AlertTriangle, 
  Copy, 
  Download, 
  BarChart3, 
  Users, 
  FileText,
  Edit,
  Save,
  X
} from 'lucide-react';
import './ChangelogGenerator.css';

interface ChangelogTemplate {
  audiences: {
    [key: string]: {
      name: string;
      description: string;
      example: string;
    };
  };
  formats: {
    [key: string]: {
      name: string;
      description: string;
      extension: string;
    };
  };
}

interface ChangelogResult {
  id?: string;
  version: string;
  date: string;
  content: string;
  commits_analyzed: number;
  target_audience: string;
  format: string;
  metadata: {
    breaking_changes: string[];
    commit_types: { [key: string]: number };
    contributors: Array<{
      name: string;
      email: string;
      commits: number;
    }>;
  };
  error?: string;
}

interface ChangelogGeneratorProps {
  repository: string | null;
  authHeaders?: () => { [key: string]: string };
  fetchWithAuth?: (url: string, options?: RequestInit) => Promise<Response>;
}

interface GenerationProgress {
  status: 'starting' | 'cloning' | 'analyzing' | 'generating' | 'complete' | 'error';
  message: string;
  progress?: number;
  estimated_time?: string;
}

export const ChangelogGenerator: React.FC<ChangelogGeneratorProps> = ({
  repository,
  authHeaders,
  fetchWithAuth
}) => {
  const [templates, setTemplates] = useState<ChangelogTemplate | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [changelog, setChangelog] = useState<ChangelogResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const [generationStartTime, setGenerationStartTime] = useState<number | null>(null);
  const [estimatedTimeRemaining, setEstimatedTimeRemaining] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Form state
  const [selectedAudience, setSelectedAudience] = useState('users');
  const [selectedFormat, setSelectedFormat] = useState('markdown');
  const [sinceVersion, setSinceVersion] = useState('');
  const [sinceDate, setSinceDate] = useState('');
  const [customVersion, setCustomVersion] = useState('');
  const [isPreview, setIsPreview] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');

  // Load templates on component mount
  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const response = fetchWithAuth 
        ? await fetchWithAuth('/api/changelog/templates')
        : await fetch('/api/changelog/templates', {
            headers: authHeaders ? authHeaders() : {}
          });
      
      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      } else {
        console.error('Failed to load changelog templates');
      }
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  };

  const generateChangelog = async () => {
    if (!repository) return;

    setIsGenerating(true);
    setError(null);
    setChangelog(null);
    setGenerationProgress({ status: 'starting', message: 'Initializing changelog generation...' });
    setGenerationStartTime(Date.now());
    setEstimatedTimeRemaining(null);

    try {
      const [repoOwner, repoName] = repository.split('/');
      
      const requestBody = {
        repo_owner: repoOwner,
        repo_name: repoName,
        since_version: sinceVersion || null,
        since_date: sinceDate || null,
        target_audience: selectedAudience,
        changelog_format: selectedFormat,
        custom_version: customVersion || null
      };

      const endpoint = isPreview ? '/api/changelog/preview' : '/api/changelog/generate';
      
      // Create AbortController for timeout handling
      const abortController = new AbortController();
      const timeoutId = setTimeout(() => {
        abortController.abort();
      }, 600000); // 10 minutes timeout

      // Start progress tracking
      const progressInterval = setInterval(() => {
        updateProgressEstimate();
      }, 2000);

      setGenerationProgress({ status: 'cloning', message: 'Cloning repository...' });
      
      const response = fetchWithAuth 
        ? await fetchWithAuth(endpoint, {
            method: 'POST',
            body: JSON.stringify(requestBody),
            signal: abortController.signal
          })
        : await fetch(endpoint, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(authHeaders ? authHeaders() : {})
            },
            body: JSON.stringify(requestBody),
            signal: abortController.signal
          });

      clearTimeout(timeoutId);
      clearInterval(progressInterval);

      if (response.ok) {
        setGenerationProgress({ status: 'complete', message: 'Changelog generated successfully!' });
        const result = await response.json();
        if (result.error) {
          setError(result.error);
          setGenerationProgress({ status: 'error', message: result.error });
        } else {
          setChangelog(result);
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        const errorMessage = errorData.detail || 'Failed to generate changelog';
        setError(errorMessage);
        setGenerationProgress({ status: 'error', message: errorMessage });
      }
    } catch (error) {
      console.error('Error generating changelog:', error);
      
      if (error instanceof Error && error.name === 'AbortError') {
        const timeoutMessage = 'Request timed out, but the server may still be processing. Checking for completion...';
        setError(null); // Clear error initially
        setGenerationProgress({ status: 'error', message: timeoutMessage });
        
        // Start polling for completion
        startPollingForCompletion();
      } else {
        const errorMessage = 'An error occurred while generating the changelog';
        setError(errorMessage);
        setGenerationProgress({ status: 'error', message: errorMessage });
      }
    } finally {
      setIsGenerating(false);
      // Clear progress after a delay to show completion/error state
      setTimeout(() => {
        setGenerationProgress(null);
        setGenerationStartTime(null);
        setEstimatedTimeRemaining(null);
      }, 3000);
    }
  };

  const updateProgressEstimate = () => {
    if (!generationStartTime || !isGenerating) return;
    
    const elapsed = Date.now() - generationStartTime;
    
    // Update progress stages based on elapsed time
    if (elapsed < 30000) {
      setGenerationProgress(prev => prev ? { ...prev, status: 'cloning', message: 'Cloning repository...' } : null);
    } else if (elapsed < 120000) {
      setGenerationProgress(prev => prev ? { ...prev, status: 'analyzing', message: 'Analyzing code changes and commit history...' } : null);
    } else {
      setGenerationProgress(prev => prev ? { ...prev, status: 'generating', message: 'Generating changelog content with AI...' } : null);
    }
    
    // Estimate remaining time (rough estimates based on typical generation times)
    if (elapsed < 60000) {
      setEstimatedTimeRemaining('2-4 minutes remaining');
    } else if (elapsed < 180000) {
      setEstimatedTimeRemaining('1-2 minutes remaining');
    } else if (elapsed < 300000) {
      setEstimatedTimeRemaining('Less than 1 minute remaining');
    } else {
      setEstimatedTimeRemaining('Finalizing...');
    }
  };

  const startPollingForCompletion = async () => {
    if (!repository || isPolling) return;
    
    setIsPolling(true);
    setGenerationProgress({ status: 'generating', message: 'Server is still processing. Checking for completion...' });
    
    const [repoOwner, repoName] = repository.split('/');
    const pollInterval = 5000; // Poll every 5 seconds
    const maxPolls = 24; // Poll for up to 2 minutes (24 * 5s = 120s)
    let pollCount = 0;
    
    const poll = async () => {
      try {
        // Check changelog history for recent completion
        const historyResponse = fetchWithAuth 
          ? await fetchWithAuth(`/api/changelog/history/${repoOwner}/${repoName}?limit=1`)
          : await fetch(`/api/changelog/history/${repoOwner}/${repoName}?limit=1`, {
              headers: authHeaders ? authHeaders() : {}
            });
        
        if (historyResponse.ok) {
          const historyData = await historyResponse.json();
          const recentChangelogs = historyData.changelogs || [];
          
          if (recentChangelogs.length > 0) {
            const latestChangelog = recentChangelogs[0];
            const changelogTime = new Date(latestChangelog.created_at).getTime();
            const generationTime = generationStartTime || Date.now();
            
            // If the latest changelog was created after we started generation (within 30 seconds buffer)
            if (changelogTime > generationTime - 30000) {
              setChangelog({
                id: latestChangelog.id,
                version: latestChangelog.version,
                date: latestChangelog.created_at,
                content: latestChangelog.content,
                commits_analyzed: latestChangelog.commits_analyzed || 0,
                target_audience: latestChangelog.target_audience,
                format: latestChangelog.format,
                metadata: latestChangelog.metadata || { breaking_changes: [], commit_types: {}, contributors: [] }
              });
              
              setGenerationProgress({ status: 'complete', message: 'Changelog found! Generation completed successfully.' });
              setIsPolling(false);
              setIsGenerating(false);
              
              // Clear progress after showing success
              setTimeout(() => {
                setGenerationProgress(null);
                setGenerationStartTime(null);
                setEstimatedTimeRemaining(null);
              }, 3000);
              
              return; // Stop polling
            }
          }
        }
        
        pollCount++;
        if (pollCount >= maxPolls) {
          // Polling timeout
          setError('Server is taking longer than expected. Please check the changelog history tab in a few minutes.');
          setGenerationProgress({ status: 'error', message: 'Polling timed out. Check changelog history later.' });
          setIsPolling(false);
        } else {
          // Continue polling
          setTimeout(poll, pollInterval);
        }
        
      } catch (error) {
        console.error('Polling error:', error);
        pollCount++;
        if (pollCount >= maxPolls) {
          setError('Unable to check completion status. Please check the changelog history tab.');
          setGenerationProgress({ status: 'error', message: 'Unable to verify completion.' });
          setIsPolling(false);
        } else {
          setTimeout(poll, pollInterval);
        }
      }
    };
    
    // Start polling after a short delay
    setTimeout(poll, 2000);
  };

  const downloadChangelog = () => {
    if (!changelog) return;

    const extension = templates?.formats[selectedFormat]?.extension || '.txt';
    const fileName = `changelog-${changelog.version}${extension}`;
    
    const content = isEditing ? editedContent : changelog.content;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const startEditing = () => {
    if (!changelog) return;
    setEditedContent(changelog.content);
    setIsEditing(true);
  };

  const saveEdits = async () => {
    if (!changelog || !repository) return;

    // If we have an ID, this changelog is stored in the database and we can update it
    if (changelog.id) {
      try {
        const [repoOwner, repoName] = repository.split('/');
        
        const response = fetchWithAuth 
          ? await fetchWithAuth(`/api/changelog/update/${repoOwner}/${repoName}/${changelog.id}`, {
              method: 'PUT',
              body: JSON.stringify({ content: editedContent })
            })
          : await fetch(`/api/changelog/update/${repoOwner}/${repoName}/${changelog.id}`, {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
                ...authHeaders ? authHeaders() : {}
              },
              body: JSON.stringify({ content: editedContent })
            });

        if (response.ok) {
          // Update local state with the new content
          setChangelog({
            ...changelog,
            content: editedContent
          });
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
    } else {
      // No ID means this is a preview or unsaved changelog, just update locally
      setChangelog({
        ...changelog,
        content: editedContent
      });
      setIsEditing(false);
    }
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setEditedContent('');
  };

  const copyToClipboard = () => {
    if (!changelog) return;

    const content = isEditing ? editedContent : changelog.content;
    navigator.clipboard.writeText(content).then(() => {
      // Could show a toast notification here
      console.log('Changelog copied to clipboard');
    }).catch(err => {
      console.error('Failed to copy to clipboard:', err);
    });
  };

  if (!repository) {
    return (
      <div className="changelog-generator-placeholder">
        <div className="placeholder-content">
          <h2>Changelog Generator</h2>
          <p>Select a repository to generate AI-powered changelogs</p>
        </div>
      </div>
    );
  }

  return (
    <div className="changelog-generator">
      <div className="changelog-header">
        <h2><GitBranch className="inline-icon" size={20} /> Changelog Generator</h2>
        <p>Generate AI-powered changelogs for <strong>{repository}</strong></p>
      </div>

      <div className="changelog-content">
        <div className="changelog-form">
          <div className="form-section">
            <h3>Configuration</h3>
            
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="audience">Target Audience</label>
                <select
                  id="audience"
                  value={selectedAudience}
                  onChange={(e) => setSelectedAudience(e.target.value)}
                  className="form-select"
                >
                  {templates?.audiences && Object.entries(templates.audiences).map(([key, audience]) => (
                    <option key={key} value={key}>
                      {audience.name}
                    </option>
                  ))}
                </select>
                {templates?.audiences[selectedAudience] && (
                  <p className="form-help">
                    {templates.audiences[selectedAudience].description}
                  </p>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="format">Format</label>
                <select
                  id="format"
                  value={selectedFormat}
                  onChange={(e) => setSelectedFormat(e.target.value)}
                  className="form-select"
                >
                  {templates?.formats && Object.entries(templates.formats).map(([key, format]) => (
                    <option key={key} value={key}>
                      {format.name}
                    </option>
                  ))}
                </select>
                {templates?.formats[selectedFormat] && (
                  <p className="form-help">
                    {templates.formats[selectedFormat].description}
                  </p>
                )}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="sinceVersion">Since Version (Optional)</label>
                <input
                  type="text"
                  id="sinceVersion"
                  value={sinceVersion}
                  onChange={(e) => setSinceVersion(e.target.value)}
                  placeholder="e.g., v1.0.0"
                  className="form-input"
                />
                <p className="form-help">
                  Generate changelog since this version tag
                </p>
              </div>

              <div className="form-group">
                <label htmlFor="sinceDate">Since Date (Optional)</label>
                <input
                  type="date"
                  id="sinceDate"
                  value={sinceDate}
                  onChange={(e) => setSinceDate(e.target.value)}
                  className="form-input"
                />
                <p className="form-help">
                  Generate changelog since this date
                </p>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="customVersion">New Version (Optional)</label>
                <input
                  type="text"
                  id="customVersion"
                  value={customVersion}
                  onChange={(e) => setCustomVersion(e.target.value)}
                  placeholder="e.g., v2.1.0"
                  className="form-input"
                />
                <p className="form-help">
                  Override auto-generated version number
                </p>
              </div>
            </div>

            <div className="form-actions">
              <button
                onClick={() => { setIsPreview(true); generateChangelog(); }}
                disabled={isGenerating}
                className="btn btn-secondary"
              >
                {isGenerating && isPreview ? 'Generating Preview...' : 'Preview'}
              </button>
              
              <button
                onClick={() => { setIsPreview(false); generateChangelog(); }}
                disabled={isGenerating}
                className="btn btn-primary"
              >
                {isGenerating && !isPreview ? 'Generating...' : 'Generate Changelog'}
              </button>
            </div>

            {/* Progress Indicator */}
            {isGenerating && generationProgress && (
              <div className="generation-progress">
                <div className="progress-content">
                  <div className="progress-header">
                    <h4>Generating Changelog</h4>
                    {estimatedTimeRemaining && (
                      <span className="time-estimate">{estimatedTimeRemaining}</span>
                    )}
                  </div>
                  
                  <div className="progress-bar-container">
                    <div className="progress-bar">
                      <div 
                        className={`progress-fill progress-${generationProgress.status}`}
                        style={{
                          width: generationProgress.status === 'starting' ? '10%' :
                                 generationProgress.status === 'cloning' ? '25%' :
                                 generationProgress.status === 'analyzing' ? '60%' :
                                 generationProgress.status === 'generating' ? '85%' :
                                 generationProgress.status === 'complete' ? '100%' : '0%'
                        }}
                      />
                    </div>
                  </div>
                  
                  <div className="progress-status">
                    <span className="status-icon">
                      {generationProgress.status === 'starting' && '🚀'}
                      {generationProgress.status === 'cloning' && '📥'}
                      {generationProgress.status === 'analyzing' && '🔍'}
                      {generationProgress.status === 'generating' && (isPolling ? '🔄' : '✨')}
                      {generationProgress.status === 'complete' && '✅'}
                      {generationProgress.status === 'error' && '❌'}
                    </span>
                    <span className="status-message">{generationProgress.message}</span>
                    {isPolling && (
                      <span className="polling-indicator">
                        <span className="polling-dots">⏳ Checking...</span>
                      </span>
                    )}
                  </div>

                  {generationProgress.status === 'error' && !isPolling && (
                    <div className="progress-error">
                      <p>The server may still be working on your request in the background. You can:</p>
                      <ul>
                        <li>Wait a few more minutes and try refreshing the page</li>
                        <li>Check the changelog history tab later</li>
                        <li>Try again with a smaller date range</li>
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {templates?.audiences[selectedAudience] && (
            <div className="form-section">
              <h3>Example Output</h3>
              <div className="example-output">
                <p>{templates.audiences[selectedAudience].example}</p>
              </div>
            </div>
          )}
        </div>

        {error && !isGenerating && (
          <div className="changelog-error">
            <div className="error-icon"><AlertTriangle size={24} /></div>
            <div className="error-content">
              <h3>Error</h3>
              <p>{error}</p>
              <div className="error-actions">
                <button 
                  onClick={() => setError(null)}
                  className="btn btn-sm btn-outline"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        )}

        {changelog && (
          <div className="changelog-result">
            <div className="result-header">
              <h3>
                {isPreview && <span className="preview-badge">Preview</span>}
                {changelog.version}
              </h3>
              <div className="result-actions">
                {isEditing ? (
                  <>
                    <button
                      onClick={saveEdits}
                      className="btn btn-sm btn-primary"
                      title="Save changes"
                    >
                      <Save size={16} /> Save
                    </button>
                    <button
                      onClick={cancelEditing}
                      className="btn btn-sm btn-outline"
                      title="Cancel editing"
                    >
                      <X size={16} /> Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={startEditing}
                      className="btn btn-sm btn-outline"
                      title="Edit changelog"
                    >
                      <Edit size={16} /> Edit
                    </button>
                    <button
                      onClick={copyToClipboard}
                      className="btn btn-sm btn-outline"
                      title="Copy to clipboard"
                    >
                      <Copy size={16} /> Copy
                    </button>
                    <button
                      onClick={downloadChangelog}
                      className="btn btn-sm btn-outline"
                      title="Download file"
                    >
                      <Download size={16} /> Download
                    </button>
                  </>
                )}
              </div>
            </div>

            <div className="result-metadata">
              <div className="metadata-item">
                <strong>Date:</strong> {new Date(changelog.date).toLocaleDateString()}
              </div>
              <div className="metadata-item">
                <strong>Commits Analyzed:</strong> {changelog.commits_analyzed}
              </div>
              <div className="metadata-item">
                <strong>Audience:</strong> {changelog.target_audience}
              </div>
              <div className="metadata-item">
                <strong>Format:</strong> {changelog.format}
              </div>
            </div>

            {changelog.metadata.breaking_changes.length > 0 && (
              <div className="breaking-changes">
                <h4><AlertTriangle size={16} /> Breaking Changes</h4>
                <ul>
                  {changelog.metadata.breaking_changes.map((change, index) => (
                    <li key={index}>{change}</li>
                  ))}
                </ul>
              </div>
            )}

            {changelog.metadata.commit_types && (
              <div className="commit-stats">
                <h4><BarChart3 size={16} /> Commit Types</h4>
                <div className="commit-type-grid">
                  {Object.entries(changelog.metadata.commit_types).map(([type, count]) => (
                    <div key={type} className="commit-type-item">
                      <span className="commit-type">{type}</span>
                      <span className="commit-count">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {changelog.metadata.contributors && (
              <div className="contributors">
                <h4><Users size={16} /> Contributors</h4>
                <div className="contributor-list">
                  {changelog.metadata.contributors.slice(0, 5).map((contributor, index) => (
                    <div key={index} className="contributor-item">
                      <span className="contributor-name">{contributor.name}</span>
                      <span className="contributor-commits">{contributor.commits} commits</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="changelog-content-container">
              <h4><FileText size={16} /> Changelog Content</h4>
              {isEditing ? (
                <div className="changelog-editor">
                  <textarea
                    value={editedContent}
                    onChange={(e) => setEditedContent(e.target.value)}
                    className="changelog-textarea"
                    rows={20}
                    placeholder="Edit your changelog content..."
                  />
                </div>
              ) : (
                <div className="changelog-preview">
                  {changelog.format === 'markdown' ? (
                    <MarkdownRenderer content={changelog.content} />
                  ) : (
                    <pre className="changelog-raw">{changelog.content}</pre>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};