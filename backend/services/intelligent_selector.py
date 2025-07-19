#!/usr/bin/env python3
"""
Intelligent Chunk Selection Service
Advanced algorithms for selecting which files/functions/chunks to summarize
based on code importance, usage patterns, and strategic value.
"""

import re
import ast
import logging
from typing import List, Dict, Any, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import networkx as nx
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class SelectionStrategy(Enum):
    """Different strategies for selecting chunks to summarize"""
    ALL = "all"                          # Summarize everything (current approach)
    IMPORTANCE_BASED = "importance"      # Based on code importance analysis
    USAGE_BASED = "usage"               # Based on code usage patterns
    STRATEGIC = "strategic"             # Based on strategic value (APIs, core logic)
    BUDGET_CONSTRAINED = "budget"       # Based on available budget/time
    HYBRID = "hybrid"                   # Combination of multiple strategies


@dataclass
class SelectionCriteria:
    """Criteria for selecting chunks to summarize"""
    max_chunks: Optional[int] = None
    max_cost: Optional[float] = None
    min_importance: Optional[str] = None
    include_patterns: List[str] = None
    exclude_patterns: List[str] = None
    prioritize_public_apis: bool = True
    prioritize_entry_points: bool = True
    prioritize_core_logic: bool = True


class ChunkSelector:
    """Intelligent selector for determining which chunks to summarize"""
    
    def __init__(self):
        self.dependency_graph = nx.DiGraph()
        self.api_endpoints = set()
        self.entry_points = set()
        self.core_modules = set()
        
    def select_chunks(self, 
                     chunks: List[Dict[str, Any]], 
                     strategy: SelectionStrategy = SelectionStrategy.IMPORTANCE_BASED,
                     criteria: SelectionCriteria = None) -> List[Dict[str, Any]]:
        """
        Select which chunks to summarize based on the given strategy
        
        Args:
            chunks: All available chunks
            strategy: Selection strategy to use
            criteria: Additional selection criteria
            
        Returns:
            List of selected chunks to summarize
        """
        if not chunks:
            return []
            
        criteria = criteria or SelectionCriteria()
        
        logger.info(f"Selecting chunks using {strategy.value} strategy from {len(chunks)} total chunks")
        
        # Apply base filtering
        filtered_chunks = self._apply_base_filters(chunks, criteria)
        
        # Apply strategy-specific selection
        if strategy == SelectionStrategy.ALL:
            selected_chunks = filtered_chunks
        elif strategy == SelectionStrategy.IMPORTANCE_BASED:
            selected_chunks = self._select_by_importance(filtered_chunks, criteria)
        elif strategy == SelectionStrategy.USAGE_BASED:
            selected_chunks = self._select_by_usage(filtered_chunks, criteria)
        elif strategy == SelectionStrategy.STRATEGIC:
            selected_chunks = self._select_by_strategic_value(filtered_chunks, criteria)
        elif strategy == SelectionStrategy.BUDGET_CONSTRAINED:
            selected_chunks = self._select_by_budget(filtered_chunks, criteria)
        elif strategy == SelectionStrategy.HYBRID:
            selected_chunks = self._select_hybrid(filtered_chunks, criteria)
        else:
            selected_chunks = filtered_chunks
        
        # Apply final constraints
        selected_chunks = self._apply_final_constraints(selected_chunks, criteria)
        
        logger.info(f"Selected {len(selected_chunks)} chunks for summarization")
        return selected_chunks
    
    def _apply_base_filters(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Apply basic filtering based on patterns and criteria"""
        filtered_chunks = []
        
        for chunk in chunks:
            # Check include patterns
            if criteria.include_patterns:
                if not any(self._matches_pattern(chunk, pattern) for pattern in criteria.include_patterns):
                    continue
            
            # Check exclude patterns
            if criteria.exclude_patterns:
                if any(self._matches_pattern(chunk, pattern) for pattern in criteria.exclude_patterns):
                    continue
            
            # Check minimum importance
            if criteria.min_importance:
                chunk_importance = self._analyze_importance(chunk)
                if not self._meets_importance_threshold(chunk_importance, criteria.min_importance):
                    continue
            
            filtered_chunks.append(chunk)
        
        return filtered_chunks
    
    def _matches_pattern(self, chunk: Dict[str, Any], pattern: str) -> bool:
        """Check if chunk matches a given pattern"""
        file_path = chunk.get('file_path', '').lower()
        chunk_name = chunk.get('name', '').lower()
        content = chunk.get('content', '').lower()
        
        pattern_lower = pattern.lower()
        
        # Check different aspects
        return (pattern_lower in file_path or 
                pattern_lower in chunk_name or 
                pattern_lower in content)
    
    def _select_by_importance(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Select chunks based on code importance analysis"""
        
        # Analyze importance for each chunk
        scored_chunks = []
        for chunk in chunks:
            importance_score = self._calculate_importance_score(chunk)
            scored_chunks.append((chunk, importance_score))
        
        # Sort by importance score (descending)
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        # Select top chunks
        if criteria.max_chunks:
            return [chunk for chunk, score in scored_chunks[:criteria.max_chunks]]
        else:
            # Select chunks above average importance
            scores = [score for chunk, score in scored_chunks]
            avg_score = sum(scores) / len(scores) if scores else 0
            return [chunk for chunk, score in scored_chunks if score > avg_score]
    
    def _select_by_usage(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Select chunks based on usage patterns and dependencies"""
        
        # Build dependency graph
        self._build_dependency_graph(chunks)
        
        # Calculate usage metrics
        usage_scores = {}
        for chunk in chunks:
            chunk_id = chunk.get('id', chunk.get('name', ''))
            
            # Calculate centrality measures
            if chunk_id in self.dependency_graph:
                in_degree = self.dependency_graph.in_degree(chunk_id)
                out_degree = self.dependency_graph.out_degree(chunk_id)
                
                # Try to calculate betweenness centrality
                try:
                    centrality = nx.betweenness_centrality(self.dependency_graph).get(chunk_id, 0)
                except:
                    centrality = 0
                
                usage_score = (in_degree * 2) + out_degree + (centrality * 10)
            else:
                usage_score = 0
            
            usage_scores[chunk_id] = usage_score
        
        # Sort by usage score
        sorted_chunks = sorted(chunks, 
                             key=lambda c: usage_scores.get(c.get('id', c.get('name', '')), 0), 
                             reverse=True)
        
        # Select top chunks
        if criteria.max_chunks:
            return sorted_chunks[:criteria.max_chunks]
        else:
            # Select chunks with above-average usage
            scores = list(usage_scores.values())
            avg_score = sum(scores) / len(scores) if scores else 0
            return [chunk for chunk in chunks 
                   if usage_scores.get(chunk.get('id', chunk.get('name', '')), 0) > avg_score]
    
    def _select_by_strategic_value(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Select chunks based on strategic value (APIs, core logic, etc.)"""
        
        strategic_chunks = []
        
        for chunk in chunks:
            strategic_score = self._calculate_strategic_score(chunk, criteria)
            if strategic_score > 0:
                chunk['strategic_score'] = strategic_score
                strategic_chunks.append(chunk)
        
        # Sort by strategic score
        strategic_chunks.sort(key=lambda c: c.get('strategic_score', 0), reverse=True)
        
        # Select based on criteria
        if criteria.max_chunks:
            return strategic_chunks[:criteria.max_chunks]
        else:
            # Select chunks with high strategic value
            return [chunk for chunk in strategic_chunks if chunk.get('strategic_score', 0) > 5]
    
    def _select_by_budget(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Select chunks based on available budget constraints"""
        
        if not criteria.max_cost and not criteria.max_chunks:
            return chunks
        
        # Calculate cost for each chunk
        costed_chunks = []
        for chunk in chunks:
            cost = self._estimate_summarization_cost(chunk)
            importance = self._calculate_importance_score(chunk)
            
            # Calculate value/cost ratio
            value_ratio = importance / max(cost, 0.01)  # Avoid division by zero
            
            costed_chunks.append((chunk, cost, value_ratio))
        
        # Sort by value/cost ratio (descending)
        costed_chunks.sort(key=lambda x: x[2], reverse=True)
        
        # Select chunks within budget
        selected_chunks = []
        total_cost = 0
        total_chunks = 0
        
        for chunk, cost, ratio in costed_chunks:
            if criteria.max_cost and total_cost + cost > criteria.max_cost:
                break
            if criteria.max_chunks and total_chunks >= criteria.max_chunks:
                break
            
            selected_chunks.append(chunk)
            total_cost += cost
            total_chunks += 1
        
        logger.info(f"Selected {len(selected_chunks)} chunks with total cost ${total_cost:.2f}")
        return selected_chunks
    
    def _select_hybrid(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Select chunks using a combination of strategies"""
        
        # Calculate multiple scores for each chunk
        hybrid_scores = {}
        
        for chunk in chunks:
            importance_score = self._calculate_importance_score(chunk)
            strategic_score = self._calculate_strategic_score(chunk, criteria)
            
            # Calculate usage score (simplified)
            usage_score = self._estimate_usage_score(chunk)
            
            # Calculate cost efficiency
            cost = self._estimate_summarization_cost(chunk)
            cost_efficiency = importance_score / max(cost, 0.01)
            
            # Weighted combination
            hybrid_score = (
                importance_score * 0.3 +
                strategic_score * 0.3 +
                usage_score * 0.2 +
                cost_efficiency * 0.2
            )
            
            hybrid_scores[chunk.get('id', chunk.get('name', ''))] = hybrid_score
        
        # Sort by hybrid score
        sorted_chunks = sorted(chunks, 
                             key=lambda c: hybrid_scores.get(c.get('id', c.get('name', '')), 0), 
                             reverse=True)
        
        # Select top chunks
        if criteria.max_chunks:
            return sorted_chunks[:criteria.max_chunks]
        else:
            # Select top 50% by default
            return sorted_chunks[:len(sorted_chunks) // 2]
    
    def _calculate_importance_score(self, chunk: Dict[str, Any]) -> float:
        """Calculate importance score for a chunk"""
        score = 0.0
        
        content = chunk.get('content', '').lower()
        chunk_type = chunk.get('type', '')
        name = chunk.get('name', '').lower()
        file_path = chunk.get('file_path', '').lower()
        
        # Type-based scoring
        type_scores = {
            'class': 5.0,
            'function': 3.0,
            'method': 2.0,
            'variable': 1.0
        }
        score += type_scores.get(chunk_type, 1.0)
        
        # Keyword-based scoring
        important_keywords = {
            'public': 10.0, 'api': 10.0, 'interface': 8.0,
            'main': 8.0, 'init': 6.0, 'setup': 6.0,
            'config': 4.0, 'service': 6.0, 'manager': 6.0,
            'handler': 5.0, 'controller': 5.0, 'router': 5.0,
            'auth': 7.0, 'security': 7.0, 'validate': 5.0,
            'process': 4.0, 'execute': 4.0, 'run': 3.0
        }
        
        for keyword, weight in important_keywords.items():
            if keyword in content or keyword in name:
                score += weight
        
        # File path-based scoring
        if any(pattern in file_path for pattern in ['api/', 'service/', 'core/', 'main.']):
            score += 5.0
        
        if any(pattern in file_path for pattern in ['util/', 'helper/', 'test/']):
            score += 1.0
        
        # Content size factor
        content_length = len(content)
        if content_length > 1000:
            score += 3.0
        elif content_length > 500:
            score += 2.0
        elif content_length > 200:
            score += 1.0
        
        # Complexity indicators
        if 'class ' in content and 'def ' in content:
            score += 4.0  # Class with methods
        
        if content.count('def ') > 3:
            score += 2.0  # Multiple functions
        
        if any(pattern in content for pattern in ['async ', 'await ', 'threading']):
            score += 3.0  # Async/concurrent code
        
        return score
    
    def _calculate_strategic_score(self, chunk: Dict[str, Any], criteria: SelectionCriteria) -> float:
        """Calculate strategic value score for a chunk"""
        score = 0.0
        
        content = chunk.get('content', '').lower()
        name = chunk.get('name', '').lower()
        file_path = chunk.get('file_path', '').lower()
        
        # API endpoints (high strategic value)
        if criteria.prioritize_public_apis:
            api_indicators = ['@app.route', '@router.', 'def get_', 'def post_', 'def put_', 'def delete_']
            if any(indicator in content for indicator in api_indicators):
                score += 15.0
        
        # Entry points (high strategic value)
        if criteria.prioritize_entry_points:
            entry_indicators = ['if __name__ == "__main__"', 'def main(', 'application.run', 'app.run']
            if any(indicator in content for indicator in entry_indicators):
                score += 12.0
        
        # Core business logic (high strategic value)
        if criteria.prioritize_core_logic:
            core_indicators = ['business', 'logic', 'algorithm', 'calculation', 'processing']
            if any(indicator in name or indicator in file_path for indicator in core_indicators):
                score += 10.0
        
        # Configuration and setup (medium strategic value)
        config_indicators = ['config', 'settings', 'setup', 'initialization']
        if any(indicator in name or indicator in file_path for indicator in config_indicators):
            score += 6.0
        
        # Database/storage access (medium strategic value)
        db_indicators = ['database', 'db', 'storage', 'repository', 'dao']
        if any(indicator in name or indicator in file_path for indicator in db_indicators):
            score += 7.0
        
        # Authentication/security (high strategic value)
        auth_indicators = ['auth', 'security', 'login', 'permission', 'access']
        if any(indicator in name or indicator in file_path for indicator in auth_indicators):
            score += 8.0
        
        return score
    
    def _estimate_usage_score(self, chunk: Dict[str, Any]) -> float:
        """Estimate usage score based on code patterns"""
        score = 0.0
        
        content = chunk.get('content', '')
        chunk_type = chunk.get('type', '')
        
        # Count imports/calls in content (rough estimation)
        import_count = content.count('import ') + content.count('from ')
        call_count = content.count('(') - content.count('def ')  # Rough function call count
        
        score += min(import_count * 2, 10)  # Cap at 10
        score += min(call_count * 0.5, 15)  # Cap at 15
        
        # Public methods/functions likely have higher usage
        if chunk_type in ['function', 'method'] and not chunk.get('name', '').startswith('_'):
            score += 5.0
        
        return score
    
    def _estimate_summarization_cost(self, chunk: Dict[str, Any]) -> float:
        """Estimate cost of summarizing a chunk"""
        content = chunk.get('content', '')
        
        # Rough token estimation (1 token ≈ 4 characters)
        tokens = len(content) // 4
        
        # Cost per token (example: $0.0001 per token)
        cost_per_token = 0.0001
        
        return tokens * cost_per_token
    
    def _build_dependency_graph(self, chunks: List[Dict[str, Any]]):
        """Build dependency graph from chunks"""
        self.dependency_graph.clear()
        
        # Add all chunks as nodes
        for chunk in chunks:
            chunk_id = chunk.get('id', chunk.get('name', ''))
            self.dependency_graph.add_node(chunk_id, **chunk)
        
        # Analyze dependencies (simplified)
        for chunk in chunks:
            chunk_id = chunk.get('id', chunk.get('name', ''))
            content = chunk.get('content', '')
            
            # Look for function calls and imports
            for other_chunk in chunks:
                if chunk == other_chunk:
                    continue
                    
                other_id = other_chunk.get('id', other_chunk.get('name', ''))
                other_name = other_chunk.get('name', '')
                
                # If this chunk references the other chunk
                if other_name and other_name in content:
                    self.dependency_graph.add_edge(chunk_id, other_id)
    
    def _analyze_importance(self, chunk: Dict[str, Any]) -> str:
        """Analyze importance level of a chunk"""
        score = self._calculate_importance_score(chunk)
        
        if score >= 15:
            return "critical"
        elif score >= 10:
            return "high"
        elif score >= 5:
            return "medium"
        else:
            return "low"
    
    def _meets_importance_threshold(self, importance: str, threshold: str) -> bool:
        """Check if importance meets threshold"""
        importance_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return importance_levels.get(importance, 1) >= importance_levels.get(threshold, 1)
    
    def _apply_final_constraints(self, chunks: List[Dict[str, Any]], criteria: SelectionCriteria) -> List[Dict[str, Any]]:
        """Apply final constraints to selected chunks"""
        
        # Limit by max_chunks
        if criteria.max_chunks and len(chunks) > criteria.max_chunks:
            chunks = chunks[:criteria.max_chunks]
        
        # Limit by cost
        if criteria.max_cost:
            total_cost = 0
            selected_chunks = []
            
            for chunk in chunks:
                cost = self._estimate_summarization_cost(chunk)
                if total_cost + cost <= criteria.max_cost:
                    selected_chunks.append(chunk)
                    total_cost += cost
                else:
                    break
            
            chunks = selected_chunks
        
        return chunks
    
    def analyze_codebase_structure(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze codebase structure to inform selection decisions"""
        
        analysis = {
            'total_chunks': len(chunks),
            'file_distribution': {},
            'type_distribution': {},
            'size_distribution': {'small': 0, 'medium': 0, 'large': 0},
            'complexity_indicators': {},
            'api_endpoints': [],
            'entry_points': [],
            'core_modules': []
        }
        
        for chunk in chunks:
            # File distribution
            file_path = chunk.get('file_path', 'unknown')
            analysis['file_distribution'][file_path] = analysis['file_distribution'].get(file_path, 0) + 1
            
            # Type distribution
            chunk_type = chunk.get('type', 'unknown')
            analysis['type_distribution'][chunk_type] = analysis['type_distribution'].get(chunk_type, 0) + 1
            
            # Size distribution
            content_size = len(chunk.get('content', ''))
            if content_size < 200:
                analysis['size_distribution']['small'] += 1
            elif content_size < 1000:
                analysis['size_distribution']['medium'] += 1
            else:
                analysis['size_distribution']['large'] += 1
            
            # Identify special components
            content = chunk.get('content', '').lower()
            name = chunk.get('name', '').lower()
            
            if any(indicator in content for indicator in ['@app.route', '@router.', 'def get_', 'def post_']):
                analysis['api_endpoints'].append(chunk.get('name', ''))
            
            if any(indicator in content for indicator in ['if __name__ == "__main__"', 'def main(']):
                analysis['entry_points'].append(chunk.get('name', ''))
            
            if any(indicator in name for indicator in ['service', 'manager', 'handler', 'controller']):
                analysis['core_modules'].append(chunk.get('name', ''))
        
        return analysis
    
    def get_selection_recommendations(self, chunks: List[Dict[str, Any]], target_percentage: float = 0.3) -> Dict[str, Any]:
        """Get recommendations for chunk selection"""
        
        analysis = self.analyze_codebase_structure(chunks)
        target_count = int(len(chunks) * target_percentage)
        
        recommendations = {
            'target_count': target_count,
            'target_percentage': target_percentage,
            'analysis': analysis,
            'strategies': {}
        }
        
        # Test different strategies
        strategies = [
            (SelectionStrategy.IMPORTANCE_BASED, "Importance-Based"),
            (SelectionStrategy.STRATEGIC, "Strategic Value"),
            (SelectionStrategy.HYBRID, "Hybrid Approach")
        ]
        
        for strategy, name in strategies:
            criteria = SelectionCriteria(max_chunks=target_count)
            selected = self.select_chunks(chunks, strategy, criteria)
            
            recommendations['strategies'][strategy.value] = {
                'name': name,
                'selected_count': len(selected),
                'estimated_cost': sum(self._estimate_summarization_cost(c) for c in selected),
                'coverage': {
                    'api_endpoints': sum(1 for c in selected if c.get('name', '') in analysis['api_endpoints']),
                    'entry_points': sum(1 for c in selected if c.get('name', '') in analysis['entry_points']),
                    'core_modules': sum(1 for c in selected if c.get('name', '') in analysis['core_modules'])
                }
            }
        
        return recommendations


# Global instance
chunk_selector = ChunkSelector()