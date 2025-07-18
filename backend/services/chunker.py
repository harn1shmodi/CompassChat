try:
    from llama_index.core.node_parser import CodeSplitter
    from llama_index.core.schema import Document, TextNode
    LLAMA_INDEX_AVAILABLE = True
except ImportError:
    print("LlamaIndex not available, using fallback implementation")
    LLAMA_INDEX_AVAILABLE = False

from typing import List, Dict, Any
import hashlib
import logging
import re

logger = logging.getLogger(__name__)


class SimpleCodeSplitter:
    """Fallback code splitter when LlamaIndex is not available"""
    def __init__(self, chunk_lines=50, chunk_lines_overlap=5, max_chars=2000):
        self.chunk_lines = chunk_lines
        self.chunk_lines_overlap = chunk_lines_overlap
        self.max_chars = max_chars
    
    def split_text(self, text: str) -> List[str]:
        """Split text into chunks"""
        lines = text.split('\n')
        chunks = []
        
        i = 0
        while i < len(lines):
            # Get chunk lines
            end_line = min(i + self.chunk_lines, len(lines))
            chunk_lines = lines[i:end_line]
            chunk_text = '\n'.join(chunk_lines)
            
            # Check character limit
            if len(chunk_text) > self.max_chars:
                # Split by characters if too long
                chunk_text = chunk_text[:self.max_chars]
            
            chunks.append(chunk_text)
            
            # Move forward with overlap
            i += max(1, self.chunk_lines - self.chunk_lines_overlap)
        
        return chunks


