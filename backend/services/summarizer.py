from openai import OpenAI
from core.config import settings
from services.embedding_cache import embedding_cache
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CodeSummarizer:
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"  # Light model for summarization
    
    def summarize_chunk(self, chunk: Dict[str, Any]) -> str:
        """Generate a summary for a code chunk with caching"""
        try:
            content = chunk.get('content', '')
            
            # Check cache first
            cached_summary = embedding_cache.get_summary(content)
            if cached_summary:
                return cached_summary
            
            chunk_type = chunk.get('type', 'code')
            file_path = chunk.get('file_path', '')
            language = chunk.get('language', '')
            name = chunk.get('name', '')
            
            # Create context-aware prompt based on chunk type
            if chunk_type == 'function':
                prompt = self._create_function_summary_prompt(chunk)
            elif chunk_type == 'class':
                prompt = self._create_class_summary_prompt(chunk)
            else:
                prompt = self._create_general_summary_prompt(chunk)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code analysis expert. Provide concise, technical summaries of code chunks that capture their purpose, functionality, and key implementation details."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            summary = response.choices[0].message.content.strip()
            
            # Cache the summary
            embedding_cache.set_summary(content, summary)
            
            logger.debug(f"Generated summary for {name} in {file_path}")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary for chunk {chunk.get('id', 'unknown')}: {e}")
            return self._fallback_summary(chunk)
    
    def _create_function_summary_prompt(self, chunk: Dict[str, Any]) -> str:
        """Create a summary prompt for a function"""
        name = chunk.get('name', 'unknown')
        content = chunk.get('content', '')
        file_path = chunk.get('file_path', '')
        parameters = chunk.get('parameters', [])
        docstring = chunk.get('docstring', '')
        
        prompt = f"""Analyze this {chunk.get('language', '')} function and provide a concise summary:

Function: {name}
File: {file_path}
Parameters: {', '.join(parameters) if parameters else 'None'}

{f"Docstring: {docstring}" if docstring else ""}

Code:
```{chunk.get('language', '')}
{content}
```

Provide a 1-2 sentence summary describing what this function does, its purpose, and any notable implementation details."""
        
        return prompt
    
    def _create_class_summary_prompt(self, chunk: Dict[str, Any]) -> str:
        """Create a summary prompt for a class"""
        name = chunk.get('name', 'unknown')
        content = chunk.get('content', '')
        file_path = chunk.get('file_path', '')
        methods = chunk.get('methods', [])
        docstring = chunk.get('docstring', '')
        
        prompt = f"""Analyze this {chunk.get('language', '')} class and provide a concise summary:

Class: {name}
File: {file_path}
Methods: {', '.join(methods) if methods else 'None'}

{f"Docstring: {docstring}" if docstring else ""}

Code:
```{chunk.get('language', '')}
{content}
```

Provide a 1-2 sentence summary describing the purpose of this class, its main responsibilities, and key methods."""
        
        return prompt
    
    def _create_general_summary_prompt(self, chunk: Dict[str, Any]) -> str:
        """Create a summary prompt for general code chunks"""
        content = chunk.get('content', '')
        file_path = chunk.get('file_path', '')
        
        prompt = f"""Analyze this {chunk.get('language', '')} code segment and provide a concise summary:

File: {file_path}
Type: {chunk.get('type', 'code segment')}

Code:
```{chunk.get('language', '')}
{content}
```

Provide a 1-2 sentence summary describing what this code does and its purpose."""
        
        return prompt
    
    def _fallback_summary(self, chunk: Dict[str, Any]) -> str:
        """Generate a fallback summary when API fails"""
        chunk_type = chunk.get('type', 'code')
        name = chunk.get('name', 'unknown')
        file_path = chunk.get('file_path', '')
        language = chunk.get('language', '')
        
        if chunk_type == 'function':
            return f"Function '{name}' in {file_path} ({language})"
        elif chunk_type == 'class':
            return f"Class '{name}' in {file_path} ({language})"
        else:
            return f"Code segment in {file_path} ({language})"
    
    def summarize_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 5) -> List[Dict[str, Any]]:
        """Generate summaries for multiple chunks using batch processing"""
        summarized_chunks = []
        
        # Process chunks in batches for efficiency
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            try:
                batch_summaries = self._batch_summarize(batch)
                
                for chunk, summary in zip(batch, batch_summaries):
                    chunk['summary'] = summary
                    summarized_chunks.append(chunk)
                    
            except Exception as e:
                logger.error(f"Failed to summarize batch {i//batch_size + 1}: {e}")
                # Add chunks with fallback summaries
                for chunk in batch:
                    chunk['summary'] = self._fallback_summary(chunk)
                    summarized_chunks.append(chunk)
        
        logger.info(f"Summarized {len(summarized_chunks)} chunks")
        return summarized_chunks
    
    def _batch_summarize(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """Summarize multiple chunks in a single API call"""
        try:
            # Create batch prompt
            batch_prompt = "Analyze these code chunks and provide a concise summary for each:\n\n"
            
            for i, chunk in enumerate(chunks, 1):
                chunk_type = chunk.get('type', 'code')
                content = chunk.get('content', '')[:800]  # Limit content length
                file_path = chunk.get('file_path', '')
                name = chunk.get('name', 'unknown')
                language = chunk.get('language', '')
                
                batch_prompt += f"CHUNK {i}:\n"
                batch_prompt += f"Type: {chunk_type}\n"
                batch_prompt += f"Name: {name}\n"
                batch_prompt += f"File: {file_path}\n"
                batch_prompt += f"Language: {language}\n"
                batch_prompt += f"Code:\n```{language}\n{content}\n```\n\n"
            
            batch_prompt += f"Provide exactly {len(chunks)} summaries, one per chunk, formatted as:\n"
            batch_prompt += "SUMMARY 1: [1-2 sentence description]\n"
            batch_prompt += "SUMMARY 2: [1-2 sentence description]\n"
            batch_prompt += "etc.\n"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code analysis expert. Provide concise, technical summaries that capture purpose, functionality, and key implementation details."
                    },
                    {
                        "role": "user", 
                        "content": batch_prompt
                    }
                ],
                max_tokens=300 * len(chunks),  # Scale with batch size
                temperature=0.1
            )
            
            # Parse batch response
            return self._parse_batch_summaries(response.choices[0].message.content, len(chunks))
            
        except Exception as e:
            logger.error(f"Error in batch summarization: {e}")
            # Fallback to individual summarization
            return [self.summarize_chunk(chunk) for chunk in chunks]
    
    def _parse_batch_summaries(self, batch_response: str, expected_count: int) -> List[str]:
        """Parse batch summarization response"""
        summaries = []
        lines = batch_response.strip().split('\n')
        
        for line in lines:
            if line.startswith('SUMMARY ') and ':' in line:
                summary = line.split(':', 1)[1].strip()
                summaries.append(summary)
        
        # Ensure we have the expected number of summaries
        while len(summaries) < expected_count:
            summaries.append("Code component analysis")
        
        return summaries[:expected_count]
