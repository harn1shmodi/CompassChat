#!/usr/bin/env python3
"""
Optimized Code Summarizer
Implements OpenAI API best practices for processing large batches of code chunks:
- Async concurrent processing with rate limiting
- Batch processing to reduce API calls
- Exponential backoff for rate limit handling
- Structured outputs for reliable parsing
- Cache optimization
- Memory-efficient streaming
"""

import asyncio
import aiohttp
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from openai import AsyncOpenAI
from core.config import settings
from services.embedding_cache import embedding_cache
from tenacity import retry, stop_after_attempt, wait_random_exponential
import json

logger = logging.getLogger(__name__)


@dataclass
class SummarizationRequest:
    """Stores a summarization request with metadata"""
    task_id: int
    chunks: List[Dict[str, Any]]
    attempts_left: int = 3
    result: Optional[List[str]] = None
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


class OptimizedCodeSummarizer:
    """High-performance code summarizer with async processing and rate limiting"""
    
    def __init__(self, 
                 max_requests_per_minute: int = 3000,
                 max_tokens_per_minute: int = 2000000, 
                 batch_size: int = 10,
                 max_concurrent: int = 50):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"
        
        # Rate limiting parameters
        self.max_requests_per_minute = max_requests_per_minute
        self.max_tokens_per_minute = max_tokens_per_minute
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        
        # Tracking
        self.available_request_capacity = max_requests_per_minute
        self.available_token_capacity = max_tokens_per_minute
        self.last_update_time = time.time()
        
        # Constants
        self.seconds_to_pause_after_rate_limit = 15
        self.seconds_to_sleep_each_loop = 0.001  # 1ms
    
    async def summarize_chunks_optimized(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Optimized chunk summarization using async processing with rate limiting
        """
        logger.info(f"Starting optimized summarization of {len(chunks)} chunks")
        
        # Filter out chunks that already have cached summaries
        chunks_to_process = []
        for chunk in chunks:
            cached_summary = embedding_cache.get_summary(chunk.get('content', ''))
            if cached_summary:
                chunk['summary'] = cached_summary
            else:
                chunks_to_process.append(chunk)
        
        logger.info(f"Found {len(chunks) - len(chunks_to_process)} cached summaries")
        logger.info(f"Processing {len(chunks_to_process)} chunks")
        
        if not chunks_to_process:
            return chunks
        
        # Create batches for processing
        batches = self._create_batches(chunks_to_process)
        logger.info(f"Created {len(batches)} batches of size {self.batch_size}")
        
        # Process batches with rate limiting
        processed_batches = await self._process_batches_async(batches)
        
        # Merge results back into original chunks
        chunk_idx = 0
        for chunk in chunks:
            if not chunk.get('summary'):  # If not cached
                if chunk_idx < len(chunks_to_process):
                    processed_chunk = next(
                        (c for batch in processed_batches for c in batch if c.get('content') == chunk.get('content')), 
                        None
                    )
                    if processed_chunk and processed_chunk.get('summary'):
                        chunk['summary'] = processed_chunk['summary']
                        # Cache the new summary
                        embedding_cache.set_summary(chunk.get('content', ''), chunk['summary'])
                    else:
                        chunk['summary'] = self._fallback_summary(chunk)
                    chunk_idx += 1
        
        logger.info(f"Completed summarization of {len(chunks)} chunks")
        return chunks
    
    def _create_batches(self, chunks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Create optimally sized batches"""
        batches = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i + self.batch_size]
            batches.append(batch)
        return batches
    
    async def _process_batches_async(self, batches: List[List[Dict[str, Any]]]) -> List[List[Dict[str, Any]]]:
        """Process batches with async rate limiting"""
        # Create request queue
        request_queue = asyncio.Queue()
        
        # Add all batches to queue
        for i, batch in enumerate(batches):
            request = SummarizationRequest(task_id=i, chunks=batch)
            await request_queue.put(request)
        
        # Track status
        status_tracker = StatusTracker()
        status_tracker.num_tasks_started = len(batches)
        status_tracker.num_tasks_in_progress = len(batches)
        
        # Process with rate limiting
        results = {}
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def worker():
            while status_tracker.num_tasks_in_progress > 0:
                # Update capacity
                self._update_capacity()
                
                try:
                    # Get next request
                    request = await asyncio.wait_for(request_queue.get(), timeout=0.1)
                    
                    # Check if we have capacity
                    estimated_tokens = self._estimate_tokens(request.chunks)
                    
                    if (self.available_request_capacity >= 1 and 
                        self.available_token_capacity >= estimated_tokens):
                        
                        # Use capacity
                        self.available_request_capacity -= 1
                        self.available_token_capacity -= estimated_tokens
                        
                        # Process the batch
                        async with semaphore:
                            await self._process_single_batch(request, status_tracker, results)
                    else:
                        # Put request back and wait
                        await request_queue.put(request)
                        await asyncio.sleep(self.seconds_to_sleep_each_loop)
                        
                except asyncio.TimeoutError:
                    await asyncio.sleep(self.seconds_to_sleep_each_loop)
                except Exception as e:
                    logger.error(f"Worker error: {e}")
        
        # Start workers
        workers = [asyncio.create_task(worker()) for _ in range(min(10, len(batches)))]
        
        # Wait for completion
        while status_tracker.num_tasks_in_progress > 0:
            await asyncio.sleep(0.1)
        
        # Cancel workers
        for worker_task in workers:
            worker_task.cancel()
        
        # Combine results in order
        processed_batches = []
        for i in range(len(batches)):
            if i in results:
                processed_batches.append(results[i])
            else:
                # Fallback for failed batches
                fallback_batch = []
                for chunk in batches[i]:
                    chunk['summary'] = self._fallback_summary(chunk)
                    fallback_batch.append(chunk)
                processed_batches.append(fallback_batch)
        
        logger.info(f"Processed {len(processed_batches)} batches. "
                   f"Success: {status_tracker.num_tasks_succeeded}, "
                   f"Failed: {status_tracker.num_tasks_failed}")
        
        return processed_batches
    
    def _update_capacity(self):
        """Update available API capacity"""
        current_time = time.time()
        seconds_since_update = current_time - self.last_update_time
        
        self.available_request_capacity = min(
            self.available_request_capacity + self.max_requests_per_minute * seconds_since_update / 60.0,
            self.max_requests_per_minute
        )
        
        self.available_token_capacity = min(
            self.available_token_capacity + self.max_tokens_per_minute * seconds_since_update / 60.0,
            self.max_tokens_per_minute
        )
        
        self.last_update_time = current_time
    
    def _estimate_tokens(self, chunks: List[Dict[str, Any]]) -> int:
        """Estimate token usage for a batch"""
        # Rough estimation: ~4 chars per token, plus overhead
        total_chars = sum(len(chunk.get('content', '')[:800]) for chunk in chunks)
        prompt_tokens = total_chars // 4 + 200  # Base prompt overhead
        completion_tokens = 100 * len(chunks)  # ~100 tokens per summary
        return prompt_tokens + completion_tokens
    
    async def _process_single_batch(self, request: SummarizationRequest, 
                                  status_tracker: StatusTracker, 
                                  results: Dict[int, List[Dict[str, Any]]]):
        """Process a single batch with retries"""
        try:
            summaries = await self._batch_summarize_async(request.chunks)
            
            # Apply summaries to chunks
            for chunk, summary in zip(request.chunks, summaries):
                chunk['summary'] = summary
            
            results[request.task_id] = request.chunks
            status_tracker.num_tasks_succeeded += 1
            status_tracker.num_tasks_in_progress -= 1
            
        except Exception as e:
            logger.error(f"Failed to process batch {request.task_id}: {e}")
            
            if "rate limit" in str(e).lower():
                status_tracker.num_rate_limit_errors += 1
                status_tracker.time_of_last_rate_limit_error = time.time()
                
                # Wait for rate limit to reset
                await asyncio.sleep(self.seconds_to_pause_after_rate_limit)
            
            request.attempts_left -= 1
            if request.attempts_left > 0:
                # Retry
                await asyncio.sleep(1)  # Brief delay before retry
                await self._process_single_batch(request, status_tracker, results)
            else:
                # Give up, use fallback
                for chunk in request.chunks:
                    chunk['summary'] = self._fallback_summary(chunk)
                results[request.task_id] = request.chunks
                status_tracker.num_tasks_failed += 1
                status_tracker.num_tasks_in_progress -= 1
    
    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
    async def _batch_summarize_async(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """Async batch summarization with structured output"""
        try:
            # Create optimized batch prompt
            batch_prompt = self._create_batch_prompt(chunks)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a code analysis expert. Provide concise, technical summaries that capture purpose, functionality, and key implementation details. Respond with exactly the requested number of summaries in the specified format."
                    },
                    {
                        "role": "user", 
                        "content": batch_prompt
                    }
                ],
                max_tokens=min(150 * len(chunks), 4000),  # Cap at model limit
                temperature=0.1,
                timeout=30.0  # Add timeout
            )
            
            # Parse response
            summaries = self._parse_batch_summaries(response.choices[0].message.content, len(chunks))
            
            # Ensure we have the right number of summaries
            while len(summaries) < len(chunks):
                summaries.append("Code component analysis")
            
            return summaries[:len(chunks)]
            
        except Exception as e:
            logger.error(f"Error in async batch summarization: {e}")
            raise
    
    def _create_batch_prompt(self, chunks: List[Dict[str, Any]]) -> str:
        """Create optimized batch prompt"""
        prompt = f"Analyze these {len(chunks)} code chunks and provide a concise summary for each:\n\n"
        
        for i, chunk in enumerate(chunks, 1):
            chunk_type = chunk.get('type', 'code')
            content = chunk.get('content', '')[:600]  # Limit to reduce tokens
            name = chunk.get('name', 'unknown')
            language = chunk.get('language', '')
            
            prompt += f"CHUNK {i} ({chunk_type}):\n"
            if name != 'unknown':
                prompt += f"Name: {name}\n"
            if language:
                prompt += f"Language: {language}\n"
            prompt += f"```\n{content}\n```\n\n"
        
        prompt += f"Provide exactly {len(chunks)} summaries in this format:\n"
        prompt += "1: [concise summary]\n"
        prompt += "2: [concise summary]\n"
        prompt += "...\n"
        
        return prompt
    
    def _parse_batch_summaries(self, response: str, expected_count: int) -> List[str]:
        """Parse batch response with multiple fallback strategies"""
        summaries = []
        
        # Strategy 1: Look for numbered format "1: summary"
        lines = response.strip().split('\n')
        for line in lines:
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0].strip().isdigit():
                    summaries.append(parts[1].strip())
        
        # Strategy 2: Look for SUMMARY format
        if len(summaries) < expected_count:
            summaries = []
            for line in lines:
                if line.startswith('SUMMARY ') and ':' in line:
                    summary = line.split(':', 1)[1].strip()
                    summaries.append(summary)
        
        # Strategy 3: Split by sentences if still not enough
        if len(summaries) < expected_count:
            sentences = response.replace('\n', ' ').split('.')
            summaries = [s.strip() + '.' for s in sentences if s.strip()]
        
        return summaries
    
    def _fallback_summary(self, chunk: Dict[str, Any]) -> str:
        """Generate fallback summary when API fails"""
        chunk_type = chunk.get('type', 'code')
        name = chunk.get('name', 'unknown')
        language = chunk.get('language', '')
        
        if chunk_type == 'function':
            return f"Function `{name}` written in {language}"
        elif chunk_type == 'class':
            return f"Class `{name}` definition in {language}"
        else:
            return f"Code component in {language}"


# Backwards compatibility wrapper
class CodeSummarizer:
    """Wrapper to maintain compatibility with existing code"""
    
    def __init__(self):
        self.optimized = OptimizedCodeSummarizer()
    
    def summarize_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 10) -> List[Dict[str, Any]]:
        """Synchronous wrapper for async processing"""
        return asyncio.run(self.optimized.summarize_chunks_optimized(chunks))
    
    def summarize_chunk(self, chunk: Dict[str, Any]) -> str:
        """Summarize single chunk"""
        result = self.summarize_chunks([chunk])
        return result[0].get('summary', self.optimized._fallback_summary(chunk))