class CodeChunker:
    def __init__(self):
        if LLAMA_INDEX_AVAILABLE:
            self.splitter = CodeSplitter(
                language="python",  # Default, will be changed per file
                chunk_lines=50,     # Lines per chunk
                chunk_lines_overlap=5,  # Overlap between chunks
                max_chars=2000      # Maximum characters per chunk
            )
            self.use_llamaindex = True
            logger.info("Using LlamaIndex CodeSplitter")
        else:
            self.splitter = SimpleCodeSplitter(
                chunk_lines=50,
                chunk_lines_overlap=5,
                max_chars=2000
            )
            self.use_llamaindex = False
            logger.info("Using fallback SimpleCodeSplitter")
    
    def chunk_file(self, ast_info: Dict[str, Any], repo_root: str = None) -> List[Dict[str, Any]]:
        """Chunk a file into semantic segments"""
        chunks = []
        file_path = ast_info['file_path']  # This is now already normalized
        content = ast_info['content']
        language = ast_info['language']
        
        # Update splitter language if using LlamaIndex
        if self.use_llamaindex:
            self.splitter.language = language
        
        # Function-level chunks
        for func in ast_info.get('functions', []):
            chunk = self._create_function_chunk(func, ast_info)
            if chunk:
                chunks.append(chunk)
        
        # Class-level chunks
        for cls in ast_info.get('classes', []):
            chunk = self._create_class_chunk(cls, ast_info)
            if chunk:
                chunks.append(chunk)
        
        # File-level chunks for remaining content
        if not chunks:  # If no functions/classes found, chunk the entire file
            if self.use_llamaindex:
                file_chunks = self._create_file_chunks_llamaindex(content, file_path, language)
            else:
                file_chunks = self._create_file_chunks_simple(content, file_path, language)
            chunks.extend(file_chunks)
        
        return chunks
    
    def _create_function_chunk(self, func: Dict[str, Any], ast_info: Dict[str, Any]) -> Dict[str, Any]:
        """Create a chunk for a function"""
        try:
            content = func['content']
            file_path = ast_info['file_path']  # Use normalized path
            chunk_id = self._generate_chunk_id(file_path, func['name'], 'function')
            
            return {
                'id': chunk_id,
                'type': 'function',
                'file_path': file_path,
                'language': ast_info['language'],
                'name': func['name'],
                'content': content,
                'start_line': func['start_point'][0] + 1,
                'end_line': func['end_point'][0] + 1,
                'parameters': func.get('parameters', []),
                'docstring': func.get('docstring'),
                'metadata': {
                    'node_type': 'function',
                    'function_name': func['name'],
                    'file_path': file_path,
                    'language': ast_info['language']
                }
            }
        except Exception as e:
            logger.warning(f"Error creating function chunk: {e}")
            return None
    
    def _create_class_chunk(self, cls: Dict[str, Any], ast_info: Dict[str, Any]) -> Dict[str, Any]:
        """Create a chunk for a class"""
        try:
            content = cls['content']
            file_path = ast_info['file_path']  # Use normalized path
            chunk_id = self._generate_chunk_id(file_path, cls['name'], 'class')
            
            return {
                'id': chunk_id,
                'type': 'class',
                'file_path': file_path,
                'language': ast_info['language'],
                'name': cls['name'],
                'content': content,
                'start_line': cls['start_point'][0] + 1,
                'end_line': cls['end_point'][0] + 1,
                'methods': cls.get('methods', []),
                'docstring': cls.get('docstring'),
                'metadata': {
                    'node_type': 'class',
                    'class_name': cls['name'],
                    'file_path': file_path,
                    'language': ast_info['language']
                }
            }
        except Exception as e:
            logger.warning(f"Error creating class chunk: {e}")
            return None
    
    def _create_file_chunks_llamaindex(self, content: str, file_path: str, language: str) -> List[Dict[str, Any]]:
        """Create chunks using LlamaIndex CodeSplitter"""
        chunks = []
        
        try:
            # Create LlamaIndex document
            document = Document(
                text=content,
                metadata={
                    'file_path': file_path,
                    'language': language
                }
            )
            
            # Use LlamaIndex CodeSplitter
            nodes = self.splitter.get_nodes_from_documents([document])
            
            for i, node in enumerate(nodes):
                chunk_id = self._generate_chunk_id(
                    file_path, 
                    f"chunk_{i}", 
                    'file_segment'
                )
                
                chunk = {
                    'id': chunk_id,
                    'type': 'file_segment',
                    'file_path': file_path,
                    'language': language,
                    'name': f"chunk_{i}",
                    'content': node.text,
                    'start_line': None,  # Not available from CodeSplitter
                    'end_line': None,
                    'metadata': {
                        'node_type': 'file_segment',
                        'chunk_index': i,
                        'file_path': file_path,
                        'language': language
                    }
                }
                chunks.append(chunk)
                
        except Exception as e:
            logger.error(f"Error creating file chunks with LlamaIndex: {e}")
            # Fallback to simple chunking
            return self._create_file_chunks_simple(content, file_path, language)
            
        return chunks

    def _create_file_chunks_simple(self, content: str, file_path: str, language: str) -> List[Dict[str, Any]]:
        """Create chunks using simple text splitter"""
        chunks = []
        
        try:
            # Use simple text splitter
            text_chunks = self.splitter.split_text(content)
            
            for i, chunk_text in enumerate(text_chunks):
                chunk_id = self._generate_chunk_id(
                    file_path, 
                    f"chunk_{i}", 
                    'file_segment'
                )
                
                chunk = {
                    'id': chunk_id,
                    'type': 'file_segment',
                    'file_path': file_path,
                    'language': language,
                    'name': f"chunk_{i}",
                    'content': chunk_text,
                    'start_line': None,  # Not available from simple splitter
                    'end_line': None,
                    'metadata': {
                        'node_type': 'file_segment',
                        'chunk_index': i,
                        'file_path': file_path,
                        'language': language
                    }
                }
                chunks.append(chunk)
                
        except Exception as e:
            logger.error(f"Error creating file chunks: {e}")
            
        return chunks
    
    def _generate_chunk_id(self, file_path: str, name: str, chunk_type: str) -> str:
        """Generate a unique chunk ID"""
        content = f"{file_path}:{name}:{chunk_type}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def chunk_repository(self, parsed_files: List[Dict[str, Any]], repo_root: str = None) -> List[Dict[str, Any]]:
        """Chunk all files in a repository"""
        all_chunks = []
        
        for ast_info in parsed_files:
            if not ast_info:
                continue
                
            file_chunks = self.chunk_file(ast_info, repo_root)
            all_chunks.extend(file_chunks)
            
            logger.info(f"Created {len(file_chunks)} chunks for {ast_info['file_path']}")
        
        logger.info(f"Created total of {len(all_chunks)} chunks from repository")
        return all_chunks
