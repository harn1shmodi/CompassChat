from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from services.changelog_service import ChangelogService
from services.graph_service import GraphService
from core.database import User
from api.auth import get_current_user
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/changelog", tags=["changelog"])


class ChangelogGenerateRequest(BaseModel):
    repo_owner: str
    repo_name: str
    comparison_type: str = "auto"  # auto, since_tag, tag_to_tag, branch_to_branch, commit_count, since_date
    from_ref: Optional[str] = None  # Starting point (tag, branch, commit)
    to_ref: Optional[str] = "HEAD"  # Ending point (tag, branch, commit)
    comparison_range: Optional[str] = None  # Direct range specification (e.g., "v1.0.0..HEAD")
    since_version: Optional[str] = None  # Backward compatibility
    since_date: Optional[datetime] = None  # Date-based comparison
    target_audience: str = "users"  # users, developers, business, mixed
    changelog_format: str = "markdown"  # markdown, json


class ChangelogResponse(BaseModel):
    version: Optional[str]
    date: Optional[str]
    content: Optional[str]
    commits_analyzed: Optional[int]
    target_audience: Optional[str]
    format: Optional[str]
    metadata: Optional[Dict[str, Any]]
    error: Optional[str]


@router.post("/generate", response_model=ChangelogResponse)
async def generate_changelog(
    request: ChangelogGenerateRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate an AI-powered changelog for a repository"""
    try:
        changelog_service = ChangelogService()
        
        # For now, we'll generate a sample changelog since we need repo_path
        # In production, you'd either:
        # 1. Store repo paths when analyzing repositories
        # 2. Clone the repo temporarily for changelog generation
        # 3. Use Git API to get commit information
        
        # Check if repository exists in our system
        graph_service = GraphService()
        repo_identifier = f"{request.repo_owner}/{request.repo_name}"
        
        if not graph_service.repository_exists(repo_identifier):
            raise HTTPException(
                status_code=404,
                detail=f"Repository {repo_identifier} not found. Please analyze it first."
            )
        
        # Determine comparison range based on request
        comparison_range = None
        if request.comparison_range:
            comparison_range = request.comparison_range
        elif request.comparison_type == "auto":
            # Auto-detect will be handled by the service
            comparison_range = None
        elif request.comparison_type == "since_tag" and request.from_ref:
            comparison_range = f"{request.from_ref}..{request.to_ref}"
        elif request.comparison_type == "tag_to_tag" and request.from_ref and request.to_ref:
            comparison_range = f"{request.from_ref}..{request.to_ref}"
        elif request.comparison_type == "branch_to_branch" and request.from_ref and request.to_ref:
            comparison_range = f"{request.from_ref}..{request.to_ref}"
        elif request.comparison_type == "commit_count" and request.from_ref:
            comparison_range = f"{request.from_ref}..{request.to_ref}"
        
        # Generate changelog (this will return an error for now since we need repo_path)
        changelog_result = await changelog_service.generate_changelog_for_repo(
            request.repo_owner,
            request.repo_name,
            comparison_range=comparison_range,
            since_version=request.since_version,
            since_date=request.since_date,
            target_audience=request.target_audience,
            changelog_format=request.changelog_format
        )
        
        # Store the changelog if generation was successful
        if changelog_result.get('version') and changelog_result.get('content'):
            stored = changelog_service.store_changelog(
                request.repo_owner,
                request.repo_name,
                changelog_result
            )
            if not stored:
                logger.warning(f"Failed to store changelog for {request.repo_owner}/{request.repo_name}")
        
        # Return the changelog result
        return ChangelogResponse(**changelog_result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating changelog: {e}")
        return ChangelogResponse(
            error=str(e),
            version=None,
            date=None,
            content=None,
            commits_analyzed=0,
            target_audience=request.target_audience,
            format=request.changelog_format,
            metadata={}
        )


@router.post("/generate-with-path")
async def generate_changelog_with_path(
    repo_path: str,
    repo_owner: str,
    repo_name: str,
    comparison_type: str = "auto",
    from_ref: Optional[str] = None,
    to_ref: Optional[str] = "HEAD",
    comparison_range: Optional[str] = None,
    since_version: Optional[str] = None,
    since_date: Optional[datetime] = None,
    target_audience: str = "users",
    changelog_format: str = "markdown",
    current_user: User = Depends(get_current_user)
):
    """Generate changelog with direct repository path (for development/testing)"""
    try:
        changelog_service = ChangelogService()
        
        # Determine comparison range
        final_comparison_range = None
        if comparison_range:
            final_comparison_range = comparison_range
        elif comparison_type == "since_tag" and from_ref:
            final_comparison_range = f"{from_ref}..{to_ref}"
        elif comparison_type == "tag_to_tag" and from_ref and to_ref:
            final_comparison_range = f"{from_ref}..{to_ref}"
        elif comparison_type == "branch_to_branch" and from_ref and to_ref:
            final_comparison_range = f"{from_ref}..{to_ref}"
        elif comparison_type == "commit_count" and from_ref:
            final_comparison_range = f"{from_ref}..{to_ref}"
        
        # Generate changelog with repository path
        changelog_result = await changelog_service.generate_changelog(
            repo_path=repo_path,
            repo_name=f"{repo_owner}/{repo_name}",
            comparison_range=final_comparison_range,
            since_version=since_version,
            since_date=since_date,
            target_audience=target_audience,
            changelog_format=changelog_format
        )
        
        # Store the changelog if generation was successful
        if changelog_result.get('version') and changelog_result.get('content'):
            stored = changelog_service.store_changelog(
                repo_owner,
                repo_name,
                changelog_result
            )
            if not stored:
                logger.warning(f"Failed to store changelog for {repo_owner}/{repo_name}")
        
        return changelog_result
    
    except Exception as e:
        logger.error(f"Error generating changelog with path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{repo_owner}/{repo_name}")
async def get_changelog_history(
    repo_owner: str,
    repo_name: str,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    """Get changelog history for a repository"""
    try:
        changelog_service = ChangelogService()
        
        # Get changelog history
        history = changelog_service.get_changelog_history(repo_owner, repo_name)
        
        return {
            "repository": f"{repo_owner}/{repo_name}",
            "history": history[:limit],
            "total": len(history)
        }
    
    except Exception as e:
        logger.error(f"Error getting changelog history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public/{repo_owner}/{repo_name}")
async def get_public_changelog(
    repo_owner: str,
    repo_name: str,
    version: Optional[str] = Query(default=None, description="Specific version to retrieve"),
    format: str = Query(default="html", description="Response format: html, json, markdown")
):
    """Get public changelog for a repository (no authentication required)"""
    try:
        changelog_service = ChangelogService()
        
        # Get changelog history
        history = changelog_service.get_changelog_history(repo_owner, repo_name)
        
        if not history:
            raise HTTPException(
                status_code=404,
                detail="No changelog found for this repository"
            )
        
        # Filter by version if specified
        if version:
            history = [entry for entry in history if entry.get('version') == version]
            if not history:
                raise HTTPException(
                    status_code=404,
                    detail=f"Version {version} not found in changelog"
                )
        
        # Return based on format
        if format == "json":
            return JSONResponse(content={
                "repository": f"{repo_owner}/{repo_name}",
                "changelog": history
            })
        elif format == "markdown":
            markdown_content = "\n\n".join([
                entry.get('content', '') for entry in history
            ])
            return HTMLResponse(content=f"<pre>{markdown_content}</pre>")
        else:  # html
            return HTMLResponse(content=_generate_changelog_html(repo_owner, repo_name, history))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting public changelog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_changelog_templates(current_user: User = Depends(get_current_user)):
    """Get available changelog templates and configurations"""
    return {
        "audiences": {
            "users": {
                "name": "End Users",
                "description": "Focus on features and bug fixes that affect end users",
                "example": "New dark mode theme, Fixed login issues, Improved performance"
            },
            "developers": {
                "name": "Developers",
                "description": "Focus on API changes, breaking changes, and technical improvements",
                "example": "New REST API endpoints, Breaking: Changed authentication method, Updated dependencies"
            },
            "business": {
                "name": "Business Stakeholders",
                "description": "Focus on business value, ROI, and strategic improvements",
                "example": "Increased user retention by 15%, Reduced operational costs, New enterprise features"
            },
            "mixed": {
                "name": "Mixed Audience",
                "description": "Balanced approach covering all types of changes",
                "example": "Features for users, API changes for developers, business impact metrics"
            }
        },
        "formats": {
            "markdown": {
                "name": "Markdown",
                "description": "GitHub-style markdown format",
                "extension": ".md"
            },
            "json": {
                "name": "JSON",
                "description": "Structured JSON format for API consumption",
                "extension": ".json"
            }
        }
    }


@router.post("/preview")
async def preview_changelog(
    request: ChangelogGenerateRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate a preview of the changelog without saving it"""
    try:
        # This is similar to generate_changelog but for preview purposes
        # In a real implementation, you might want to use cached data or a subset of commits
        changelog_service = ChangelogService()
        
        # Generate a sample preview
        preview_result = {
            "version": "v1.2.3",
            "date": datetime.now().isoformat(),
            "content": f"""# v1.2.3

*Released: {datetime.now().strftime('%Y-%m-%d')}*

## 🚀 New Features
- Added new user dashboard with customizable widgets
- Implemented dark mode theme support
- Added export functionality for user data

## 🐛 Bug Fixes
- Fixed login issues with OAuth providers
- Resolved performance issues in file upload
- Fixed responsive design issues on mobile devices

## 🔧 Improvements
- Enhanced search functionality with better relevance
- Improved error messages for better user experience
- Updated dependencies for better security

## 🏠 Internal Changes
- Refactored authentication system
- Added comprehensive test coverage
- Improved code documentation

---
""",
            "commits_analyzed": 25,
            "target_audience": request.target_audience,
            "format": request.changelog_format,
            "metadata": {
                "breaking_changes": [],
                "commit_types": {
                    "feat": 8,
                    "fix": 12,
                    "docs": 3,
                    "chore": 2
                },
                "contributors": [
                    {"name": "John Doe", "email": "john@example.com", "commits": 15},
                    {"name": "Jane Smith", "email": "jane@example.com", "commits": 10}
                ]
            },
            "error": None
        }
    except Exception as e:
        logger.error(f"Error generating changelog preview: {e}")
        preview_result = {
            "error": str(e),
            "version": None,
            "date": None,
            "content": None,
            "commits_analyzed": 0,
            "target_audience": request.target_audience,
            "format": request.changelog_format,
            "metadata": {}
        }
        
        return ChangelogResponse(**preview_result)


@router.get("/comparison-points/{repo_owner}/{repo_name}")
async def get_comparison_points(
    repo_owner: str,
    repo_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get available comparison points for a repository"""
    try:
        changelog_service = ChangelogService()
        
        # For now, we need the actual repo path
        # In a production system, you might store this path or have a way to access it
        return {
            "error": "Repository path required for comparison point analysis. Use /comparison-points-with-path endpoint.",
            "available_types": [
                "auto",
                "since_tag", 
                "tag_to_tag",
                "branch_to_branch", 
                "commit_count",
                "since_date"
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting comparison points: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comparison-points-with-path")
async def get_comparison_points_with_path(
    repo_path: str,
    current_user: User = Depends(get_current_user)
):
    """Get available comparison points for a repository with direct path access"""
    try:
        changelog_service = ChangelogService()
        
        # Get comparison points
        comparison_points = await changelog_service.get_comparison_points(repo_path)
        
        return comparison_points
    
    except Exception as e:
        logger.error(f"Error getting comparison points with path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _generate_changelog_html(repo_owner: str, repo_name: str, changelog_history: List[Dict[str, Any]]) -> str:
    """Generate HTML for public changelog viewing"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{repo_owner}/{repo_name} Changelog</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f8f9fa;
            }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
                padding: 20px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .changelog-entry {{
                background-color: white;
                margin-bottom: 30px;
                padding: 25px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .version {{
                color: #0066cc;
                margin-bottom: 10px;
                border-bottom: 2px solid #e9ecef;
                padding-bottom: 10px;
            }}
            .date {{
                color: #6c757d;
                font-size: 0.9em;
                margin-bottom: 20px;
            }}
            .content {{
                line-height: 1.8;
            }}
            .content h2 {{
                color: #495057;
                margin-top: 25px;
                margin-bottom: 15px;
            }}
            .content h3 {{
                color: #6c757d;
                margin-top: 20px;
                margin-bottom: 10px;
            }}
            .content ul {{
                padding-left: 20px;
            }}
            .content li {{
                margin-bottom: 8px;
            }}
            .footer {{
                text-align: center;
                margin-top: 40px;
                padding: 20px;
                color: #6c757d;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{repo_owner}/{repo_name}</h1>
            <p>Changelog</p>
        </div>
        
        <div class="changelog-content">
    """
    
    if not changelog_history:
        html_content += """
            <div class="changelog-entry">
                <h2>No changelog entries found</h2>
                <p>This repository doesn't have any changelog entries yet.</p>
            </div>
        """
    else:
        for entry in changelog_history:
            version = entry.get('version', 'Unknown Version')
            date = entry.get('date', 'Unknown Date')
            content = entry.get('content', 'No content available')
            
            # Parse date if it's ISO format
            try:
                if 'T' in date:
                    parsed_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
                    formatted_date = parsed_date.strftime('%B %d, %Y')
                else:
                    formatted_date = date
            except:
                formatted_date = date
            
            html_content += f"""
            <div class="changelog-entry">
                <h2 class="version">{version}</h2>
                <p class="date">{formatted_date}</p>
                <div class="content">
                    <pre style="white-space: pre-wrap; font-family: inherit;">{content}</pre>
                </div>
            </div>
            """
    
    html_content += """
        </div>
        
        <div class="footer">
            <p>Generated by CompassChat AI-Powered Changelog</p>
        </div>
    </body>
    </html>
    """
    
    return html_content