"""
Query preprocessing service for handling vague queries in RAG systems.

This service implements query expansion, intent detection, and HyDE (Hypothetical Document Embeddings)
to improve retrieval quality for vague or underspecified user queries.
"""

import logging
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from core.config import settings
from services.ai_provider import ai_provider
import json
import re

logger = logging.getLogger(__name__)

class QueryPreprocessor:
    """Handles query preprocessing for better RAG retrieval"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        
    def preprocess_query(self, query: str, repository: str = None) -> Dict[str, any]:
        """
        Main preprocessing pipeline for queries.
        
        Args:
            query: Raw user query
            repository: Repository being queried
            
        Returns:
            Dict containing processed query and metadata
        """
        try:
            logger.info(f"Starting query preprocessing for: '{query[:50]}...'")
            
            # Step 1: Detect query intent and type
            intent_data = self._detect_intent(query, repository)
            
            # Step 2: Query expansion and rewriting
            expanded_query = self._expand_query(query, intent_data)
            
            # Step 3: HyDE - Generate hypothetical document for embedding
            hyde_doc = self._generate_hyde_document(query, intent_data, repository)
            
            # Step 4: Generate search queries for different retrieval strategies
            search_queries = self._generate_search_queries(query, expanded_query, intent_data)
            
            result = {
                'original_query': query,
                'processed_query': expanded_query,
                'hyde_document': hyde_doc,
                'intent': intent_data['intent'],
                'confidence': intent_data['confidence'],
                'search_queries': search_queries,
                'metadata': intent_data.get('metadata', {})
            }
            
            logger.info(f"Query preprocessing completed. Intent: {intent_data['intent']} (confidence: {intent_data['confidence']})")
            return result
            
        except Exception as e:
            logger.error(f"Error in query preprocessing: {e}")
            # Return original query as fallback
            return {
                'original_query': query,
                'processed_query': query,
                'hyde_document': query,
                'intent': 'general',
                'confidence': 0.0,
                'search_queries': [query],
                'metadata': {}
            }
    
    def _detect_intent(self, query: str, repository: str = None) -> Dict[str, any]:
        """
        Detect the intent behind a user's query using LLM classification.
        
        Intents:
        - project_overview: "what does this app do?", "explain this project"
        - specific_feature: "how does authentication work?", "show me the API endpoints"
        - code_explanation: "what does this function do?", "explain this class"
        - debugging: "why is this error happening?", "fix this bug"
        - architecture: "how is the app structured?", "what are the main components"
        - usage: "how to use this library?", "installation guide"
        - general: catch-all for unclear intents
        """
        try:
            prompt = f"""
            Analyze the following user query and determine its intent in the context of code analysis.
            
            Query: "{query}"
            Repository: {repository or "unknown"}
            
            Classify the intent as one of these types:
            - project_overview: User wants a high-level explanation of what the project does
            - specific_feature: User is asking about a specific feature or component
            - code_explanation: User wants to understand specific code (function, class, etc.)
            - debugging: User is trying to solve a problem or fix an error
            - architecture: User wants to understand the overall structure/design
            - usage: User wants to know how to use/install the project
            - general: Other or unclear intent
            
            Also extract any technical terms, function names, or specific concepts mentioned.
            
            Respond with JSON format:
            {{
                "intent": "project_overview",
                "confidence": 0.85,
                "metadata": {{
                    "key_terms": ["authentication", "JWT"],
                    "specific_concepts": ["user login", "token validation"],
                    "is_vague": true/false
                }}
            }}
            """
            
            response = ai_provider.generate_chat_completion([
                {"role": "system", "content": "You are a query intent classifier for code analysis. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ], max_tokens=200, temperature=0.1)
            
            try:
                result = json.loads(response.strip())
                return result
            except json.JSONDecodeError:
                # Fallback to simple heuristic
                return self._simple_intent_detection(query)
                
        except Exception as e:
            logger.error(f"Error in intent detection: {e}")
            return self._simple_intent_detection(query)
    
    def _simple_intent_detection(self, query: str) -> Dict[str, any]:
        """Simple rule-based intent detection as fallback"""
        query_lower = query.lower().strip()
        
        # Vague project overview patterns
        vague_patterns = [
            r"what does this (app|project|repository|codebase) do",
            r"what is this (app|project|repository|codebase)",
            r"explain this (project|app|repository)",
            r"tell me about this (project|app|repository)",
            r"overview of this (project|app|repository)",
            r"describe this (project|app|repository)"
        ]
        
        # Specific feature patterns
        feature_patterns = [
            r"how does .* work",
            r"show me .*",
            r"where is .* implemented",
            r"explain .* (feature|component|module)"
        ]
        
        # Usage patterns
        usage_patterns = [
            r"how to use",
            r"how do i install",
            r"getting started",
            r"usage example"
        ]
        
        # Architecture patterns
        architecture_patterns = [
            r"how is .* structured",
            r"architecture of",
            r"main components",
            r"design pattern"
        ]
        
        # Check each pattern category
        for pattern in vague_patterns:
            if re.search(pattern, query_lower):
                return {
                    "intent": "project_overview",
                    "confidence": 0.7,
                    "metadata": {"is_vague": True, "key_terms": [], "specific_concepts": []}
                }
        
        for pattern in feature_patterns:
            if re.search(pattern, query_lower):
                return {
                    "intent": "specific_feature",
                    "confidence": 0.6,
                    "metadata": {"is_vague": False, "key_terms": [], "specific_concepts": []}
                }
                
        for pattern in usage_patterns:
            if re.search(pattern, query_lower):
                return {
                    "intent": "usage",
                    "confidence": 0.6,
                    "metadata": {"is_vague": False, "key_terms": [], "specific_concepts": []}
                }
                
        for pattern in architecture_patterns:
            if re.search(pattern, query_lower):
                return {
                    "intent": "architecture",
                    "confidence": 0.6,
                    "metadata": {"is_vague": False, "key_terms": [], "specific_concepts": []}
                }
        
        # Default
        return {
            "intent": "general",
            "confidence": 0.3,
            "metadata": {"is_vague": True, "key_terms": [], "specific_concepts": []}
        }
    
    def _expand_query(self, query: str, intent_data: Dict) -> str:
        """Expand query based on detected intent"""
        try:
            intent = intent_data.get('intent', 'general')
            metadata = intent_data.get('metadata', {})
            
            # Handle vague project overview queries
            if intent == 'project_overview' and metadata.get('is_vague', False):
                # Add project context terms
                expanded = f"{query} project overview purpose functionality what it does main features"
                return expanded
            
            # Handle specific feature queries
            elif intent == 'specific_feature':
                key_terms = metadata.get('key_terms', [])
                if key_terms:
                    expanded = f"{query} implementation code function class"
                    return expanded
            
            # Handle usage queries
            elif intent == 'usage':
                expanded = f"{query} usage documentation example tutorial"
                return expanded
            
            # Handle architecture queries
            elif intent == 'architecture':
                expanded = f"{query} architecture structure design components classes modules"
                return expanded
            
            # For debugging and code explanation, keep original
            elif intent in ['debugging', 'code_explanation']:
                return query
            
            return query
            
        except Exception as e:
            logger.error(f"Error in query expansion: {e}")
            return query
    
    def _generate_hyde_document(self, query: str, intent_data: Dict, repository: str = None) -> str:
        """
        Generate hypothetical document using HyDE (Hypothetical Document Embeddings)
        for better semantic search.
        """
        try:
            intent = intent_data.get('intent', 'general')
            
            # Context-aware prompts for different intents
            prompts = {
                'project_overview': f"""
                Write a concise technical document that explains what the {repository or 'project'} does. 
                Include its main purpose, key features, and overall functionality based on the codebase.
                Query: {query}
                """,
                
                'specific_feature': f"""
                Write a technical explanation that answers: {query}
                Focus on the actual implementation details and code structure.
                """,
                
                'code_explanation': f"""
                Write a clear explanation of the code that addresses: {query}
                Include relevant code examples and technical details.
                """,
                
                'architecture': f"""
                Describe the architecture and structure of {repository or 'the project'} 
                that would answer: {query}
                """,
                
                'usage': f"""
                Write documentation explaining how to use {repository or 'the project'} 
                that addresses: {query}
                """,
                
                'debugging': f"""
                Provide a technical explanation that helps debug or solve: {query}
                Include relevant code context and potential solutions.
                """,
                
                'general': f"""
                Write a technical document that answers: {query}
                Focus on the actual codebase and implementation details.
                """
            }
            
            prompt = prompts.get(intent, prompts['general'])
            
            response = ai_provider.generate_chat_completion([
                {"role": "system", "content": "You are writing a hypothetical technical document for retrieval purposes. Be specific and include relevant technical details."},
                {"role": "user", "content": prompt}
            ], max_tokens=300, temperature=0.3)
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generating HyDE document: {e}")
            # Fallback to original query
            return query
    
    def _generate_search_queries(self, original_query: str, expanded_query: str, intent_data: Dict) -> List[str]:
        """Generate multiple search queries for different retrieval strategies"""
        try:
            intent = intent_data.get('intent', 'general')
            queries = [original_query, expanded_query]
            
            # Add intent-specific queries
            if intent == 'project_overview':
                queries.extend([
                    "project overview README",
                    "project description main functionality",
                    "what this project does purpose",
                    "introduction getting started"
                ])
            elif intent == 'architecture':
                queries.extend([
                    "architecture structure design",
                    "main components modules",
                    "system architecture overview"
                ])
            elif intent == 'usage':
                queries.extend([
                    "usage documentation",
                    "getting started tutorial",
                    "how to use examples"
                ])
            
            # Remove duplicates while preserving order
            seen = set()
            unique_queries = []
            for q in queries:
                if q and q.lower() not in seen:
                    seen.add(q.lower())
                    unique_queries.append(q)
            
            return unique_queries[:5]  # Limit to top 5 queries
            
        except Exception as e:
            logger.error(f"Error generating search queries: {e}")
            return [original_query, expanded_query]
    
    def should_use_hyde(self, intent_data: Dict) -> bool:
        """Determine if HyDE should be used based on intent and confidence"""
        intent = intent_data.get('intent', 'general')
        confidence = intent_data.get('confidence', 0.0)
        is_vague = intent_data.get('metadata', {}).get('is_vague', False)
        
        # Use HyDE for vague queries or low confidence
        return is_vague or confidence < 0.7 or intent in ['project_overview', 'architecture']

# Global instance
query_preprocessor = QueryPreprocessor()