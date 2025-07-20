import React from 'react';
import { CodeSnippet } from './CodeSnippet';
import './MarkdownRenderer.css';

interface MarkdownRendererProps {
  content: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  const renderContent = () => {
    // Split content by code blocks
    const parts = content.split(/(```[\s\S]*?```)/g);
    
    return parts.map((part, index) => {
      // Check if this part is a code block
      if (part.startsWith('```') && part.endsWith('```')) {
        // Extract language and code
        const lines = part.slice(3, -3).split('\n');
        const language = lines[0].trim() || 'text';
        const code = lines.slice(1).join('\n');
        
        return (
          <CodeSnippet
            key={index}
            code={code}
            language={language}
            showLineNumbers={true}
          />
        );
      } else {
        // Regular text content - apply basic markdown formatting
        let formattedText = part;
        
        // Headers (h1-h6)
        formattedText = formattedText.replace(/^### (.*$)/gm, '<h3>$1</h3>');
        formattedText = formattedText.replace(/^## (.*$)/gm, '<h2>$1</h2>');
        formattedText = formattedText.replace(/^# (.*$)/gm, '<h1>$1</h1>');
        formattedText = formattedText.replace(/^#### (.*$)/gm, '<h4>$1</h4>');
        formattedText = formattedText.replace(/^##### (.*$)/gm, '<h5>$1</h5>');
        formattedText = formattedText.replace(/^###### (.*$)/gm, '<h6>$1</h6>');
        
        // Bold text
        formattedText = formattedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Italic text
        formattedText = formattedText.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Inline code
        formattedText = formattedText.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
        
        // Lists - handle unordered lists (lines starting with - or *)
        formattedText = formattedText.replace(/^[\s]*[-*]\s(.+)$/gm, '<li>$1</li>');
        
        // Wrap consecutive list items in ul tags
        formattedText = formattedText.replace(/(<li>.*<\/li>(\n|<br \/>)*)+/g, (match) => {
          const cleanMatch = match.replace(/<br \/>/g, '');
          return `<ul>${cleanMatch}</ul>`;
        });
        
        // Ordered lists (lines starting with numbers)
        formattedText = formattedText.replace(/^[\s]*\d+\.\s(.+)$/gm, '<li>$1</li>');
        
        // Line breaks - convert double newlines to paragraphs, single newlines to br
        formattedText = formattedText.replace(/\n\n+/g, '</p><p>');
        formattedText = formattedText.replace(/\n/g, '<br />');
        formattedText = '<p>' + formattedText + '</p>';
        
        // Clean up empty paragraphs and fix nested paragraph issues
        formattedText = formattedText.replace(/<p><\/p>/g, '');
        formattedText = formattedText.replace(/<p><br \/>/g, '<p>');
        formattedText = formattedText.replace(/<br \/><\/p>/g, '</p>');
        formattedText = formattedText.replace(/<p><ul>/g, '<ul>');
        formattedText = formattedText.replace(/<\/ul><\/p>/g, '</ul>');
        
        return (
          <div 
            key={index} 
            dangerouslySetInnerHTML={{ __html: formattedText }}
          />
        );
      }
    });
  };

  return <div className="markdown-content">{renderContent()}</div>;
};
