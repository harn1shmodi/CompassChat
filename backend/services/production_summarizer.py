#!/usr/bin/env python3
"""
Production-ready summarization service with intelligent selection
Drop-in replacement for existing summarizer
"""

import asyncio
import logging
from typing import List, Dict, Any
from services.optimized_summarizer import OptimizedCodeSummarizer
from services.intelligent_selector import chunk_selector, SelectionStrategy, SelectionCriteria
from core.config import settings

logger = logging.getLogger(__name__)


class ProductionSummarizationService:
    """Production-ready summarization with intelligent selection"""
    
    def __init__(self):
        self.traditional_summarizer = OptimizedCodeSummarizer()
        
    async def summarize_chunks_intelligently(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Intelligent summarization with automatic selection
        Drop-in replacement for existing summarizer
        """
        if not chunks:
            return chunks
            
        logger.info(f"Starting intelligent summarization for {len(chunks)} chunks")
        
        # Step 1: Select important chunks
        if getattr(settings, 'enable_intelligent_selection', True):
            selected_chunks = self._select_important_chunks(chunks)
            logger.info(f"Selected {len(selected_chunks)} chunks for AI summarization")
        else:
            selected_chunks = chunks
            
        # Step 2: AI summarization for selected chunks
        if selected_chunks:
            summarized_chunks = await self.traditional_summarizer.summarize_chunks_optimized(selected_chunks)
        else:
            summarized_chunks = []
            
        # Step 3: Simple summaries for unselected chunks
        self._add_simple_summaries(chunks, summarized_chunks)
        
        logger.info(f"Completed intelligent summarization for {len(chunks)} chunks")
        return chunks
    
    def _select_important_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select important chunks for AI summarization"""
        
        # Get selection parameters from config
        selection_percentage = getattr(settings, 'selection_percentage', 0.3)
        max_chunks_by_percentage = int(len(chunks) * selection_percentage)
        
        # Apply hard cap of 200 batches (API calls)
        max_batch_cap = getattr(settings, 'max_summarization_batches', 200)
        max_chunks = min(max_chunks_by_percentage, max_batch_cap)
        
        logger.info(f"Selection limits: {max_chunks_by_percentage} by percentage (30%), {max_batch_cap} by cap - using {max_chunks}")
        
        # Set up selection criteria
        criteria = SelectionCriteria(
            max_chunks=max_chunks,
            exclude_patterns=["test/", "mock/", "example/"] if getattr(settings, 'exclude_test_files', True) else [],
            prioritize_public_apis=True,
            prioritize_entry_points=True,
            min_importance="medium"
        )
        
        # Select chunks based on configured strategy
        strategy_name = getattr(settings, 'selection_strategy', 'importance')
        
        if strategy_name == 'strategic':
            strategy = SelectionStrategy.STRATEGIC
        elif strategy_name == 'hybrid':
            strategy = SelectionStrategy.HYBRID
        elif strategy_name == 'budget':
            strategy = SelectionStrategy.BUDGET_CONSTRAINED
        else:
            strategy = SelectionStrategy.IMPORTANCE_BASED
            
        return chunk_selector.select_chunks(chunks, strategy, criteria)
    
    def _add_simple_summaries(self, all_chunks: List[Dict[str, Any]], ai_summarized: List[Dict[str, Any]]):
        """Add simple rule-based summaries for unselected chunks"""
        
        # Create lookup of AI-summarized chunks
        ai_summarized_ids = {chunk.get('id', chunk.get('content', '')) for chunk in ai_summarized}
        
        # Add simple summaries for remaining chunks
        for chunk in all_chunks:
            chunk_id = chunk.get('id', chunk.get('content', ''))
            
            if chunk_id not in ai_summarized_ids and not chunk.get('summary'):
                chunk['summary'] = self._generate_simple_summary(chunk)
    
    def _generate_simple_summary(self, chunk: Dict[str, Any]) -> str:
        """Generate simple rule-based summary"""
        chunk_type = chunk.get('type', 'code')
        name = chunk.get('name', 'unknown')
        language = chunk.get('language', 'unknown')
        
        if chunk_type == 'function':
            return f"Function '{name}' in {language}"
        elif chunk_type == 'class':
            return f"Class '{name}' definition in {language}"
        elif chunk_type == 'method':
            return f"Method '{name}' implementation"
        else:
            return f"Code component in {language}"


# Global instance
production_summarizer = ProductionSummarizationService()