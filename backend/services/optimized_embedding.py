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
                 max_concurrent: int = 5,
                 batch_size: int = 100,  # Conservative batch size to stay under token limits
                 requests_per_minute: int = 300,
                 enable_cache: bool = True):
        """
        Initialize the optimized embedding service
        
        Args:
            max_concurrent: Maximum concurrent API requests
            batch_size: Number of texts per batch (max 2048 for OpenAI)
            requests_per_minute: Rate limit for API calls
            enable_cache: Whether to use Redis caching
        """
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.max_concurrent = max_concurrent
        self.batch_size = min(batch_size, 2048)  # OpenAI limit
        self.requests_per_minute = requests_per_minute
        self.enable_cache = enable_cache
        
        # Rate limiting
        self.request_interval = 60.0 / requests_per_minute
        self.last_request_time = 0.0
        
        logger.info(f"Initialized OptimizedEmbeddingService: batch_size={self.batch_size}, "
                   f"max_concurrent={self.max_concurrent}, requests_per_minute={self.requests_per_minute}")
    
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
        processed_batches = await self._process_batches_async(batches)
        
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
        """Create optimally sized batches for API calls"""
        batches = []
        current_batch = []
        current_batch_tokens = 0
        
        for chunk in chunks:
            content = chunk.get('content', '')
            # Rough token estimate (1 token ≈ 4 characters)
            estimated_tokens = len(content) // 4
            
            # Check if adding this chunk would exceed limits
            if (len(current_batch) >= self.batch_size or 
                current_batch_tokens + estimated_tokens > 8000):  # Conservative token limit
                
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_batch_tokens = 0
            
            current_batch.append(chunk)
            current_batch_tokens += estimated_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    async def _process_batches_async(self, batches: List[List[Dict[str, Any]]]) -> List[List[Dict[str, Any]]]:
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
        
        async def worker():
            while True:
                request = await request_queue.get()
                async with semaphore:
                    await self._process_single_batch(request, status_tracker)
                    results[request.task_id] = request
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
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=1, max=60),
        retry_error_callback=lambda retry_state: logger.warning(f"Embedding API retry {retry_state.attempt_number}")
    )
    async def _process_single_batch(self, request: EmbeddingRequest, status_tracker: StatusTracker):
        """Process a single batch of embeddings with retry logic"""
        if not request.texts:
            request.result = []
            return
        
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
            
        except Exception as e:
            logger.error(f"Batch {request.task_id} failed: {e}")
            request.error = str(e)
            request.attempts_left -= 1
            
            if "rate limit" in str(e).lower():
                status_tracker.num_rate_limit_errors += 1
                status_tracker.time_of_last_rate_limit_error = time.time()
            
            status_tracker.num_tasks_failed += 1
            status_tracker.num_tasks_in_progress -= 1
            
            if request.attempts_left > 0:
                # Exponential backoff for retries
                await asyncio.sleep(2 ** (3 - request.attempts_left))
                raise  # This will trigger the retry decorator
    
    async def _rate_limit(self):
        """Implement rate limiting between API calls"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.request_interval:
            sleep_time = self.request_interval - time_since_last_request
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _merge_results(self, original_chunks: List[Dict[str, Any]], processed_batches: List[List[Dict[str, Any]]]):
        """Merge processed results back into original chunks"""
        # Create a mapping of content to embedding for processed chunks
        content_to_embedding = {}
        for batch in processed_batches:
            for chunk in batch:
                if 'embedding' in chunk:
                    content = chunk.get('content', '')
                    content_to_embedding[content] = chunk['embedding']
        
        # Apply embeddings to original chunks (handles deduplication)
        for chunk in original_chunks:
            if 'embedding' not in chunk:  # Not from cache
                content = chunk.get('content', '')
                if content in content_to_embedding:
                    chunk['embedding'] = content_to_embedding[content]
    
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