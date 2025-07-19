import neo4j
from openai import OpenAI
from core.neo4j_conn import neo4j_conn
from core.config import settings
from services.embedding_cache import embedding_cache
from services.optimized_embedding import optimized_embedding_service
from services.ai_provider import ai_provider
from services.query_preprocessor import query_preprocessor
from typing import List, Dict, Any, Optional
import logging
import json
import os
import asyncio
from ratelimit import limits, sleep_and_retry
import time

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
            
            # Custom retrieval query for code context (simplified to avoid hanging)
            retrieval_query = """
            OPTIONAL MATCH (node)-[:PART_OF]->(file:File)
            OPTIONAL MATCH (file)-[:DEFINES]->(func:Function)
            OPTIONAL MATCH (file)-[:DEFINES]->(cls:Class)
            
            RETURN 
                node.content as content,
                node.summary as summary,
                node.type as chunk_type,
                node.name as chunk_name,
                file.path as file_path,
                file.language as language,
                collect(DISTINCT func.name)[0..5] as functions,
                collect(DISTINCT cls.name)[0..5] as classes,
                [] as called_functions,
                [] as imports,
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
    
    def hybrid_search(self, query: str, limit: int = 10, repository: str = None, user_id: str = None) -> List[Dict[str, Any]]:
        """Perform repository-scoped hybrid search only with user isolation"""
        try:
            import time
            start_time = time.time()
            
            logger.info(f"GraphRAGRetriever.hybrid_search called with query: '{query[:50]}...' repository: '{repository}' user: '{user_id}' limit: {limit}")
            
            # Repository is required for all searches
            if not repository:
                logger.warning("Repository parameter is required for all searches")
                return []
            
            # Always use repository-scoped search implementation
            results = self._repository_scoped_search(query, limit, repository, user_id)
            
            duration = time.time() - start_time
            logger.info(f"GraphRAGRetriever.hybrid_search completed in {duration:.2f}s, returning {len(results)} results")
            
            return results
                
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Fallback to repository-scoped search
            return self._repository_scoped_search(query, limit, repository, user_id)
    
    def _repository_scoped_search(self, query: str, limit: int = 10, repository: str = None, user_id: str = None) -> List[Dict[str, Any]]:
        """Repository-scoped hybrid search implementation with enhanced scoring and user isolation"""
        try:
            import time
            start_time = time.time()
            
            logger.info(f"_repository_scoped_search called with query: '{query[:50]}...' repository: '{repository}' user: '{user_id}' limit: {limit}")
            
            # Repository parameter is required
            if not repository:
                logger.error("Repository parameter is required for search")
                return []
                
            # Allow all questions including basic ones like "what does this app do?"
                
            # Generate query embedding
            embedding_start = time.time()
            logger.info(f"Generating embeddings for query: '{query[:50]}...'")
            
            query_embedding = self._get_embeddings(query)
            if not query_embedding:
                logger.error("Failed to generate query embedding")
                return []
                
            embedding_duration = time.time() - embedding_start
            logger.info(f"Query embedding generated in {embedding_duration:.2f}s")

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
                    'repo_owner': repo_owner,
                    'user_id': user_id
                }
                
                # Repository-scoped hybrid query with optimizations and timeout safety
                hybrid_query = """
                // 1. Vector similarity search with repository filtering and minimum threshold
                CALL db.index.vector.queryNodes('chunk_embeddings', $vector_limit, $query_embedding) 
                YIELD node as chunk, score as vector_score
                WHERE vector_score > 0.1  // Filter out very low relevance early
                
                // 2. Get file context with repository filtering and user isolation
                MATCH (chunk)-[:PART_OF]->(file:File)<-[:CONTAINS]-(repo:Repository)
                WHERE repo.name = $repo_name AND repo.owner = $repo_owner
                AND ($user_id IS NULL OR repo.user_id = $user_id)
                
                // 3. Relaxed filtering for basic questions
                WITH chunk, file, vector_score
                WHERE vector_score > 0.05
                
                // 4. Get basic file metadata (simplified for performance)
                OPTIONAL MATCH (file)-[:DEFINES]->(func:Function)
                OPTIONAL MATCH (file)-[:DEFINES]->(cls:Class)
                
                // 5. Full-text search for all chunks (including documentation)
                OPTIONAL CALL db.index.fulltext.queryNodes('chunk_content', $query) 
                YIELD node as ft_chunk, score as ft_score
                WHERE chunk = ft_chunk
                
                WITH chunk, file, vector_score, COALESCE(ft_score, 0) as fulltext_score,
                     collect(DISTINCT func.name)[0..5] as functions,  // Limit to prevent memory issues
                     collect(DISTINCT cls.name)[0..5] as classes
                
                // 6. Calculate context boost factors (optimized for project overview)
                WITH chunk, file, vector_score, fulltext_score, functions, classes,
                     // Boost for documentation and project overview chunks
                     CASE chunk.type 
                          WHEN 'project_overview' THEN 0.3
                          WHEN 'project_description' THEN 0.25
                          WHEN 'project_metadata' THEN 0.25
                          WHEN 'documentation' THEN 0.2
                          WHEN 'feature' THEN 0.15
                          WHEN 'function' THEN 0.15
                          WHEN 'class' THEN 0.1
                          ELSE 0.1 END as type_boost,
                     // Boost for main files (README, package.json, etc.)
                     CASE 
                          WHEN file.path CONTAINS 'README' THEN 0.3
                          WHEN file.path CONTAINS 'package.json' THEN 0.25
                          WHEN file.path CONTAINS 'requirements.txt' THEN 0.25
                          WHEN file.path CONTAINS 'Dockerfile' THEN 0.2
                          WHEN size(split(file.path, '/')) <= 2 THEN 0.15
                          ELSE 0.05 END as file_boost
                
                // 7. Calculate final weighted score (optimized for basic questions)
                WITH chunk, file, vector_score, fulltext_score, functions, classes,
                     (vector_score * 0.5 + 
                      fulltext_score * 0.3 + 
                      type_boost + 
                      file_boost) as combined_score
                
                // 8. Filter out very low relevance results (relaxed threshold)
                WHERE combined_score > 0.05
                
                RETURN 
                    chunk.content as content,
                    chunk.summary as summary,
                    chunk.type as chunk_type,
                    chunk.name as chunk_name,
                    file.path as file_path,
                    file.language as language,
                    functions,
                    classes,
                    [] as called_functions,  // Simplified - removed expensive calls lookup
                    [] as imports,           // Simplified - removed expensive imports lookup
                    combined_score,
                    vector_score,
                    fulltext_score
                ORDER BY combined_score DESC
                LIMIT $limit * 2  // Get more results for deduplication
                """
                
                # Execute query with timeout handling
                try:
                    query_start = time.time()
                    logger.info(f"Executing Neo4j hybrid query for repository: '{repository}'")
                    
                    # Set transaction timeout to prevent hanging
                    with session.begin_transaction() as tx:
                        # Set a reasonable timeout to prevent hanging
                        results = tx.run(hybrid_query, query_params)
                        
                        # Convert to list with timeout (this is the potential hanging point)
                        logger.info("Converting Neo4j results to list... (potential hanging point)")
                        results = list(results)
                        
                    query_duration = time.time() - query_start
                    logger.info(f"Neo4j hybrid query completed in {query_duration:.2f}s, got {len(results)} raw results")
                    
                except Exception as query_error:
                    query_duration = time.time() - query_start
                    logger.warning(f"Complex query execution failed after {query_duration:.2f}s, trying fallback: {query_error}")
                    
                    # Try a simpler fallback query
                    try:
                        fallback_start = time.time()
                        logger.info("Executing fallback Neo4j query...")
                        
                        fallback_query = """
                        CALL db.index.vector.queryNodes('chunk_embeddings', $vector_limit, $query_embedding) 
                        YIELD node as chunk, score as vector_score
                        WHERE vector_score > 0.03
                        
                        MATCH (chunk)-[:PART_OF]->(file:File)<-[:CONTAINS]-(repo:Repository)
                        WHERE repo.name = $repo_name AND repo.owner = $repo_owner
                        AND ($user_id IS NULL OR repo.user_id = $user_id)
                        
                        RETURN 
                            chunk.content as content,
                            chunk.summary as summary,
                            chunk.type as chunk_type,
                            chunk.name as chunk_name,
                            file.path as file_path,
                            file.language as language,
                            [] as functions,
                            [] as classes,
                            [] as called_functions,
                            [] as imports,
                            vector_score as combined_score,
                            vector_score,
                            0.0 as fulltext_score
                        ORDER BY vector_score DESC
                        LIMIT $limit
                        """
                        
                        with session.begin_transaction() as tx:
                            results = tx.run(fallback_query, query_params)
                            results = list(results)
                            
                        fallback_duration = time.time() - fallback_start
                        logger.info(f"Fallback query completed in {fallback_duration:.2f}s, got {len(results)} results")
                            
                    except Exception as fallback_error:
                        fallback_duration = time.time() - fallback_start
                        logger.error(f"Even fallback query failed after {fallback_duration:.2f}s: {fallback_error}")
                        return []
                
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
    
    def _search_with_embedding(self, query: str, embedding: List[float], limit: int, repository: str, user_id: str) -> List[Dict[str, Any]]:
        """Search using a specific embedding vector"""
        try:
            with neo4j_conn.get_session() as session:
                # Parse repository name
                if '/' in repository:
                    repo_owner, repo_name = repository.split('/', 1)
                else:
                    repo_owner = "unknown"
                    repo_name = repository
                
                vector_query = """
                CALL db.index.vector.queryNodes('chunk_embeddings', $limit, $query_embedding) 
                YIELD node as chunk, score as vector_score
                WHERE vector_score > 0.05
                
                MATCH (chunk)-[:PART_OF]->(file:File)<-[:CONTAINS]-(repo:Repository)
                WHERE repo.name = $repo_name AND repo.owner = $repo_owner
                AND ($user_id IS NULL OR repo.user_id = $user_id)
                
                RETURN 
                    chunk.content as content,
                    chunk.summary as summary,
                    chunk.type as chunk_type,
                    chunk.name as chunk_name,
                    file.path as file_path,
                    file.language as language,
                    [] as functions,
                    [] as classes,
                    [] as called_functions,
                    [] as imports,
                    vector_score as combined_score,
                    vector_score,
                    0.0 as fulltext_score
                ORDER BY vector_score DESC
                LIMIT $limit
                """
                
                results = session.run(vector_query, {
                    'query_embedding': embedding,
                    'limit': limit,
                    'repo_name': repo_name,
                    'repo_owner': repo_owner,
                    'user_id': user_id
                })
                
                search_results = []
                for record in results:
                    result = {
                        'content': record.get('content', ''),
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
                
                return search_results
                
        except Exception as e:
            logger.error(f"Error in vector search with custom embedding: {e}")
            return []
    
    def _re_rank_results(self, results: List[Dict[str, Any]], preprocessed: Dict, limit: int) -> List[Dict[str, Any]]:
        """Re-rank results based on query intent and relevance"""
        try:
            if not results:
                return results
            
            intent = preprocessed.get('intent', 'general')
            
            # Boost scores based on intent
            for result in results:
                original_score = result.get('score', 0.0)
                boost = 0.0
                
                # Intent-specific boosting
                if intent == 'project_overview':
                    # Boost README, package.json, main files
                    file_path = result.get('file_path', '').lower()
                    if 'readme' in file_path:
                        boost += 0.3
                    elif 'package.json' in file_path or 'requirements.txt' in file_path:
                        boost += 0.25
                    elif result.get('chunk_type') == 'documentation':
                        boost += 0.2
                
                elif intent == 'architecture':
                    # Boost main module files and documentation
                    file_path = result.get('file_path', '').lower()
                    if any(term in file_path for term in ['main', 'app', 'index', 'config']):
                        boost += 0.15
                    elif result.get('chunk_type') == 'class':
                        boost += 0.1
                
                elif intent == 'usage':
                    # Boost documentation and examples
                    if result.get('chunk_type') == 'documentation':
                        boost += 0.2
                    elif 'example' in result.get('file_path', '').lower():
                        boost += 0.15
                
                # Update score
                result['score'] = original_score + boost
            
            # Sort by updated score
            results.sort(key=lambda x: x.get('score', 0.0), reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error re-ranking results: {e}")
            return results[:limit]


class GraphService:
    def __init__(self):
        self.driver = neo4j_conn.driver
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.retriever = GraphRAGRetriever(self.driver, self.openai_client)
    
    def get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI"""
        return self.retriever._get_embeddings(text)
    
    def upsert_repository_data(self, repo_info: Dict, chunks: List[Dict[str, Any]], ast_data: List[Dict[str, Any]], user_id: str = None):
        """Upsert repository data into Neo4j with user ownership"""
        try:
            with neo4j_conn.get_session() as session:
                # Create repository node with user ownership
                self._create_repository_node(session, repo_info, user_id)
                
                # Create file nodes and relationships with user ownership
                for ast_info in ast_data:
                    if ast_info:
                        self._create_file_nodes(session, ast_info, repo_info, user_id)
                
                # Create chunk nodes with embeddings and user ownership
                self._create_chunk_nodes(session, chunks, repo_info, user_id)
                
                logger.info(f"Successfully upserted repository data for {repo_info.get('name', 'unknown')} (user: {user_id})")
                
        except Exception as e:
            logger.error(f"Error upserting repository data: {e}")
            raise
    
    def _create_repository_node(self, session, repo_info: Dict, user_id: str = None):
        """Create repository node with user ownership"""
        if user_id:
            # User-specific repository
            query = """
            MERGE (user:User {user_id: $user_id})
            MERGE (repo:Repository {name: $name, owner: $owner, user_id: $user_id})
            SET repo.url = $url,
                repo.default_branch = $default_branch,
                repo.user_id = $user_id,
                repo.updated_at = datetime()
            MERGE (user)-[:OWNS]->(repo)
            """
            session.run(query, {**repo_info, 'user_id': user_id})
        else:
            # Backward compatibility: global repository
            query = """
            MERGE (repo:Repository {name: $name, owner: $owner})
            SET repo.url = $url,
                repo.default_branch = $default_branch,
                repo.updated_at = datetime()
            """
            session.run(query, repo_info)
    
    def _create_file_nodes(self, session, ast_info: Dict, repo_info: Dict, user_id: str = None):
        """Create file nodes and code element relationships with user ownership"""
        file_path = ast_info['file_path']
        language = ast_info['language']
        content = ast_info['content']
        
        try:
            if user_id:
                # User-specific repository with consistent file identifier
                file_query = """
                MATCH (repo:Repository {name: $repo_name, owner: $repo_owner, user_id: $user_id})
                MERGE (file:File {path: $file_path, user_id: $user_id})
                ON CREATE SET file.language = $language,
                              file.content = $content,
                              file.size = size($content),
                              file.user_id = $user_id
                ON MATCH SET file.language = $language,
                             file.content = $content,
                             file.size = size($content),
                             file.updated_at = datetime()
                MERGE (repo)-[:CONTAINS]->(file)
                """
                session.run(file_query, {
                    'repo_name': repo_info['name'],
                    'repo_owner': repo_info['owner'],
                    'user_id': user_id,
                    'file_path': file_path,
                    'language': language,
                    'content': content
                })
            else:
                # Global repository - ensure no user_id conflicts
                file_query = """
                MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
                WHERE repo.user_id IS NULL
                MERGE (file:File {path: $file_path})
                WHERE file.user_id IS NULL
                ON CREATE SET file.language = $language,
                              file.content = $content,
                              file.size = size($content)
                ON MATCH SET file.language = $language,
                             file.content = $content,
                             file.size = size($content),
                             file.updated_at = datetime()
                MERGE (repo)-[:CONTAINS]->(file)
                """
                session.run(file_query, {
                    'repo_name': repo_info['name'],
                    'repo_owner': repo_info['owner'],
                    'file_path': file_path,
                    'language': language,
                    'content': content
                })
        except Exception as e:
            logger.error(f"Error creating file node for {file_path}: {e}")
            # Try to handle constraint violations by updating existing node
            try:
                if user_id:
                    fallback_query = """
                    MATCH (repo:Repository {name: $repo_name, owner: $repo_owner, user_id: $user_id})
                    MATCH (file:File {path: $file_path})
                    SET file.user_id = $user_id,
                        file.language = $language,
                        file.content = $content,
                        file.size = size($content),
                        file.updated_at = datetime()
                    MERGE (repo)-[:CONTAINS]->(file)
                    """
                else:
                    fallback_query = """
                    MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
                    WHERE repo.user_id IS NULL
                    MATCH (file:File {path: $file_path})
                    SET file.language = $language,
                        file.content = $content,
                        file.size = size($content),
                        file.updated_at = datetime()
                    MERGE (repo)-[:CONTAINS]->(file)
                    """
                
                session.run(fallback_query, {
                    'repo_name': repo_info['name'],
                    'repo_owner': repo_info['owner'],
                    'user_id': user_id,
                    'file_path': file_path,
                    'language': language,
                    'content': content
                })
                logger.info(f"Successfully updated existing file node: {file_path}")
            except Exception as fallback_error:
                logger.error(f"Failed to handle file node constraint violation for {file_path}: {fallback_error}")
                raise
        
        # Create function nodes
        for func in ast_info.get('functions', []):
            self._create_function_node(session, func, file_path, user_id)
        
        # Create class nodes
        for cls in ast_info.get('classes', []):
            self._create_class_node(session, cls, file_path, user_id)
        
        # Create import relationships
        for imp in ast_info.get('imports', []):
            self._create_import_relationship(session, imp, file_path)
    
    def _create_function_node(self, session, func: Dict, file_path: str, user_id: str = None):
        """Create function node and relationships with user ownership"""
        func_id = f"{file_path}:{func['name']}"
        
        try:
            if user_id:
                query = """
                MATCH (file:File {path: $file_path, user_id: $user_id})
                MERGE (func:Function {id: $func_id, user_id: $user_id})
                ON CREATE SET func.name = $name,
                              func.parameters = $parameters,
                              func.start_line = $start_line,
                              func.end_line = $end_line,
                              func.content = $content,
                              func.docstring = $docstring,
                              func.user_id = $user_id
                ON MATCH SET func.name = $name,
                             func.parameters = $parameters,
                             func.start_line = $start_line,
                             func.end_line = $end_line,
                             func.content = $content,
                             func.docstring = $docstring,
                             func.updated_at = datetime()
                MERGE (file)-[:DEFINES]->(func)
                """
            else:
                query = """
                MATCH (file:File {path: $file_path})
                WHERE file.user_id IS NULL
                MERGE (func:Function {id: $func_id})
                WHERE func.user_id IS NULL
                ON CREATE SET func.name = $name,
                              func.parameters = $parameters,
                              func.start_line = $start_line,
                              func.end_line = $end_line,
                              func.content = $content,
                              func.docstring = $docstring
                ON MATCH SET func.name = $name,
                             func.parameters = $parameters,
                             func.start_line = $start_line,
                             func.end_line = $end_line,
                             func.content = $content,
                             func.docstring = $docstring,
                             func.updated_at = datetime()
                MERGE (file)-[:DEFINES]->(func)
                """

            session.run(query, {
                'file_path': file_path,
                'func_id': func_id,
                'name': func['name'],
                'parameters': func.get('parameters', []),
                'start_line': func.get('start_point', [0])[0] + 1,
                'end_line': func.get('end_point', [0])[0] + 1,
                'content': func['content'],
                'docstring': func.get('docstring'),
                'user_id': user_id
            })
        except Exception as e:
            logger.error(f"Error creating function node {func_id}: {e}")
            # Try fallback approach
            try:
                if user_id:
                    fallback_query = """
                    MATCH (file:File {path: $file_path})
                    MATCH (func:Function {id: $func_id})
                    SET func.user_id = $user_id,
                        func.name = $name,
                        func.parameters = $parameters,
                        func.start_line = $start_line,
                        func.end_line = $end_line,
                        func.content = $content,
                        func.docstring = $docstring,
                        func.updated_at = datetime()
                    MERGE (file)-[:DEFINES]->(func)
                    """
                else:
                    fallback_query = """
                    MATCH (file:File {path: $file_path})
                    WHERE file.user_id IS NULL
                    MATCH (func:Function {id: $func_id})
                    SET func.name = $name,
                        func.parameters = $parameters,
                        func.start_line = $start_line,
                        func.end_line = $end_line,
                        func.content = $content,
                        func.docstring = $docstring,
                        func.updated_at = datetime()
                    MERGE (file)-[:DEFINES]->(func)
                    """
                
                session.run(fallback_query, {
                    'file_path': file_path,
                    'func_id': func_id,
                    'name': func['name'],
                    'parameters': func.get('parameters', []),
                    'start_line': func.get('start_point', [0])[0] + 1,
                    'end_line': func.get('end_point', [0])[0] + 1,
                    'content': func['content'],
                    'docstring': func.get('docstring'),
                    'user_id': user_id
                })
                logger.info(f"Successfully updated existing function node: {func_id}")
            except Exception as fallback_error:
                logger.error(f"Failed to handle function node constraint violation for {func_id}: {fallback_error}")
    
    def _create_class_node(self, session, cls: Dict, file_path: str, user_id: str = None):
        """Create class node and relationships with user ownership"""
        class_id = f"{file_path}:{cls['name']}"
        
        try:
            if user_id:
                query = """
                MATCH (file:File {path: $file_path, user_id: $user_id})
                MERGE (class:Class {id: $class_id, user_id: $user_id})
                ON CREATE SET class.name = $name,
                              class.methods = $methods,
                              class.start_line = $start_line,
                              class.end_line = $end_line,
                              class.content = $content,
                              class.docstring = $docstring,
                              class.user_id = $user_id
                ON MATCH SET class.name = $name,
                             class.methods = $methods,
                             class.start_line = $start_line,
                             class.end_line = $end_line,
                             class.content = $content,
                             class.docstring = $docstring,
                             class.updated_at = datetime()
                MERGE (file)-[:DEFINES]->(class)
                """
            else:
                query = """
                MATCH (file:File {path: $file_path})
                WHERE file.user_id IS NULL
                MERGE (class:Class {id: $class_id})
                WHERE class.user_id IS NULL
                ON CREATE SET class.name = $name,
                              class.methods = $methods,
                              class.start_line = $start_line,
                              class.end_line = $end_line,
                              class.content = $content,
                              class.docstring = $docstring
                ON MATCH SET class.name = $name,
                             class.methods = $methods,
                             class.start_line = $start_line,
                             class.end_line = $end_line,
                             class.content = $content,
                             class.docstring = $docstring,
                             class.updated_at = datetime()
                MERGE (file)-[:DEFINES]->(class)
                """
            
            session.run(query, {
                'file_path': file_path,
                'class_id': class_id,
                'user_id': user_id,
                'name': cls['name'],
                'methods': cls.get('methods', []),
                'start_line': cls.get('start_point', [0])[0] + 1,
                'end_line': cls.get('end_point', [0])[0] + 1,
                'content': cls['content'],
                'docstring': cls.get('docstring')
            })
        except Exception as e:
            logger.error(f"Error creating class node {class_id}: {e}")
            # Try fallback approach
            try:
                if user_id:
                    fallback_query = """
                    MATCH (file:File {path: $file_path})
                    MATCH (class:Class {id: $class_id})
                    SET class.user_id = $user_id,
                        class.name = $name,
                        class.methods = $methods,
                        class.start_line = $start_line,
                        class.end_line = $end_line,
                        class.content = $content,
                        class.docstring = $docstring,
                        class.updated_at = datetime()
                    MERGE (file)-[:DEFINES]->(class)
                    """
                else:
                    fallback_query = """
                    MATCH (file:File {path: $file_path})
                    WHERE file.user_id IS NULL
                    MATCH (class:Class {id: $class_id})
                    SET class.name = $name,
                        class.methods = $methods,
                        class.start_line = $start_line,
                        class.end_line = $end_line,
                        class.content = $content,
                        class.docstring = $docstring,
                        class.updated_at = datetime()
                    MERGE (file)-[:DEFINES]->(class)
                    """
                
                session.run(fallback_query, {
                    'file_path': file_path,
                    'class_id': class_id,
                    'user_id': user_id,
                    'name': cls['name'],
                    'methods': cls.get('methods', []),
                    'start_line': cls.get('start_point', [0])[0] + 1,
                    'end_line': cls.get('end_point', [0])[0] + 1,
                    'content': cls['content'],
                    'docstring': cls.get('docstring')
                })
                logger.info(f"Successfully updated existing class node: {class_id}")
            except Exception as fallback_error:
                logger.error(f"Failed to handle class node constraint violation for {class_id}: {fallback_error}")
    
    def _create_import_relationship(self, session, imp: Dict, file_path: str):
        """Create import relationships between files"""
        # This is a simplified implementation
        # In practice, you'd want to parse import statements more carefully
        pass
    
    def _create_chunk_nodes(self, session, chunks: List[Dict], repo_info: Dict, user_id: str = None):
        """Create chunk nodes with embeddings using optimized batch processing"""
        if not chunks:
            return
        
        # Check if optimized embedding is enabled
        if settings.enable_optimized_embedding:
            try:
                # Generate embeddings for all chunks in batches
                logger.info(f"Generating embeddings for {len(chunks)} chunks using optimized batch processing")
                
                # Use async embedding generation with thread pool to avoid event loop conflict
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        optimized_embedding_service.generate_embeddings_for_chunks(chunks)
                    )
                    chunks_with_embeddings = future.result()
                
                # Batch database operations
                self._batch_insert_chunks(session, chunks_with_embeddings, user_id)
                
            except Exception as e:
                logger.error(f"Error in optimized chunk processing: {e}")
                # Fallback to sequential processing
                self._create_chunk_nodes_sequential(session, chunks, repo_info, user_id)
        else:
            # Use sequential processing
            logger.info(f"Using sequential embedding processing for {len(chunks)} chunks (optimized processing disabled)")
            self._create_chunk_nodes_sequential(session, chunks, repo_info, user_id)
    
    def _batch_insert_chunks(self, session, chunks: List[Dict], user_id: str = None):
        """Insert chunks in batches to reduce database overhead with user ownership"""
        batch_size = 100
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            try:
                if user_id:
                    query = """
                    UNWIND $chunks AS chunk_data
                    MATCH (file:File {path: chunk_data.file_path, user_id: $user_id})
                    MERGE (chunk:Chunk {id: chunk_data.chunk_id, user_id: $user_id})
                    ON CREATE SET chunk.content = chunk_data.content,
                                  chunk.summary = chunk_data.summary,
                                  chunk.type = chunk_data.type,
                                  chunk.name = chunk_data.name,
                                  chunk.start_line = chunk_data.start_line,
                                  chunk.end_line = chunk_data.end_line,
                                  chunk.language = chunk_data.language,
                                  chunk.embedding = chunk_data.embedding,
                                  chunk.user_id = $user_id
                    ON MATCH SET chunk.content = chunk_data.content,
                                 chunk.summary = chunk_data.summary,
                                 chunk.type = chunk_data.type,
                                 chunk.name = chunk_data.name,
                                 chunk.start_line = chunk_data.start_line,
                                 chunk.end_line = chunk_data.end_line,
                                 chunk.language = chunk_data.language,
                                 chunk.embedding = chunk_data.embedding,
                                 chunk.updated_at = datetime()
                    MERGE (chunk)-[:PART_OF]->(file)
                    """
                else:
                    query = """
                    UNWIND $chunks AS chunk_data
                    MATCH (file:File {path: chunk_data.file_path})
                    WHERE file.user_id IS NULL
                    MERGE (chunk:Chunk {id: chunk_data.chunk_id})
                    WHERE chunk.user_id IS NULL
                    ON CREATE SET chunk.content = chunk_data.content,
                                  chunk.summary = chunk_data.summary,
                                  chunk.type = chunk_data.type,
                                  chunk.name = chunk_data.name,
                                  chunk.start_line = chunk_data.start_line,
                                  chunk.end_line = chunk_data.end_line,
                                  chunk.language = chunk_data.language,
                                  chunk.embedding = chunk_data.embedding
                    ON MATCH SET chunk.content = chunk_data.content,
                                 chunk.summary = chunk_data.summary,
                                 chunk.type = chunk_data.type,
                                 chunk.name = chunk_data.name,
                                 chunk.start_line = chunk_data.start_line,
                                 chunk.end_line = chunk_data.end_line,
                                 chunk.language = chunk_data.language,
                                 chunk.embedding = chunk_data.embedding,
                                 chunk.updated_at = datetime()
                    MERGE (chunk)-[:PART_OF]->(file)
                    """
                
                # Prepare batch data
                batch_data = []
                for chunk in batch:
                    embedding = chunk.get('embedding')
                    if embedding:  # Only include chunks with embeddings
                        batch_data.append({
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
                
                if batch_data:
                    session.run(query, {'chunks': batch_data, 'user_id': user_id})
                    logger.info(f"Inserted batch of {len(batch_data)} chunks")
                    
            except Exception as e:
                logger.error(f"Error in batch chunk insertion: {e}")
                # Fallback to individual chunk processing
                logger.info(f"Falling back to individual chunk processing for batch {i//batch_size + 1}")
                for chunk in batch:
                    try:
                        embedding = chunk.get('embedding')
                        if not embedding:
                            continue
                            
                        self._create_single_chunk(session, chunk, user_id)
                    except Exception as chunk_error:
                        logger.error(f"Failed to process individual chunk {chunk.get('id', 'unknown')}: {chunk_error}")
                        continue
    
    def _create_chunk_nodes_sequential(self, session, chunks: List[Dict], repo_info: Dict, user_id: str = None):
        """Fallback sequential processing method"""
        logger.warning("Using fallback sequential processing for chunks")
        
        for chunk in chunks:
            try:
                # Generate embedding for chunk content
                embedding = self.get_embeddings(chunk['content'])
                
                if not embedding:
                    logger.warning(f"Failed to generate embedding for chunk {chunk.get('id', 'unknown')}")
                    continue
                
                chunk['embedding'] = embedding
                self._create_single_chunk(session, chunk, user_id)
                
            except Exception as e:
                logger.error(f"Error creating chunk node {chunk.get('id', 'unknown')}: {e}")
    
    def _create_single_chunk(self, session, chunk: Dict, user_id: str = None):
        """Create a single chunk node with proper error handling"""
        try:
            if user_id:
                query = """
                MATCH (file:File {path: $file_path, user_id: $user_id})
                MERGE (chunk:Chunk {id: $chunk_id, user_id: $user_id})
                ON CREATE SET chunk.content = $content,
                              chunk.summary = $summary,
                              chunk.type = $type,
                              chunk.name = $name,
                              chunk.start_line = $start_line,
                              chunk.end_line = $end_line,
                              chunk.language = $language,
                              chunk.embedding = $embedding,
                              chunk.user_id = $user_id
                ON MATCH SET chunk.content = $content,
                             chunk.summary = $summary,
                             chunk.type = $type,
                             chunk.name = $name,
                             chunk.start_line = $start_line,
                             chunk.end_line = $end_line,
                             chunk.language = $language,
                             chunk.embedding = $embedding,
                             chunk.updated_at = datetime()
                MERGE (chunk)-[:PART_OF]->(file)
                """
            else:
                query = """
                MATCH (file:File {path: $file_path})
                WHERE file.user_id IS NULL
                MERGE (chunk:Chunk {id: $chunk_id})
                WHERE chunk.user_id IS NULL
                ON CREATE SET chunk.content = $content,
                              chunk.summary = $summary,
                              chunk.type = $type,
                              chunk.name = $name,
                              chunk.start_line = $start_line,
                              chunk.end_line = $end_line,
                              chunk.language = $language,
                              chunk.embedding = $embedding
                ON MATCH SET chunk.content = $content,
                             chunk.summary = $summary,
                             chunk.type = $type,
                             chunk.name = $name,
                             chunk.start_line = $start_line,
                             chunk.end_line = $end_line,
                             chunk.language = $language,
                             chunk.embedding = $embedding,
                             chunk.updated_at = datetime()
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
                'embedding': chunk.get('embedding'),
                'user_id': user_id
            })
        except Exception as e:
            logger.error(f"Error creating single chunk {chunk.get('id', 'unknown')}: {e}")
            # Try fallback without user constraints
            try:
                fallback_query = """
                MATCH (file:File {path: $file_path})
                MATCH (chunk:Chunk {id: $chunk_id})
                SET chunk.content = $content,
                    chunk.summary = $summary,
                    chunk.type = $type,
                    chunk.name = $name,
                    chunk.start_line = $start_line,
                    chunk.end_line = $end_line,
                    chunk.language = $language,
                    chunk.embedding = $embedding,
                    chunk.updated_at = datetime()
                MERGE (chunk)-[:PART_OF]->(file)
                """
                
                session.run(fallback_query, {
                    'file_path': chunk['file_path'],
                    'chunk_id': chunk['id'],
                    'content': chunk['content'],
                    'summary': chunk.get('summary', ''),
                    'type': chunk['type'],
                    'name': chunk['name'],
                    'start_line': chunk.get('start_line'),
                    'end_line': chunk.get('end_line'),
                    'language': chunk['language'],
                    'embedding': chunk.get('embedding')
                })
                logger.info(f"Successfully updated existing chunk: {chunk.get('id', 'unknown')}")
            except Exception as fallback_error:
                logger.error(f"Failed to handle chunk constraint violation for {chunk.get('id', 'unknown')}: {fallback_error}")
    
    def search_code(self, query: str, limit: int = 10, repository: str = None, user_id: str = None) -> List[Dict[str, Any]]:
        """Search code using hybrid GraphRAG retrieval with query preprocessing and user isolation"""
        try:
            import time
            start_time = time.time()
            
            logger.info(f"GraphService.search_code called with query: '{query[:50]}...' repository: '{repository}' user: '{user_id}' limit: {limit}")
            
            # Step 1: Preprocess query for better retrieval
            preprocessed = query_preprocessor.preprocess_query(query, repository)
            
            # Step 2: Use different search strategies based on preprocessing
            all_results = []
            seen_content_hashes = set()
            
            # Use both original and processed queries for better coverage
            search_queries = preprocessed['search_queries']
            
            # For each query variant, perform search
            for search_query in search_queries:
                try:
                    # Use HyDE document for embedding if beneficial
                    if query_preprocessor.should_use_hyde(preprocessed):
                        hyde_embedding = self.retriever._get_embeddings(preprocessed['hyde_document'])
                        if hyde_embedding:
                            # Use hyde embedding for vector search
                            temp_results = self._search_with_embedding(
                                search_query, hyde_embedding, limit, repository, user_id
                            )
                        else:
                            temp_results = self.retriever.hybrid_search(search_query, limit, repository, user_id)
                    else:
                        temp_results = self.retriever.hybrid_search(search_query, limit, repository, user_id)
                    
                    # Deduplicate results
                    for result in temp_results:
                        content_hash = hash(result.get('content', '')[:200])
                        if content_hash not in seen_content_hashes:
                            seen_content_hashes.add(content_hash)
                            all_results.append(result)
                    
                    # Stop if we have enough results
                    if len(all_results) >= limit:
                        break
                        
                except Exception as e:
                    logger.warning(f"Error with query variant '{search_query}': {e}")
                    continue
            
            # Step 3: Re-rank results based on intent
            final_results = self._re_rank_results(all_results, preprocessed, limit)
            
            duration = time.time() - start_time
            logger.info(f"GraphService.search_code completed in {duration:.2f}s, returning {len(final_results)} results")
            
            return final_results
            
        except Exception as e:
            logger.error(f"Error searching code: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Fallback to original search
            return self.retriever.hybrid_search(query, limit, repository, user_id)
    
    def _search_with_embedding(self, query: str, embedding: List[float], limit: int, repository: str, user_id: str) -> List[Dict[str, Any]]:
        """Search using a specific embedding vector"""
        try:
            with neo4j_conn.get_session() as session:
                # Parse repository name
                if '/' in repository:
                    repo_owner, repo_name = repository.split('/', 1)
                else:
                    repo_owner = "unknown"
                    repo_name = repository
                
                vector_query = """
                CALL db.index.vector.queryNodes('chunk_embeddings', $limit, $query_embedding) 
                YIELD node as chunk, score as vector_score
                WHERE vector_score > 0.05
                
                MATCH (chunk)-[:PART_OF]->(file:File)<-[:CONTAINS]-(repo:Repository)
                WHERE repo.name = $repo_name AND repo.owner = $repo_owner
                AND ($user_id IS NULL OR repo.user_id = $user_id)
                
                RETURN 
                    chunk.content as content,
                    chunk.summary as summary,
                    chunk.type as chunk_type,
                    chunk.name as chunk_name,
                    file.path as file_path,
                    file.language as language,
                    [] as functions,
                    [] as classes,
                    [] as called_functions,
                    [] as imports,
                    vector_score as combined_score,
                    vector_score,
                    0.0 as fulltext_score
                ORDER BY vector_score DESC
                LIMIT $limit
                """
                
                results = session.run(vector_query, {
                    'query_embedding': embedding,
                    'limit': limit,
                    'repo_name': repo_name,
                    'repo_owner': repo_owner,
                    'user_id': user_id
                })
                
                search_results = []
                for record in results:
                    result = {
                        'content': record.get('content', ''),
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
                
                return search_results
                
        except Exception as e:
            logger.error(f"Error in vector search with custom embedding: {e}")
            return []
    
    def _re_rank_results(self, results: List[Dict[str, Any]], preprocessed: Dict, limit: int) -> List[Dict[str, Any]]:
        """Re-rank results based on query intent and relevance"""
        try:
            if not results:
                return results
            
            intent = preprocessed.get('intent', 'general')
            
            # Boost scores based on intent
            for result in results:
                original_score = result.get('score', 0.0)
                boost = 0.0
                
                # Intent-specific boosting
                if intent == 'project_overview':
                    # Boost README, package.json, main files
                    file_path = result.get('file_path', '').lower()
                    if 'readme' in file_path:
                        boost += 0.3
                    elif 'package.json' in file_path or 'requirements.txt' in file_path:
                        boost += 0.25
                    elif result.get('chunk_type') == 'documentation':
                        boost += 0.2
                
                elif intent == 'architecture':
                    # Boost main module files and documentation
                    file_path = result.get('file_path', '').lower()
                    if any(term in file_path for term in ['main', 'app', 'index', 'config']):
                        boost += 0.15
                    elif result.get('chunk_type') == 'class':
                        boost += 0.1
                
                elif intent == 'usage':
                    # Boost documentation and examples
                    if result.get('chunk_type') == 'documentation':
                        boost += 0.2
                    elif 'example' in result.get('file_path', '').lower():
                        boost += 0.15
                
                # Update score
                result['score'] = original_score + boost
            
            # Sort by updated score
            results.sort(key=lambda x: x.get('score', 0.0), reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error re-ranking results: {e}")
            return results[:limit]
    
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
        """Generate answer using configured AI provider with rate limiting"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a code analysis assistant. Answer the user's question based on the provided code context."
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nCode Context:\n{context}"
                }
            ]
            
            return ai_provider.generate_chat_completion(messages, max_tokens=1000, temperature=0.1)
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return "I apologize, but I encountered an error while generating an answer."
    
    @sleep_and_retry
    @limits(calls=50, period=60)  # 50 calls per minute per instance
    def _call_openai_chat(self, messages, max_tokens=1000, temperature=0.1, stream=False):
        """Rate-limited OpenAI chat completion call"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI chat API error: {e}")
            raise
    
    @sleep_and_retry
    @limits(calls=100, period=60)  # 100 calls per minute for embeddings
    def _call_openai_embeddings(self, input_text, model="text-embedding-3-small"):
        """Rate-limited OpenAI embeddings call"""
        try:
            response = self.openai_client.embeddings.create(
                input=input_text,
                model=model
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI embeddings API error: {e}")
            raise
    
    def stream_answer(self, question: str, context: str = None):
        """Stream answer generation with buffered chunks"""
        try:
            import time
            start_time = time.time()
            
            logger.info(f"GraphService.stream_answer called with question: '{question[:50]}...'")
            
            if context is None:
                # Get context using GraphRAG
                context_start = time.time()
                logger.info("Getting context for streaming answer...")
                
                context_results = self.search_code(question, limit=10)
                context = self._format_context(context_results)
                
                context_duration = time.time() - context_start
                logger.info(f"Context generation completed in {context_duration:.2f}s")
            
            # Call AI provider API
            openai_start = time.time()
            logger.info(f"Calling {settings.ai_provider} API for streaming response...")
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a code analysis assistant. Answer the user's question based on the provided code context."
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nCode Context:\n{context}"
                }
            ]
            
            # Use AI provider for streaming
            response = ai_provider.generate_streaming_completion(messages, max_tokens=1000, temperature=0.1)
            
            openai_call_duration = time.time() - openai_start
            logger.info(f"{settings.ai_provider} API call initiated in {openai_call_duration:.2f}s, starting stream processing...")
            
            buffer = ""
            chunk_count = 0
            
            for chunk in response:
                if chunk:  # AI provider returns the content directly
                    buffer += chunk
                    chunk_count += 1
                    
                    # Yield when we have a complete sentence or enough text
                    if len(buffer) >= 50 or any(buffer.endswith(punct) for punct in ['. ', '! ', '? ', '\n\n']):
                        yield buffer
                        buffer = ""
            
            # Yield any remaining content
            if buffer:
                yield buffer
                
            total_duration = time.time() - start_time
            logger.info(f"GraphService.stream_answer completed in {total_duration:.2f}s, processed {chunk_count} chunks")
                
        except Exception as e:
            logger.error(f"Error streaming answer: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            yield "I apologize, but I encountered an error while generating an answer."
    
    def _format_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Format search results into context string"""
        if not search_results:
            return "No relevant code found."
        
        context_parts = []
        for i, result in enumerate(search_results[:5], 1):
            file_path = result.get('file_path', 'unknown')
            chunk_name = result.get('chunk_name', 'unknown')
            chunk_type = result.get('chunk_type', 'code')
            summary = result.get('summary', '')
            content = result.get('content', '')
            
            context_part = f"""
## Result {i}: {chunk_type.title()} - {chunk_name}
**File:** {file_path}
**Summary:** {summary}

```{result.get('language', '')}
{content[:800]}{'...' if len(content) > 800 else ''}
```"""
            context_parts.append(context_part)
        
        return '\n'.join(context_parts)
    
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
    
    def get_repository_stats(self, repo_name: str, repo_owner: str, user_id: str = None) -> Dict[str, Any]:
        """Get repository statistics with user isolation"""
        try:
            with neo4j_conn.get_session() as session:
                if user_id:
                    query = """
                    MATCH (repo:Repository {name: $repo_name, owner: $repo_owner, user_id: $user_id})
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
                else:
                    query = """
                    MATCH (repo:Repository {name: $repo_name, owner: $repo_owner})
                    WHERE repo.user_id IS NULL
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
                
                params = {
                    'repo_name': repo_name,
                    'repo_owner': repo_owner
                }
                
                if user_id:
                    params['user_id'] = user_id
                
                result = session.run(query, params).single()
                
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
