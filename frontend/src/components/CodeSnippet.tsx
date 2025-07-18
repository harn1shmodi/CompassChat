import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import './CodeSnippet.css';

interface CodeSnippetProps {
  code: string;
  language: string;
  fileName?: string;
  showLineNumbers?: boolean;
}

export const CodeSnippet: React.FC<CodeSnippetProps> = ({
  code,
  language,
  fileName,
  showLineNumbers = true
}) => {
  const [copied, setCopied] = useState(false);

  const normalizeLanguage = (lang: string): string => {
    // Map common language variations to react-syntax-highlighter supported languages
    const languageMap: { [key: string]: string } = {
      'ts': 'typescript',
      'tsx': 'tsx',
      'js': 'javascript',
      'jsx': 'jsx',
      'py': 'python',
      'cpp': 'cpp',
      'c++': 'cpp',
      'cxx': 'cpp',
      'cc': 'cpp',
      'h': 'c',
      'hpp': 'cpp',
      'java': 'java',
      'json': 'json',
      'yaml': 'yaml',
      'yml': 'yaml',
      'xml': 'xml',
      'html': 'markup',
      'css': 'css',
      'scss': 'scss',
      'bash': 'bash',
      'sh': 'bash',
      'zsh': 'bash',
      'sql': 'sql',
      'md': 'markdown',
      'markdown': 'markdown'
    };

    const normalizedLang = lang.toLowerCase().trim();
    return languageMap[normalizedLang] || normalizedLang || 'text';
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code: ', err);
    }
  };

  return (
    <div className="code-snippet">
      {fileName && (
        <div className="code-header">
          <span className="file-name">{fileName}</span>
          <button 
            onClick={copyToClipboard} 
            className={`copy-button ${copied ? 'copied' : ''}`} 
            title={copied ? 'Copied!' : 'Copy code'}
          >
            {copied ? '✓' : '📋'}
          </button>
        </div>
      )}
      
      <div className="code-container">
        <SyntaxHighlighter
          language={normalizeLanguage(language)}
          style={oneDark}
          showLineNumbers={showLineNumbers}
          customStyle={{
            margin: 0,
            borderRadius: fileName ? '0 0 8px 8px' : '8px',
            fontSize: '14px',
            lineHeight: '1.5'
          }}
          codeTagProps={{
            style: {
              fontSize: '14px',
              fontFamily: '"Fira Code", "Monaco", "Menlo", "Ubuntu Mono", monospace'
            }
          }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
};
