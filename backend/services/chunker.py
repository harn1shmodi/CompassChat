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
import os

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
        
        # Import documentation parser
        try:
            from services.documentation_parser import DocumentationParser
            self.doc_parser = DocumentationParser()
            logger.info("Documentation parser initialized")
        except ImportError:
            self.doc_parser = None
            logger.warning("Documentation parser not available")
    
    def chunk_file(self, ast_info: Dict[str, Any], repo_root: str = None) -> List[Dict[str, Any]]:
        """Chunk a file into semantic segments"""
        chunks = []
        file_path = ast_info['file_path']  # This is now already normalized
        content = ast_info['content']
        language = ast_info['language']
        
        # Handle documentation files with special parser
        if self.doc_parser and self.doc_parser.should_parse_file(file_path):
            doc_chunks = self._create_documentation_chunks(ast_info)
            if doc_chunks:
                chunks.extend(doc_chunks)
            return chunks
        
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
    
    def _create_documentation_chunks(self, ast_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create chunks for documentation and configuration files"""
        chunks = []
        file_path = ast_info['file_path']
        content = ast_info['content']
        
        if not self.doc_parser:
            return []
        
        # Parse the documentation file
        parsed_data = self.doc_parser.parse_file(file_path, content)
        
        # Create different types of chunks based on file type
        file_name = os.path.basename(file_path)
        
        if file_name.lower() == 'readme.md':
            # Create project overview chunks from README
            chunks.append(self._create_project_overview_chunk(parsed_data, file_path))
            
            # Create feature chunks
            if parsed_data.get('features'):
                for feature in parsed_data['features']:
                    chunks.append(self._create_feature_chunk(feature, file_path))
            
            # Create description chunk
            if parsed_data.get('description'):
                chunks.append(self._create_description_chunk(parsed_data, file_path))
                
        elif file_name == 'package.json':
            # Create project metadata chunks from package.json
            chunks.append(self._create_package_json_chunk(parsed_data, file_path))
            
        elif file_name == 'requirements.txt':
            # Create Python project overview
            chunks.append(self._create_requirements_chunk(parsed_data, file_path))
            
        elif file_name in ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml']:
            # Create deployment overview
            chunks.append(self._create_docker_chunk(parsed_data, file_path))
            
        else:
            # Generic documentation chunk
            chunks.append(self._create_generic_doc_chunk(parsed_data, file_path))
        
        return chunks
    
    def _create_project_overview_chunk(self, parsed_data: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create a project overview chunk from README"""
        return {
            'id': self._generate_chunk_id(file_path, 'project_overview', 'documentation'),
            'type': 'project_overview',
            'file_path': file_path,
            'language': 'markdown',
            'name': 'Project Overview',
            'content': f"""
Project Title: {parsed_data.get('title', 'Unknown')}
Description: {parsed_data.get('description', '')}

Key Features:
{chr(10).join(f"- {feature}" for feature in parsed_data.get('features', [])[:5])}

Installation: {parsed_data.get('installation', 'See README for installation instructions')}
            """.strip(),
            'summary': f"Project: {parsed_data.get('title', 'Unknown')} - {parsed_data.get('description', '')[:200]}...",
            'metadata': {
                'node_type': 'project_overview',
                'project_name': parsed_data.get('title', 'Unknown'),
                'project_type': 'documentation'
            }
        }
    
    def _create_feature_chunk(self, feature: str, file_path: str) -> Dict[str, Any]:
        """Create a feature-specific chunk"""
        return {
            'id': self._generate_chunk_id(file_path, f'feature_{feature[:20]}', 'documentation'),
            'type': 'feature',
            'file_path': file_path,
            'language': 'markdown',
            'name': f'Feature: {feature[:50]}',
            'content': f"Feature: {feature}",
            'summary': f"Feature: {feature}",
            'metadata': {
                'node_type': 'feature',
                'feature_description': feature
            }
        }
    
    def _create_description_chunk(self, parsed_data: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create a project description chunk"""
        return {
            'id': self._generate_chunk_id(file_path, 'project_description', 'documentation'),
            'type': 'project_description',
            'file_path': file_path,
            'language': 'markdown',
            'name': 'Project Description',
            'content': parsed_data.get('description', ''),
            'summary': f"Project Description: {parsed_data.get('description', '')[:200]}...",
            'metadata': {
                'node_type': 'project_description',
                'description': parsed_data.get('description', '')
            }
        }
    
    def _create_package_json_chunk(self, parsed_data: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create Node.js project metadata chunks"""
        return {
            'id': self._generate_chunk_id(file_path, 'node_project', 'configuration'),
            'type': 'project_metadata',
            'file_path': file_path,
            'language': 'json',
            'name': f"Node.js Project: {parsed_data.get('name', '')}",
            'content': f"""
Project: {parsed_data.get('name', 'Unknown')}
Description: {parsed_data.get('description', '')}
Version: {parsed_data.get('version', '')}
Main Entry: {parsed_data.get('main', '')}

Dependencies: {', '.join(parsed_data.get('dependencies', [])[:10])}
Dev Dependencies: {', '.join(parsed_data.get('dev_dependencies', [])[:5])}
Scripts: {', '.join(parsed_data.get('scripts', [])[:5])}
            """.strip(),
            'summary': f"Node.js project: {parsed_data.get('name', '')} - {parsed_data.get('description', '')}",
            'metadata': {
                'node_type': 'project_metadata',
                'project_type': 'nodejs',
                'dependencies': parsed_data.get('dependencies', []),
                'dev_dependencies': parsed_data.get('dev_dependencies', [])
            }
        }
    
    def _create_requirements_chunk(self, parsed_data: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create Python project overview"""
        return {
            'id': self._generate_chunk_id(file_path, 'python_project', 'configuration'),
            'type': 'project_metadata',
            'file_path': file_path,
            'language': 'text',
            'name': 'Python Project Dependencies',
            'content': f"""
Python project with {len(parsed_data.get('dependencies', []))} dependencies:
{chr(10).join(f"- {dep}" for dep in parsed_data.get('dependencies', [])[:10])}
            """.strip(),
            'summary': f"Python project with {len(parsed_data.get('dependencies', []))} dependencies",
            'metadata': {
                'node_type': 'project_metadata',
                'project_type': 'python',
                'dependencies': parsed_data.get('dependencies', [])
            }
        }
    
    def _create_docker_chunk(self, parsed_data: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create Docker deployment overview"""
        return {
            'id': self._generate_chunk_id(file_path, 'docker_info', 'configuration'),
            'type': 'deployment_info',
            'file_path': file_path,
            'language': 'dockerfile',
            'name': 'Docker Configuration',
            'content': f"""
Docker Configuration:
Base Image: {parsed_data.get('base_image', 'Not specified')}
Services: {', '.join(parsed_data.get('services', []))}
            """.strip(),
            'summary': f"Docker configuration using {parsed_data.get('base_image', 'custom setup')}",
            'metadata': {
                'node_type': 'deployment_info',
                'base_image': parsed_data.get('base_image'),
                'services': parsed_data.get('services', [])
            }
        }
    
    def _create_generic_doc_chunk(self, parsed_data: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Create a generic documentation chunk"""
        return {
            'id': self._generate_chunk_id(file_path, 'documentation', 'documentation'),
            'type': 'documentation',
            'file_path': file_path,
            'language': 'text',
            'name': parsed_data.get('file_type', 'documentation'),
            'content': parsed_data.get('content', ''),
            'summary': parsed_data.get('summary', f"Documentation: {os.path.basename(file_path)}"),
            'metadata': {
                'node_type': 'documentation',
                'file_type': parsed_data.get('file_type', 'unknown')
            }
        }
    
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
