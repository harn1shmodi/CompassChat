from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from services.graph_service import GraphService
from core.database import User
from api.auth import get_current_user
from utils.path_utils import clean_search_results
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    repository: str = None  # Format: "owner/name"
    max_results: int = 10


class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    repository: str = None


@router.post("/", response_model=ChatResponse)
async def chat_with_code(request: ChatRequest, current_user: User = Depends(get_current_user)):
    """Chat with code using hybrid retrieval"""
    try:
        graph_service = GraphService()
        
        # Search for relevant code chunks
        search_results = graph_service.search_code(
            query=request.question,
            limit=request.max_results
        )
        
        if not search_results:
            return ChatResponse(
                answer="I couldn't find any relevant code for your question. Please make sure the repository has been analyzed.",
                sources=[],
                repository=request.repository
            )
        
        # Clean file paths in search results
        search_results = clean_search_results(search_results)
        
        # Generate answer using the LLM with context
        answer = await generate_answer_with_context(
            question=request.question,
            search_results=search_results,
            graph_service=graph_service
        )
        
        # Format sources for response
        sources = format_sources(search_results)
        
        return ChatResponse(
            answer=answer,
            sources=sources,
            repository=request.repository
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    graph_service = GraphService()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            question = message.get('question', '')
            repository = message.get('repository')
            max_results = message.get('max_results', 10)
            
            if not question:
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': 'Question is required'
                }))
                continue
                
            if not repository:
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': 'Repository context is required for all searches'
                }))
                continue
            
            try:
                # Send thinking status
                await websocket.send_text(json.dumps({
                    'type': 'status',
                    'message': 'Searching code...'
                }))
                
                # Search for relevant code
                search_results = graph_service.search_code(
                    query=question,
                    limit=max_results,
                    repository=repository
                )
                
                await websocket.send_text(json.dumps({
                    'type': 'status',
                    'message': f'Found {len(search_results)} relevant code chunks'
                }))
                
                if not search_results:
                    await websocket.send_text(json.dumps({
                        'type': 'answer',
                        'content': "I couldn't find any relevant code for your question. Please make sure the repository has been analyzed.",
                        'sources': [],
                        'repository': repository
                    }))
                    
                    # Send empty sources and completion for consistency
                    await websocket.send_text(json.dumps({
                        'type': 'sources',
                        'sources': [],
                        'repository': repository
                    }))
                    
                    await websocket.send_text(json.dumps({
                        'type': 'complete'
                    }))
                    continue
                
                # Clean file paths in search results
                search_results = clean_search_results(search_results)
                
                await websocket.send_text(json.dumps({
                    'type': 'status',
                    'message': 'Generating answer...'
                }))
                
                # Generate streaming answer
                chunk_count = 0
                for chunk in stream_answer_with_context(
                    question=question,
                    search_results=search_results,
                    graph_service=graph_service
                ):
                    chunk_count += 1
                    await websocket.send_text(json.dumps({
                        'type': 'answer_chunk',
                        'content': chunk
                    }))
                
                logger.info(f"Streamed {chunk_count} chunks for question: {question[:50]}...")
                
                # Send sources
                sources = format_sources(search_results)
                await websocket.send_text(json.dumps({
                    'type': 'sources',
                    'sources': sources,
                    'repository': repository
                }))
                
                # Send completion
                await websocket.send_text(json.dumps({
                    'type': 'complete'
                }))
                
            except Exception as e:
                logger.error(f"Error processing chat message: {e}")
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': 'An error occurred while processing your question'
                }))
    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


async def generate_answer_with_context(
    question: str, 
    search_results: List[Dict[str, Any]], 
    graph_service: GraphService
) -> str:
    """Generate answer using LLM with code context"""
    try:
        # Try to use Neo4j GraphRAG pipeline first
        try:
            answer = graph_service.generate_answer_with_graphrag(question)
            if answer and answer.strip():
                return answer
        except Exception as e:
            logger.warning(f"GraphRAG pipeline failed, falling back to custom implementation: {e}")
        
        # Fallback to custom implementation
        context = build_context_from_results(search_results)
        answer = graph_service.generate_answer(question, context)
        return answer
        
    except Exception as e:
        logger.error(f"Error generating answer: {e}")
        return "I apologize, but I encountered an error while generating an answer to your question."


def stream_answer_with_context(
    question: str, 
    search_results: List[Dict[str, Any]], 
    graph_service: GraphService
):
    """Stream answer generation for WebSocket"""
    try:
        # For streaming, we'll use the custom implementation with context
        # since the GraphRAG pipeline doesn't support streaming yet
        context = build_context_from_results(search_results)
        
        # Stream response from LLM
        for chunk in graph_service.stream_answer(question, context):
            yield chunk
                
    except Exception as e:
        logger.error(f"Error streaming answer: {e}")
        yield "I apologize, but I encountered an error while generating an answer to your question."


def build_context_from_results(search_results: List[Dict[str, Any]]) -> str:
    """Build context string from search results"""
    context_parts = []
    
    for i, result in enumerate(search_results[:5], 1):  # Limit to top 5 results
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
{content[:1000]}{'...' if len(content) > 1000 else ''}
```
"""
        context_parts.append(context_part)
    
    return '\n'.join(context_parts)


def format_sources(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format search results as sources for the response"""
    sources = []
    
    for result in search_results:
        # Ensure file path is clean (should already be cleaned by clean_search_results)
        file_path = result.get('file_path', '')
        
        source = {
            'file_path': file_path,
            'chunk_name': result.get('chunk_name', ''),
            'chunk_type': result.get('chunk_type', ''),
            'language': result.get('language', ''),
            'summary': result.get('summary', ''),
            'score': round(result.get('score', 0.0), 3),
            'content_preview': result.get('content', '')[:200] + ('...' if len(result.get('content', '')) > 200 else '')
        }
        sources.append(source)
    
    return sources
