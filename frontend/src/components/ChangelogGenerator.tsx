import React, { useState, useEffect } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { 
  GitBranch, 
  AlertTriangle, 
  Copy, 
  Download, 
  BarChart3, 
  Users, 
  FileText
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

export const ChangelogGenerator: React.FC<ChangelogGeneratorProps> = ({
  repository,
  authHeaders,
  fetchWithAuth
}) => {
  const [templates, setTemplates] = useState<ChangelogTemplate | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [changelog, setChangelog] = useState<ChangelogResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [selectedAudience, setSelectedAudience] = useState('users');
  const [selectedFormat, setSelectedFormat] = useState('markdown');
  const [sinceVersion, setSinceVersion] = useState('');
  const [sinceDate, setSinceDate] = useState('');
  const [isPreview, setIsPreview] = useState(false);

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

    try {
      const [repoOwner, repoName] = repository.split('/');
      
      const requestBody = {
        repo_owner: repoOwner,
        repo_name: repoName,
        since_version: sinceVersion || null,
        since_date: sinceDate || null,
        target_audience: selectedAudience,
        changelog_format: selectedFormat
      };

      const endpoint = isPreview ? '/api/changelog/preview' : '/api/changelog/generate';
      
      const response = fetchWithAuth 
        ? await fetchWithAuth(endpoint, {
            method: 'POST',
            body: JSON.stringify(requestBody)
          })
        : await fetch(endpoint, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(authHeaders ? authHeaders() : {})
            },
            body: JSON.stringify(requestBody)
          });

      if (response.ok) {
        const result = await response.json();
        if (result.error) {
          setError(result.error);
        } else {
          setChangelog(result);
        }
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to generate changelog');
      }
    } catch (error) {
      console.error('Error generating changelog:', error);
      setError('An error occurred while generating the changelog');
    } finally {
      setIsGenerating(false);
    }
  };

  const downloadChangelog = () => {
    if (!changelog) return;

    const extension = templates?.formats[selectedFormat]?.extension || '.txt';
    const fileName = `changelog-${changelog.version}${extension}`;
    
    const blob = new Blob([changelog.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    if (!changelog) return;

    navigator.clipboard.writeText(changelog.content).then(() => {
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

        {error && (
          <div className="changelog-error">
            <div className="error-icon"><AlertTriangle size={24} /></div>
            <div className="error-content">
              <h3>Error</h3>
              <p>{error}</p>
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
              <div className="changelog-preview">
                {changelog.format === 'markdown' ? (
                  <MarkdownRenderer content={changelog.content} />
                ) : (
                  <pre className="changelog-raw">{changelog.content}</pre>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};