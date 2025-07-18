from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from services.github_clone import GitHubCloner
from services.ast_parser import ASTParser
from services.chunker import CodeChunker
from services.optimized_summarizer import OptimizedCodeSummarizer
from services.graph_service import GraphService
from services.cache_service import cache_service
from core.database import User
from api.auth import get_current_user
from typing import Generator, Optional
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["repositories"])


class RepoAnalyzeRequest(BaseModel):
    url: HttpUrl


@router.post("/analyze")
async def analyze_repository(
    request: RepoAnalyzeRequest, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Analyze a GitHub repository and index it into the graph database"""
    
    async def process_repository():
        cloner = GitHubCloner()
        parser = ASTParser()
        chunker = CodeChunker()
        summarizer = OptimizedCodeSummarizer()
        graph_service = GraphService()
        
        try:
            repo_url = str(request.url)
            
            # Check if repository is already cached
            yield f"data: {json.dumps({'status': 'checking_cache', 'message': 'Checking repository cache'})}\n\n"
            
            if cache_service.is_repository_cached(repo_url):
                # Repository is cached, grant user access and return cached stats
                yield f"data: {json.dumps({'status': 'cache_hit', 'message': 'Repository found in cache'})}\n\n"
                
                cache_service.grant_user_access(current_user, repo_url)
                cached_stats = cache_service.get_cached_repository_stats(repo_url)
                
                if cached_stats:
                    yield f"data: {json.dumps({'status': 'complete', 'data': cached_stats})}\n\n"
                    return
            
            # Repository not cached, proceed with analysis
            yield f"data: {json.dumps({'status': 'cloning', 'message': 'Starting repository clone'})}\n\n"
            
            repo_info = None
            files_data = None
            temp_dir = None
            
            for update in cloner.clone_repo(repo_url):
                yield f"data: {json.dumps(update)}\n\n"
                
                if update['status'] == 'info':
                    repo_info = update['data']
                elif update['status'] == 'files':
                    files_data = update['data']
                    temp_dir = files_data['temp_dir']
                elif update['status'] == 'error':
                    return
            
            if not repo_info or not files_data:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Failed to get repository information'})}\n\n"
                return
            
            files = files_data['files']
            yield f"data: {json.dumps({'status': 'progress', 'message': f'Found {len(files)} source files'})}\n\n"
            
            # Step 2: Parse AST for each file
            yield f"data: {json.dumps({'status': 'parsing', 'message': 'Parsing source files'})}\n\n"
            
            parsed_files = []
            for i, file_info in enumerate(files):
                try:
                    # Pass the temp_dir as repo_root for path normalization
                    ast_info = parser.parse_file(file_info['absolute_path'], temp_dir)
                    if ast_info:
                        parsed_files.append(ast_info)
                    
                    # Send progress update every 10 files
                    if (i + 1) % 10 == 0 or i == len(files) - 1:
                        progress = {
                            'status': 'parsing_progress',
                            'current': i + 1,
                            'total': len(files),
                            'message': f'Parsed {i + 1}/{len(files)} files'
                        }
                        yield f"data: {json.dumps(progress)}\n\n"
                        
                except Exception as e:
                    logger.warning(f"Error parsing file {file_info['path']}: {e}")
            
            yield f"data: {json.dumps({'status': 'progress', 'message': f'Successfully parsed {len(parsed_files)} files'})}\n\n"
            
            # Step 3: Chunk code
            yield f"data: {json.dumps({'status': 'chunking', 'message': 'Creating code chunks'})}\n\n"
            
            all_chunks = chunker.chunk_repository(parsed_files, temp_dir)
            yield f"data: {json.dumps({'status': 'progress', 'message': f'Created {len(all_chunks)} code chunks'})}\n\n"
            
            # Step 4: Generate summaries
            yield f"data: {json.dumps({'status': 'summarizing', 'message': 'Generating chunk summaries'})}\n\n"
            
            summarized_chunks = await summarizer.summarize_chunks_optimized(all_chunks)
            yield f"data: {json.dumps({'status': 'progress', 'message': f'Generated summaries for {len(summarized_chunks)} chunks'})}\n\n"
            
            # Step 5: Index into Neo4j
            yield f"data: {json.dumps({'status': 'indexing', 'message': 'Indexing into graph database'})}\n\n"
            
            graph_service.upsert_repository_data(repo_info, summarized_chunks, parsed_files)
            
            # Get final stats
            stats = graph_service.get_repository_stats(repo_info['name'], repo_info['owner'])
            
            # Update cache with analysis results
            cache_service.update_repository_cache(
                repo_url=repo_url,
                repo_name=f"{repo_info['owner']}/{repo_info['name']}",
                commit_hash=repo_info.get('commit_hash'),
                stats=stats
            )
            
            # Grant user access to the repository
            cache_service.grant_user_access(current_user, repo_url)
            
            yield f"data: {json.dumps({'status': 'complete', 'message': 'Repository analysis complete', 'stats': stats})}\n\n"
            
        except Exception as e:
            logger.error(f"Error during repository analysis: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': f'Analysis failed: {str(e)}'})}\n\n"
        
        finally:
            # Cleanup
            try:
                cloner.cleanup()
            except:
                pass
    
    return StreamingResponse(
        process_repository(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/popular")
async def get_popular_repositories(limit: int = 10):
    """Get popular repositories (public endpoint)"""
    try:
        repositories = cache_service.get_popular_repositories(limit)
        return {
            "repositories": repositories,
            "total": len(repositories)
        }
    except Exception as e:
        logger.error(f"Error fetching popular repositories: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch popular repositories"
        )


@router.delete("/cache/{repo_name:path}")
async def invalidate_repository_cache(
    repo_name: str,
    current_user: User = Depends(get_current_user)
):
    """Invalidate repository cache (admin/owner only for now)"""
    try:
        # For now, allow any authenticated user to invalidate cache
        # In production, add proper authorization
        repo_url = f"https://github.com/{repo_name}"
        cache_service.invalidate_repository_cache(repo_url)
        
        return {"message": f"Cache invalidated for repository: {repo_name}"}
        
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to invalidate cache"
        )


@router.get("/stats/{owner}/{name}")
async def get_repository_stats(owner: str, name: str):
    """Get statistics for an analyzed repository"""
    try:
        graph_service = GraphService()
        stats = graph_service.get_repository_stats(name, owner)
        
        if stats['files'] == 0:
            raise HTTPException(status_code=404, detail="Repository not found or not analyzed")
        
        return {
            "repository": f"{owner}/{name}",
            "statistics": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting repository stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/user")
async def get_user_repositories(current_user: User = Depends(get_current_user)):
    """Get repositories accessible to the current user"""
    try:
        repositories = cache_service.get_user_repositories(current_user)
        return {
            "repositories": repositories,
            "total": len(repositories)
        }
    except Exception as e:
        logger.error(f"Error fetching user repositories: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch user repositories"
        )
