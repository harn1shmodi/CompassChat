#!/usr/bin/env python3
"""
Optimized Embedding Service
Implements OpenAI API best practices for processing large batches of embeddings:
- Async concurrent processing with rate limiting
- Batch processing to reduce API calls (up to 2048 texts per call)
- Exponential backoff for rate limit handling
- Memory-efficient processing
- Deduplication to avoid redundant embeddings
- Cache optimization
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from openai import AsyncOpenAI
from core.config import settings
from services.embedding_cache import embedding_cache
from tenacity import retry, stop_after_attempt, wait_random_exponential
import hashlib
import json
import tiktoken

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingRequest:
    """Stores an embedding request with metadata"""
    task_id: int
    texts: List[str]
    chunk_ids: List[str]
    attempts_left: int = 3
    result: Optional[List[List[float]]] = None
    error: Optional[str] = None


@dataclass
class StatusTracker:
    """Tracks processing status"""
    num_tasks_started: int = 0
    num_tasks_in_progress: int = 0
    num_tasks_succeeded: int = 0
    num_tasks_failed: int = 0
    num_rate_limit_errors: int = 0
    time_of_last_rate_limit_error: float = 0


class OptimizedEmbeddingService:
    """High-performance embedding service with async processing and rate limiting"""
    
    def __init__(self, 
                 max_concurrent: int = None,
                 batch_size: int = None,
                 requests_per_minute: int = None,
                 enable_cache: bool = True):
        """
        Initialize the optimized embedding service
        
        Args:
            max_concurrent: Maximum concurrent API requests (from config if None)
            batch_size: Number of texts per batch (from config if None, max 2048 for OpenAI)
            requests_per_minute: Rate limit for API calls (from config if None)
            enable_cache: Whether to use Redis caching
        """
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.max_concurrent = max_concurrent or settings.embedding_max_concurrent
        self.batch_size = min(batch_size or settings.embedding_batch_size, 2048)  # OpenAI limit
        self.requests_per_minute = requests_per_minute or settings.embedding_requests_per_minute
        self.enable_cache = enable_cache
        
        # Token counting
        try:
            self.tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")
        except Exception as e:
            logger.warning(f"Failed to load tokenizer, using fallback: {e}")
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Rate limiting
        self.request_interval = 60.0 / self.requests_per_minute
        self.last_request_time = 0.0
        
        logger.info(f"Initialized OptimizedEmbeddingService: batch_size={self.batch_size}, "
                   f"max_concurrent={self.max_concurrent}, requests_per_minute={self.requests_per_minute}")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken"""
        try:
            return len(self.tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Error counting tokens, using estimate: {e}")
            return len(text) // 4  # Rough estimate: 1 token ≈ 4 characters
    
    def chunk_oversized_text(self, text: str, max_tokens: int = 8000, overlap: int = 100) -> List[str]:
        """Split oversized text into smaller chunks that fit within token limit"""
        if not text:
            return []
        
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return [text]
        
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
            
            if end >= len(tokens):
                break
            
            # Move start position with overlap
            start = max(0, end - overlap)
        
        logger.debug(f"Split oversized text ({len(tokens)} tokens) into {len(chunks)} chunks")
        return chunks
    
    async def generate_embeddings_for_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate embeddings for a list of chunks efficiently
        
        Args:
            chunks: List of chunk dictionaries with 'content' and 'id' fields
            
        Returns:
            List of chunks with 'embedding' field added
        """
        if not chunks:
            return chunks
        
        logger.info(f"Starting embedding generation for {len(chunks)} chunks")
        start_time = time.time()
        
        # Step 1: Check cache and deduplicate
        chunks_to_process, cache_hits = self._check_cache_and_deduplicate(chunks)
        
        if not chunks_to_process:
            logger.info(f"All {len(chunks)} embeddings found in cache!")
            return chunks
        
        logger.info(f"Cache hits: {cache_hits}/{len(chunks)}, processing {len(chunks_to_process)} unique texts")
        
        # Step 2: Create batches
        batches = self._create_batches(chunks_to_process)
        logger.info(f"Created {len(batches)} batches for processing")
        
        # Step 3: Process batches asynchronously
        processed_batches = await self._process_batches_async(batches, len(chunks))
        
        # Step 4: Merge results back into original chunks
        self._merge_results(chunks, processed_batches)
        
        # Step 5: Cache new embeddings
        self._cache_new_embeddings(chunks)
        
        elapsed_time = time.time() - start_time
        logger.info(f"Completed embedding generation for {len(chunks)} chunks in {elapsed_time:.2f}s")
        
        return chunks
    
    def _check_cache_and_deduplicate(self, chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """Check cache and deduplicate texts to minimize API calls"""
        chunks_to_process = []
        cache_hits = 0
        seen_content = {}
        
        for chunk in chunks:
            content = chunk.get('content', '')
            if not content:
                continue
            
            # Check cache first
            if self.enable_cache:
                cached_embedding = embedding_cache.get_embedding(content)
                if cached_embedding:
                    chunk['embedding'] = cached_embedding
                    cache_hits += 1
                    continue
            
            # Deduplicate identical content
            content_hash = hashlib.md5(content.encode()).hexdigest()
            if content_hash in seen_content:
                # This content was already processed, we'll copy the embedding later
                seen_content[content_hash]['duplicate_chunks'].append(chunk)
            else:
                # New content to process
                seen_content[content_hash] = {
                    'chunk': chunk,
                    'duplicate_chunks': []
                }
                chunks_to_process.append(chunk)
        
        return chunks_to_process, cache_hits
    
    def _create_batches(self, chunks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Create optimally sized batches for API calls with oversized chunk handling"""
        batches = []
        
        # Process chunks, handling oversized ones
        processed_chunks = []
        for chunk in chunks:
            content = chunk.get('content', '')
            if not content:
                continue
                
            token_count = self.count_tokens(content)
            
            if token_count <= 8000:  # Safe limit for OpenAI
                processed_chunks.append(chunk)
            else:
                # Split oversized chunk
                logger.warning(f"Chunk {chunk.get('id', 'unknown')} has {token_count} tokens, splitting...")
                split_chunks = self.chunk_oversized_text(content, max_tokens=7500, overlap=200)
                
                for i, split_text in enumerate(split_chunks):
                    split_chunk = chunk.copy()
                    split_chunk['content'] = split_text
                    split_chunk['id'] = f"{chunk.get('id', 'unknown')}_split_{i}"
                    split_chunk['original_chunk_id'] = chunk.get('id', 'unknown')
                    split_chunk['split_index'] = i
                    split_chunk['total_splits'] = len(split_chunks)
                    processed_chunks.append(split_chunk)
        
        # Create batches from processed chunks
        current_batch = []
        current_batch_tokens = 0
        
        for chunk in processed_chunks:
            content = chunk.get('content', '')
            token_count = self.count_tokens(content)
            
            # Check if adding this chunk would exceed limits
            if (len(current_batch) >= self.batch_size or 
                current_batch_tokens + token_count > 7500):  # Conservative limit
                
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_batch_tokens = 0
            
            current_batch.append(chunk)
            current_batch_tokens += token_count
        
        if current_batch:
            batches.append(current_batch)
        
        logger.info(f"Created {len(batches)} batches from {len(processed_chunks)} processed chunks")
        return batches
    
    async def _process_batches_async(self, batches: List[List[Dict[str, Any]]], total_chunks: int) -> List[List[Dict[str, Any]]]:
        """Process batches with async rate limiting"""
        if not batches:
            return []
        
        # Create request queue
        request_queue = asyncio.Queue()
        
        # Add all batches to queue
        for i, batch in enumerate(batches):
            texts = [chunk.get('content', '') for chunk in batch]
            chunk_ids = [chunk.get('id', f'chunk_{i}_{j}') for j, chunk in enumerate(batch)]
            request = EmbeddingRequest(task_id=i, texts=texts, chunk_ids=chunk_ids)
            await request_queue.put(request)
        
        # Track status
        status_tracker = StatusTracker()
        status_tracker.num_tasks_started = len(batches)
        status_tracker.num_tasks_in_progress = len(batches)
        
        # Process with rate limiting
        results = {}
        semaphore = asyncio.Semaphore(self.max_concurrent)
        processed_chunks = 0
        
        async def worker():
            nonlocal processed_chunks
            while True:
                request = await request_queue.get()
                async with semaphore:
                    await self._process_single_batch(request, status_tracker)
                    results[request.task_id] = request
                    
                    # Progress reporting
                    processed_chunks += len(request.texts)
                    progress = (processed_chunks / total_chunks) * 100
                    if processed_chunks % 500 == 0 or processed_chunks == total_chunks:
                        logger.info(f"Embedding progress: {processed_chunks}/{total_chunks} chunks ({progress:.1f}%)")
                    
                    request_queue.task_done()
        
        # Start workers
        workers = [asyncio.create_task(worker()) for _ in range(self.max_concurrent)]
        
        # Wait for all tasks to complete
        await request_queue.join()
        
        # Cancel workers
        for worker in workers:
            worker.cancel()
        
        # Collect results in order
        processed_batches = []
        for i in range(len(batches)):
            if i in results and results[i].result:
                batch = batches[i]
                embeddings = results[i].result
                
                # Add embeddings to chunks
                for chunk, embedding in zip(batch, embeddings):
                    chunk['embedding'] = embedding
                
                processed_batches.append(batch)
            else:
                # Failed batch, add without embeddings
                processed_batches.append(batches[i])
        
        logger.info(f"Batch processing completed: {status_tracker.num_tasks_succeeded} succeeded, "
                   f"{status_tracker.num_tasks_failed} failed, "
                   f"{status_tracker.num_rate_limit_errors} rate limited")
        
        return processed_batches
    
    async def _process_single_batch(self, request: EmbeddingRequest, status_tracker: StatusTracker):
        """Process a single batch of embeddings with sophisticated error handling"""
        if not request.texts:
            request.result = []
            return
        
        max_retries = 3
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Rate limiting
                await self._rate_limit()
                
                # Make API call
                response = await self.client.embeddings.create(
                    model="text-embedding-3-small",
                    input=request.texts
                )
                
                # Extract embeddings
                embeddings = [data.embedding for data in response.data]
                request.result = embeddings
                
                status_tracker.num_tasks_succeeded += 1
                status_tracker.num_tasks_in_progress -= 1
                
                logger.debug(f"Batch {request.task_id}: Generated {len(embeddings)} embeddings")
                return
                
            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"Batch {request.task_id} attempt {attempt + 1} failed: {e}")
                
                # Handle token limit errors
                if "maximum context length" in error_msg or "too many tokens" in error_msg:
                    logger.warning(f"Token limit exceeded for batch {request.task_id}, attempting to split...")
                    
                    # Split oversized texts and retry
                    split_texts = []
                    split_chunk_ids = []
                    
                    for text, chunk_id in zip(request.texts, request.chunk_ids):
                        token_count = self.count_tokens(text)
                        
                        if token_count > 8000:  # Token limit
                            # Split this oversized text
                            chunks = self.chunk_oversized_text(text, max_tokens=7500, overlap=200)
                            for i, chunk_text in enumerate(chunks):
                                split_texts.append(chunk_text)
                                split_chunk_ids.append(f"{chunk_id}_retry_split_{i}")
                        else:
                            split_texts.append(text)
                            split_chunk_ids.append(chunk_id)
                    
                    if len(split_texts) > len(request.texts):
                        logger.info(f"Split {len(request.texts)} texts into {len(split_texts)} smaller chunks")
                        request.texts = split_texts
                        request.chunk_ids = split_chunk_ids
                        
                        # Recursively process the split batches
                        if attempt < max_retries - 1:
                            await asyncio.sleep(base_delay * (2 ** attempt))
                            continue
                
                # Handle rate limit errors
                elif "rate limit" in error_msg:
                    status_tracker.num_rate_limit_errors += 1
                    status_tracker.time_of_last_rate_limit_error = time.time()
                    
                    if attempt < max_retries - 1:
                        delay = base_delay * (4 ** attempt)  # More aggressive backoff for rate limits
                        logger.info(f"Rate limit hit, waiting {delay}s before retry {attempt + 1}")
                        await asyncio.sleep(delay)
                        continue
                
                # Handle other errors
                else:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.info(f"Retrying batch {request.task_id} after {delay}s delay")
                        await asyncio.sleep(delay)
                        continue
                
                # All retries exhausted
                logger.error(f"Batch {request.task_id} failed after {max_retries} attempts")
                request.error = str(e)
                status_tracker.num_tasks_failed += 1
                status_tracker.num_tasks_in_progress -= 1
                return
    
    async def _rate_limit(self):
        """Implement rate limiting between API calls"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.request_interval:
            sleep_time = self.request_interval - time_since_last_request
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _merge_results(self, original_chunks: List[Dict[str, Any]], processed_batches: List[List[Dict[str, Any]]]):
        """Merge processed results back into original chunks, handling split chunks"""
        # Create mappings for split chunks
        original_embeddings = {}
        split_embeddings = {}
        
        for batch in processed_batches:
            for chunk in batch:
                if 'embedding' in chunk:
                    chunk_id = chunk.get('id', '')
                    original_chunk_id = chunk.get('original_chunk_id')
                    
                    if original_chunk_id:
                        # This is a split chunk
                        if original_chunk_id not in split_embeddings:
                            split_embeddings[original_chunk_id] = []
                        split_embeddings[original_chunk_id].append({
                            'embedding': chunk['embedding'],
                            'split_index': chunk.get('split_index', 0),
                            'content': chunk.get('content', '')
                        })
                    else:
                        # This is an original chunk
                        original_embeddings[chunk_id] = chunk['embedding']
        
        # Apply embeddings to original chunks
        for chunk in original_chunks:
            chunk_id = chunk.get('id', '')
            
            if chunk_id in original_embeddings:
                # Direct embedding
                chunk['embedding'] = original_embeddings[chunk_id]
            elif chunk_id in split_embeddings:
                # Merge split chunk embeddings using averaging
                split_data = split_embeddings[chunk_id]
                split_data.sort(key=lambda x: x['split_index'])
                
                # Average the embeddings
                if split_data:
                    import numpy as np
                    embeddings = [data['embedding'] for data in split_data]
                    averaged_embedding = np.mean(embeddings, axis=0).tolist()
                    chunk['embedding'] = averaged_embedding
                    
                    # Store split metadata for debugging
                    chunk['split_chunks_processed'] = len(split_data)
                    chunk['split_chunk_embeddings'] = embeddings
            elif 'embedding' not in chunk:
                # Try content-based matching for deduplication
                content = chunk.get('content', '')
                for emb_content, embedding in original_embeddings.items():
                    if content == emb_content:
                        chunk['embedding'] = embedding
                        break
    
    def _cache_new_embeddings(self, chunks: List[Dict[str, Any]]):
        """Cache newly generated embeddings"""
        if not self.enable_cache:
            return
        
        cached_count = 0
        for chunk in chunks:
            if 'embedding' in chunk:
                content = chunk.get('content', '')
                embedding = chunk['embedding']
                if content and embedding:
                    embedding_cache.set_embedding(content, embedding)
                    cached_count += 1
        
        logger.info(f"Cached {cached_count} new embeddings")


# Global instance
optimized_embedding_service = OptimizedEmbeddingService()