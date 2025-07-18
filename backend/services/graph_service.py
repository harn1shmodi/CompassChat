import neo4j
from openai import OpenAI
from core.neo4j_conn import neo4j_conn
from core.config import settings
from services.embedding_cache import embedding_cache
from typing import List, Dict, Any, Optional
import logging
import json
import os

logger = logging.getLogger(__name__)

# Import Neo4j GraphRAG components if available
# try:
from neo4j_graphrag.retrievers import HybridCypherRetriever, VectorRetriever
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.indexes import create_vector_index, create_fulltext_index
from neo4j_graphrag.retrievers.base import RetrieverResultItem
NEO4J_GRAPHRAG_AVAILABLE = True
logger.info("Neo4j GraphRAG library loaded successfully")
# except ImportError as e:
#     logger.warning(f"neo4j-graphrag not available: {e}, using fallback implementation")
#     NEO4J_GRAPHRAG_AVAILABLE = False


class GraphRAGRetriever:
    """Neo4j GraphRAG implementation for hybrid retrieval"""
    
    def __init__(self, driver, openai_client):
        self.driver = driver
        self.openai_client = openai_client
        
        if NEO4J_GRAPHRAG_AVAILABLE:
            # Use official Neo4j GraphRAG
            self.embedder = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=settings.openai_api_key
            )
            
            # Initialize LLM for GraphRAG
            self.llm = OpenAILLM(
                model_name="gpt-4o-mini",
                api_key=settings.openai_api_key,
                model_params={"temperature": 0.1, "max_tokens": 1000}
            )
            
            # Setup hybrid retriever with custom Cypher query
            self.hybrid_retriever = None  # Will be initialized after ensuring indexes exist
            
            # Custom prompt template for code analysis
            self.prompt_template = RagTemplate(
                template="""You are a code analysis assistant. Use the provided code context to answer the user's question.

Context:
{context}

Question: {question}

Answer the question based on the code context provided. Include:
- Relevant code snippets
- Function/class names and their purposes
- File paths where the code is located
- Any relevant relationships between code components

Answer:""",
                expected_inputs=["context", "question"]
            )
            
            # Initialize GraphRAG pipeline
            self._setup_graphrag()
        else:
            # Fallback to custom implementation
            logger.info("Using fallback GraphRAG implementation")
    
    def _setup_graphrag(self):
        """Setup Neo4j GraphRAG retriever and pipeline"""
        try:
            # Ensure indexes exist
            self._ensure_indexes()
            
            # Custom retrieval query for code context
            retrieval_query = """
            OPTIONAL MATCH (node)-[:PART_OF]->(file:File)
            OPTIONAL MATCH (file)-[:DEFINES]->(func:Function)
            OPTIONAL MATCH (file)-[:DEFINES]->(cls:Class)
            OPTIONAL MATCH (func)-[:CALLS]->(called_func:Function)
            OPTIONAL MATCH (file)-[:IMPORTS*1..2]->(imported_file:File)
            
            RETURN 
                node.content as content,
                node.summary as summary,
                node.type as chunk_type,
                node.name as chunk_name,
                file.path as file_path,
                file.language as language,
                collect(DISTINCT func.name) as functions,
                collect(DISTINCT cls.name) as classes,
                collect(DISTINCT called_func.name) as called_functions,
                collect(DISTINCT imported_file.path) as imports,
                score
            """
            
            # Initialize hybrid retriever
            self.hybrid_retriever = HybridCypherRetriever(
                driver=self.driver,
                vector_index_name="chunk_embeddings",
                fulltext_index_name="chunk_content",
                retrieval_query=retrieval_query,
                embedder=self.embedder
            )
            
            # Initialize GraphRAG pipeline
            self.graphrag = GraphRAG(
                retriever=self.hybrid_retriever,
                llm=self.llm,
                prompt_template=self.prompt_template
            )
            
            logger.info("Neo4j GraphRAG setup completed successfully")
            
        except Exception as e:
            logger.error(f"Error setting up Neo4j GraphRAG: {e}")
            # Fall back to custom implementation
            global NEO4J_GRAPHRAG_AVAILABLE
            NEO4J_GRAPHRAG_AVAILABLE = False
    
    def _ensure_indexes(self):
        """Ensure vector and fulltext indexes exist"""
        try:
            with self.driver.session() as session:
                # Check if vector index exists
                vector_index_query = """
                SHOW INDEXES YIELD name, type
                WHERE name = 'chunk_embeddings' AND type = 'VECTOR'
                RETURN count(*) as count
                """
                result = session.run(vector_index_query).single()
                
                if result['count'] == 0:
                    logger.info("Creating vector index for chunk embeddings")
                    create_vector_index(
                        driver=self.driver,
                        index_name="chunk_embeddings",
                        label="Chunk",
                        embedding_property="embedding",
                        dimensions=1536,  # text-embedding-3-small dimensions
                        similarity_function="cosine"
                    )
                
                # Check if fulltext index exists
                fulltext_index_query = """
                SHOW INDEXES YIELD name, type
                WHERE name = 'chunk_content' AND type = 'FULLTEXT'
                RETURN count(*) as count
                """
                result = session.run(fulltext_index_query).single()
                
                if result['count'] == 0:
                    logger.info("Creating fulltext index for chunk content")
                    create_fulltext_index(
                        driver=self.driver,
                        index_name="chunk_content",
                        label="Chunk",
                        properties=["content", "summary", "name"]
                    )
                    
        except Exception as e:
            logger.error(f"Error ensuring indexes: {e}")
            raise
    
    def hybrid_search(self, query: str, limit: int = 10, repository: str = None) -> List[Dict[str, Any]]:
        """Perform repository-scoped hybrid search only"""
        try:
            # Repository is required for all searches
            if not repository:
                logger.warning("Repository parameter is required for all searches")
                return []
            
            # Always use repository-scoped search implementation
            return self._repository_scoped_search(query, limit, repository)
                
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            # Fallback to repository-scoped search
            return self._repository_scoped_search(query, limit, repository)
    
    def _repository_scoped_search(self, query: str, limit: int = 10, repository: str = None) -> List[Dict[str, Any]]:
        """Repository-scoped hybrid search implementation with enhanced scoring"""
        try:
            # Repository parameter is required
            if not repository:
                logger.error("Repository parameter is required for search")
                return []
                
            # Quick relevance check for obviously irrelevant questions
            irrelevant_keywords = ['weather', 'forecast', 'climate', 'rain', 'snow', 'temperature', 
                                 'cooking', 'recipe', 'food', 'medicine', 'health', 'sports', 
                                 'politics', 'news', 'entertainment', 'movie', 'music']
            
            query_lower = query.lower()
            if any(keyword in query_lower for keyword in irrelevant_keywords) and \
               not any(tech_word in query_lower for tech_word in ['code', 'function', 'class', 'api', 'app', 'application', 'software', 'program']):
                logger.info(f"Detected potentially irrelevant question: {query[:50]}...")
                return []
                
            # Generate query embedding
            query_embedding = self._get_embeddings(query)
            if not query_embedding:
                return []

            with neo4j_conn.get_session() as session:
                # Parse repository name (format: owner/name)
                if '/' in repository:
                    repo_owner, repo_name = repository.split('/', 1)
                else:
                    repo_owner = "unknown"
                    repo_name = repository
                
                # Set query timeout to prevent hanging on irrelevant queries
                query_params = {
                    'query': query,
                    'query_embedding': query_embedding,
                    'vector_limit': limit * 3,
                    'limit': limit,
                    'repo_name': repo_name,
                    'repo_owner': repo_owner
                }
                
                # Repository-scoped hybrid query with optimizations
                hybrid_query = """
                // 1. Vector similarity search with repository filtering and minimum threshold
                CALL db.index.vector.queryNodes('chunk_embeddings', $vector_limit, $query_embedding) 
                YIELD node as chunk, score as vector_score
                WHERE vector_score > 0.1  // Filter out very low relevance early
                
                // 2. Get file context with repository filtering
                MATCH (chunk)-[:PART_OF]->(file:File)<-[:CONTAINS]-(repo:Repository)
                WHERE repo.name = $repo_name AND repo.owner = $repo_owner
                
                // 3. Early filtering for decent vector matches only
                WITH chunk, file, vector_score
                WHERE vector_score > 0.15
                
                OPTIONAL MATCH (file)-[:DEFINES]->(func:Function)
                OPTIONAL MATCH (file)-[:DEFINES]->(cls:Class)
                OPTIONAL MATCH (func)-[:CALLS]->(called_func:Function)
                OPTIONAL MATCH (file)-[:IMPORTS*1..2]->(imported_file:File)
                
                // 4. Conditional full-text search (only if we have decent vector matches)
                OPTIONAL CALL db.index.fulltext.queryNodes('chunk_content', $query) 
                YIELD node as ft_chunk, score as ft_score
                WHERE chunk = ft_chunk AND vector_score > 0.2
                
                WITH chunk, file, vector_score, COALESCE(ft_score, 0) as fulltext_score,
                     collect(DISTINCT func.name) as functions,
                     collect(DISTINCT cls.name) as classes,
                     collect(DISTINCT called_func.name) as called_functions,
                     collect(DISTINCT imported_file.path) as imports
                
                // 5. Calculate context boost factors (simplified for performance)
                WITH chunk, file, vector_score, fulltext_score, functions, classes, called_functions, imports,
                     // Simplified scoring for better performance
                     CASE WHEN vector_score > 0.5 THEN 0.2 ELSE 0.0 END as relevance_boost,
                     // Boost for file relevance (lower path depth = higher relevance for main files)
                     CASE WHEN size(split(file.path, '/')) <= 3 THEN 0.1 ELSE 0.0 END as file_boost,
                     // Boost for chunk type relevance
                     CASE chunk.type 
                          WHEN 'function' THEN 0.15
                          WHEN 'class' THEN 0.1
                          ELSE 0.0 END as type_boost
                
                // 6. Calculate final weighted score (simplified and optimized)
                WITH chunk, file, vector_score, fulltext_score, functions, classes, called_functions, imports,
                     // Optimized scoring algorithm - prioritize vector similarity for performance
                     (vector_score * 0.6 + 
                      fulltext_score * 0.2 + 
                      relevance_boost + 
                      file_boost + 
                      type_boost) as combined_score
                
                // 7. Filter out very low relevance results
                WHERE combined_score > 0.1
                
                RETURN 
                    chunk.content as content,
                    chunk.summary as summary,
                    chunk.type as chunk_type,
                    chunk.name as chunk_name,
                    file.path as file_path,
                    file.language as language,
                    functions,
                    classes,
                    called_functions,
                    imports,
                    combined_score,
                    vector_score,
                    fulltext_score
                ORDER BY combined_score DESC
                LIMIT $limit * 2  // Get more results for deduplication
                """
                
                # Execute query with timeout handling
                try:
                    results = session.run(hybrid_query, query_params)
                except Exception as query_error:
                    logger.warning(f"Query execution failed, possibly due to irrelevant question: {query_error}")
                    return []
                
                results = session.run(hybrid_query, query_params)
                
                search_results = []
                seen_content_hashes = set()
                
                for record in results:
                    content = record.get('content', '')
                    
                    # Simple deduplication by content hash
                    content_hash = hash(content[:200])  # Use first 200 chars for similarity
                    if content_hash in seen_content_hashes:
                        continue
                    seen_content_hashes.add(content_hash)
                    
                    result = {
                        'content': content,
                        'summary': record.get('summary', ''),
                        'chunk_type': record.get('chunk_type', ''),
                        'chunk_name': record.get('chunk_name', ''),
                        'file_path': record.get('file_path', ''),
                        'language': record.get('language', ''),
                        'functions': record.get('functions', []),
                        'classes': record.get('classes', []),
                        'called_functions': record.get('called_functions', []),
                        'imports': record.get('imports', []),
                        'score': record.get('combined_score', 0.0),
                        'vector_score': record.get('vector_score', 0.0),
                        'fulltext_score': record.get('fulltext_score', 0.0)
                    }
                    search_results.append(result)
                    
                    if len(search_results) >= limit:
                        break
                
                return search_results
                
        except Exception as e:
            logger.error(f"Error in repository-scoped search: {e}")
            return []
    
    def _get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI with caching"""
        try:
            # Check cache first
            cached_embedding = embedding_cache.get_embedding(text)
            if cached_embedding:
                return cached_embedding
            
            # Generate new embedding
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            embedding = response.data[0].embedding
            
            # Cache the result
            embedding_cache.set_embedding(text, embedding)
            
            return embedding
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []


class GraphService:
    def __init__(self):
        self.driver = neo4j_conn.driver
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.retriever = GraphRAGRetriever(self.driver, self.openai_client)
    
    def get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI"""
        return self.retriever._get_embeddings(text)
    
    def upsert_repository_data(self, repo_info: Dict, chunks: List[Dict[str, Any]], ast_data: List[Dict[str, Any]]):
        """Upsert repository data into Neo4j"""
        try:
            with neo4j_conn.get_session() as session:
                # Create repository node
                self._create_repository_node(session, repo_info)
                
                # Create file nodes and relationships
                for ast_info in ast_data:
                    if ast_info:
                        self._create_file_nodes(session, ast_info, repo_info)
                
                # Create chunk nodes with embeddings
                self._create_chunk_nodes(session, chunks, repo_info)
                
                logger.info(f"Successfully upserted repository data for {repo_info.get('name', 'unknown')}")
                
        except Exception as e:
            logger.error(f"Error upserting repository data: {e}")
            raise
    
    def _create_repository_node(self, session, repo_info: Dict):
        """Create repository node"""
        query = """
        MERGE (repo:Repository {name: $name, owner: $owner})
        SET repo.url = $url,
            repo.default_branch = $default_branch,
            repo.updated_at = datetime()
        """
        session.run(query, repo_info)
    
    def _create_file_nodes(self, session, ast_info: Dict, repo_info: Dict):
        """Create file nodes and code element relationships"""
        file_path = ast_info['file_path']
        language = ast_info['language']
        content = ast_info['content']
        
        # Create file node
        file_query = """
        MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
        MERGE (file:File {path: $file_path})
        SET file.language = $language,
            file.content = $content,
            file.size = size($content)
        MERGE (repo)-[:CONTAINS]->(file)
        """
        session.run(file_query, {
            'repo_name': repo_info['name'],
            'repo_owner': repo_info['owner'],
            'file_path': file_path,
            'language': language,
            'content': content
        })
        
        # Create function nodes
        for func in ast_info.get('functions', []):
            self._create_function_node(session, func, file_path)
        
        # Create class nodes
        for cls in ast_info.get('classes', []):
            self._create_class_node(session, cls, file_path)
        
        # Create import relationships
        for imp in ast_info.get('imports', []):
            self._create_import_relationship(session, imp, file_path)
    
    def _create_function_node(self, session, func: Dict, file_path: str):
        """Create function node and relationships"""
        query = """
        MATCH (file:File {path: $file_path})
        MERGE (func:Function {id: $func_id})
        SET func.name = $name,
            func.parameters = $parameters,
            func.start_line = $start_line,
            func.end_line = $end_line,
            func.content = $content,
            func.docstring = $docstring
        MERGE (file)-[:DEFINES]->(func)
        """
        
        func_id = f"{file_path}:{func['name']}"
        session.run(query, {
            'file_path': file_path,
            'func_id': func_id,
            'name': func['name'],
            'parameters': func.get('parameters', []),
            'start_line': func.get('start_point', [0])[0] + 1,
            'end_line': func.get('end_point', [0])[0] + 1,
            'content': func['content'],
            'docstring': func.get('docstring')
        })
    
    def _create_class_node(self, session, cls: Dict, file_path: str):
        """Create class node and relationships"""
        query = """
        MATCH (file:File {path: $file_path})
        MERGE (class:Class {id: $class_id})
        SET class.name = $name,
            class.methods = $methods,
            class.start_line = $start_line,
            class.end_line = $end_line,
            class.content = $content,
            class.docstring = $docstring
        MERGE (file)-[:DEFINES]->(class)
        """
        
        class_id = f"{file_path}:{cls['name']}"
        session.run(query, {
            'file_path': file_path,
            'class_id': class_id,
            'name': cls['name'],
            'methods': cls.get('methods', []),
            'start_line': cls.get('start_point', [0])[0] + 1,
            'end_line': cls.get('end_point', [0])[0] + 1,
            'content': cls['content'],
            'docstring': cls.get('docstring')
        })
    
    def _create_import_relationship(self, session, imp: Dict, file_path: str):
        """Create import relationships between files"""
        # This is a simplified implementation
        # In practice, you'd want to parse import statements more carefully
        pass
    
    def _create_chunk_nodes(self, session, chunks: List[Dict], repo_info: Dict):
        """Create chunk nodes with embeddings"""
        for chunk in chunks:
            try:
                # Generate embedding for chunk content
                embedding = self.get_embeddings(chunk['content'])
                
                if not embedding:
                    logger.warning(f"Failed to generate embedding for chunk {chunk.get('id', 'unknown')}")
                    continue
                
                # Create chunk node
                query = """
                MATCH (file:File {path: $file_path})
                MERGE (chunk:Chunk {id: $chunk_id})
                SET chunk.content = $content,
                    chunk.summary = $summary,
                    chunk.type = $type,
                    chunk.name = $name,
                    chunk.start_line = $start_line,
                    chunk.end_line = $end_line,
                    chunk.language = $language,
                    chunk.embedding = $embedding
                MERGE (chunk)-[:PART_OF]->(file)
                """
                
                session.run(query, {
                    'file_path': chunk['file_path'],
                    'chunk_id': chunk['id'],
                    'content': chunk['content'],
                    'summary': chunk.get('summary', ''),
                    'type': chunk['type'],
                    'name': chunk['name'],
                    'start_line': chunk.get('start_line'),
                    'end_line': chunk.get('end_line'),
                    'language': chunk['language'],
                    'embedding': embedding
                })
                
            except Exception as e:
                logger.error(f"Error creating chunk node {chunk.get('id', 'unknown')}: {e}")
    
    def search_code(self, query: str, limit: int = 10, repository: str = None) -> List[Dict[str, Any]]:
        """Search code using hybrid GraphRAG retrieval"""
        try:
            return self.retriever.hybrid_search(query, limit, repository)
        except Exception as e:
            logger.error(f"Error searching code: {e}")
            return []
    
    def generate_answer_with_graphrag(self, question: str) -> str:
        """Generate answer using Neo4j GraphRAG pipeline"""
        try:
            if NEO4J_GRAPHRAG_AVAILABLE and hasattr(self.retriever, 'graphrag') and self.retriever.graphrag:
                # Use official GraphRAG pipeline
                response = self.retriever.graphrag.search(
                    query_text=question,
                    retriever_config={"top_k": 10}
                )
                
                if hasattr(response, 'answer'):
                    return response.answer
                else:
                    return str(response)
            else:
                # Fallback to custom implementation
                context_results = self.search_code(question, limit=10)
                context = self._format_context(context_results)
                return self.generate_answer(question, context)
                
        except Exception as e:
            logger.error(f"Error generating answer with GraphRAG: {e}")
            # Fallback to custom implementation
            context_results = self.search_code(question, limit=10)
            context = self._format_context(context_results)
            return self.generate_answer(question, context)
    
    def _format_context(self, results: List[Dict]) -> str:
        """Format search results into context string"""
        context_parts = []
        for result in results:
            context_part = f"File: {result.get('file_path', 'unknown')}\n"
            context_part += f"Language: {result.get('language', 'unknown')}\n"
            context_part += f"Type: {result.get('chunk_type', 'unknown')}\n"
            if result.get('chunk_name'):
                context_part += f"Name: {result.get('chunk_name')}\n"
            context_part += f"Content:\n{result.get('content', '')}\n"
            if result.get('summary'):
                context_part += f"Summary: {result.get('summary')}\n"
            context_part += f"Relevance Score: {result.get('score', 0.0):.3f}\n"
            context_part += "---\n"
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    def generate_answer(self, question: str, context: str) -> str:
        """Generate answer using OpenAI"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code analysis assistant. Answer the user's question based on the provided code context."
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nCode Context:\n{context}"
                    }
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return "I apologize, but I encountered an error while generating an answer."
    
    def stream_answer(self, question: str, context: str = None):
        """Stream answer generation with buffered chunks"""
        try:
            if context is None:
                # Get context using GraphRAG
                context_results = self.search_code(question, limit=10)
                context = self._format_context(context_results)
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code analysis assistant. Answer the user's question based on the provided code context."
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nCode Context:\n{context}"
                    }
                ],
                max_tokens=1000,
                temperature=0.1,
                stream=True
            )
            
            buffer = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    buffer += chunk.choices[0].delta.content
                    
                    # Yield when we have a complete sentence or enough text
                    if len(buffer) >= 50 or any(buffer.endswith(punct) for punct in ['. ', '! ', '? ', '\n\n']):
                        yield buffer
                        buffer = ""
            
            # Yield any remaining content
            if buffer:
                yield buffer
                    
        except Exception as e:
            logger.error(f"Error streaming answer: {e}")
            yield "I apologize, but I encountered an error while generating an answer."
    
    def repository_exists(self, repo_name: str) -> bool:
        """Check if repository exists in the graph database"""
        try:
            with neo4j_conn.get_session() as session:
                # Split repo_name if it contains owner/name format
                if '/' in repo_name:
                    owner, name = repo_name.split('/', 1)
                else:
                    owner, name = None, repo_name
                
                if owner:
                    query = """
                    MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
                    RETURN count(repo) > 0 as exists
                    """
                    result = session.run(query, {
                        'repo_name': name,
                        'repo_owner': owner
                    }).single()
                else:
                    query = """
                    MATCH (repo:Repository {name: $repo_name})
                    RETURN count(repo) > 0 as exists
                    """
                    result = session.run(query, {'repo_name': name}).single()
                
                return result and result['exists']
                
        except Exception as e:
            logger.error(f"Error checking repository existence: {e}")
            return False
    
    def clear_repository(self, repo_name: str):
        """Clear repository data from graph database"""
        try:
            with neo4j_conn.get_session() as session:
                # Split repo_name if it contains owner/name format
                if '/' in repo_name:
                    owner, name = repo_name.split('/', 1)
                else:
                    owner, name = None, repo_name
                
                if owner:
                    query = """
                    MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
                    OPTIONAL MATCH (repo)-[:CONTAINS]->(file:File)
                    OPTIONAL MATCH (file)-[:DEFINES|PART_OF*]->(node)
                    DETACH DELETE repo, file, node
                    """
                    session.run(query, {
                        'repo_name': name,
                        'repo_owner': owner
                    })
                else:
                    query = """
                    MATCH (repo:Repository {name: $repo_name})
                    OPTIONAL MATCH (repo)-[:CONTAINS]->(file:File)
                    OPTIONAL MATCH (file)-[:DEFINES|PART_OF*]->(node)
                    DETACH DELETE repo, file, node
                    """
                    session.run(query, {'repo_name': name})
                
                logger.info(f"Cleared repository data: {repo_name}")
                
        except Exception as e:
            logger.error(f"Error clearing repository: {e}")
    
    def get_repository_stats(self, repo_name: str, repo_owner: str) -> Dict[str, Any]:
        """Get repository statistics"""
        try:
            with neo4j_conn.get_session() as session:
                query = """
                MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
                OPTIONAL MATCH (repo)-[:CONTAINS]->(file:File)
                OPTIONAL MATCH (file)-[:DEFINES]->(func:Function)
                OPTIONAL MATCH (file)-[:DEFINES]->(cls:Class)
                OPTIONAL MATCH (chunk:Chunk)-[:PART_OF]->(file)
                
                RETURN 
                    count(DISTINCT file) as file_count,
                    count(DISTINCT func) as function_count,
                    count(DISTINCT cls) as class_count,
                    count(DISTINCT chunk) as chunk_count,
                    collect(DISTINCT file.language) as languages
                """
                
                result = session.run(query, {
                    'repo_name': repo_name,
                    'repo_owner': repo_owner
                }).single()
                
                if result:
                    return {
                        'files': result['file_count'],
                        'functions': result['function_count'],
                        'classes': result['class_count'],
                        'chunks': result['chunk_count'],
                        'languages': [lang for lang in result['languages'] if lang]
                    }
                
                return {
                    'files': 0,
                    'functions': 0,
                    'classes': 0,
                    'chunks': 0,
                    'languages': []
                }
                
        except Exception as e:
            logger.error(f"Error getting repository stats: {e}")
            return {
                'files': 0,
                'functions': 0,
                'classes': 0,
                'chunks': 0,
                'languages': []
            }
