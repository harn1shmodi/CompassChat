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
import html
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/changelog", tags=["changelog"])


def simple_markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML"""
    if not text:
        return ""
    
    # Escape HTML characters first
    text = html.escape(text)
    
    # Convert headers
    text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    
    # Convert bold and italic
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    
    # Convert links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    # Convert inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Convert code blocks
    text = re.sub(r'^```(\w*)\n(.*?)^```', r'<pre><code>\2</code></pre>', text, flags=re.MULTILINE | re.DOTALL)
    
    # Handle the specific case where there might be "- text:" followed by multiple "- item" lines
    # This transforms poorly formatted lists into proper nested lists
    lines = text.split('\n')
    formatted_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        # Check if this is a line like "- **API & Interface Modifications**:"
        if re.match(r'^- \*\*.*?\*\*:\s*$', line):
            formatted_lines.append(line)
            # Look ahead to see if the next lines are indented items
            i += 1
            while i < len(lines) and lines[i].strip().startswith('- '):
                # Convert these to indented list items
                formatted_lines.append('    ' + lines[i])
                i += 1
            continue
        else:
            formatted_lines.append(line)
            i += 1
    
    text = '\n'.join(formatted_lines)
    
    # Convert lists (including nested and indented content)
    lines = text.split('\n')
    in_list = False
    result_lines = []
    
    for line in lines:
        # Check for list items (including indented ones)
        if re.match(r'^[-*+] ', line) or re.match(r'^    [-*+] ', line):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            # Remove list marker and any leading spaces
            item_text = re.sub(r'^(\s*)[-*+] ', '', line)
            result_lines.append(f'<li>{item_text}</li>')
        # Check for indented content that continues a list item
        elif in_list and re.match(r'^    ', line) and line.strip():
            # This is continued content for the previous list item
            # Remove the li tag from the last line and append this content
            if result_lines and result_lines[-1].startswith('<li>') and result_lines[-1].endswith('</li>'):
                # Remove the closing </li> tag
                result_lines[-1] = result_lines[-1][:-5]
                # Add the continued content
                continued_text = line.strip()
                result_lines[-1] += f' {continued_text}</li>'
            else:
                result_lines.append(line)
        else:
            if in_list and line.strip() == '':
                # Empty line within list - keep the list open
                result_lines.append('')
            elif in_list and not re.match(r'^[-*+] ', line) and not re.match(r'^    ', line):
                # Non-list content - close the list
                result_lines.append('</ul>')
                in_list = False
                result_lines.append(line)
            else:
                result_lines.append(line)
    
    if in_list:
        result_lines.append('</ul>')
    
    text = '\n'.join(result_lines)
    
    # Convert horizontal rules
    text = re.sub(r'^---+$', '<hr>', text, flags=re.MULTILINE)
    
    # Convert line breaks to paragraphs
    paragraphs = text.split('\n\n')
    formatted_paragraphs = []
    
    for para in paragraphs:
        para = para.strip()
        if para and not para.startswith('<'):
            # Convert single line breaks to <br> within paragraphs
            para = para.replace('\n', '<br>')
            para = f'<p>{para}</p>'
        formatted_paragraphs.append(para)
    
    return '\n'.join(formatted_paragraphs)


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
    custom_version: Optional[str] = None  # Custom version override


class ChangelogResponse(BaseModel):
    id: Optional[str]
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
            changelog_format=request.changelog_format,
            custom_version=request.custom_version
        )
        
        # Store the changelog if generation was successful
        changelog_id = None
        if changelog_result.get('version') and changelog_result.get('content'):
            changelog_id = changelog_service.store_changelog(
                request.repo_owner,
                request.repo_name,
                changelog_result,
                current_user.username
            )
            if not changelog_id:
                logger.warning(f"Failed to store changelog for {request.repo_owner}/{request.repo_name}")
        
        # Add the changelog ID to the result
        if changelog_id:
            changelog_result['id'] = changelog_id
        
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
                changelog_result,
                current_user.username
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
        history = changelog_service.get_changelog_history(repo_owner, repo_name, current_user.username)
        
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
        
        # Get changelog history (public endpoint - no user_id)
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


@router.post("/publish/{repo_owner}/{repo_name}/{version}")
async def publish_changelog(
    repo_owner: str,
    repo_name: str,
    version: str,
    current_user: User = Depends(get_current_user)
):
    """Publish a specific changelog version to make it publicly accessible"""
    try:
        changelog_service = ChangelogService()
        
        # Publish the changelog version
        success = changelog_service.publish_changelog(
            repo_owner, 
            repo_name, 
            version, 
            current_user.username
        )
        
        if success:
            return {
                "message": f"Successfully published changelog {version} for {repo_owner}/{repo_name}",
                "version": version,
                "published": True
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Changelog version {version} not found for repository {repo_owner}/{repo_name}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing changelog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ChangelogUpdateRequest(BaseModel):
    content: str


@router.put("/update/{repo_owner}/{repo_name}/{changelog_id}")
async def update_changelog(
    repo_owner: str,
    repo_name: str,
    changelog_id: str,
    request: ChangelogUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Update the content of an existing changelog entry"""
    try:
        changelog_service = ChangelogService()
        
        # Update the changelog content
        success = changelog_service.update_changelog(
            repo_owner, 
            repo_name, 
            changelog_id,
            request.content,
            current_user.username
        )
        
        if success:
            return {
                "message": f"Successfully updated changelog {changelog_id} for {repo_owner}/{repo_name}",
                "changelog_id": changelog_id,
                "updated": True
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Changelog {changelog_id} not found for repository {repo_owner}/{repo_name} or access denied"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating changelog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _generate_changelog_html(repo_owner: str, repo_name: str, changelog_history: List[Dict[str, Any]]) -> str:
    """Generate beautiful HTML for public changelog viewing with markdown rendering and dark mode"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en" data-theme="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{repo_owner}/{repo_name} Changelog</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
            
            :root {{
                /* Light theme - matching your app's index.css */
                --background: 0 0% 98.8235%;
                --foreground: 0 0% 9.0196%;
                --card: 0 0% 98.8235%;
                --card-foreground: 0 0% 9.0196%;
                --popover: 0 0% 98.8235%;
                --popover-foreground: 0 0% 32.1569%;
                --primary: 151.3274 66.8639% 66.8627%;
                --primary-foreground: 153.3333 13.0435% 13.5294%;
                --secondary: 0 0% 99.2157%;
                --secondary-foreground: 0 0% 9.0196%;
                --muted: 0 0% 92.9412%;
                --muted-foreground: 0 0% 12.5490%;
                --accent: 0 0% 92.9412%;
                --accent-foreground: 0 0% 12.5490%;
                --destructive: 9.8901 81.9820% 43.5294%;
                --destructive-foreground: 0 100% 99.4118%;
                --border: 0 0% 87.4510%;
                --input: 0 0% 96.4706%;
                --ring: 151.3274 66.8639% 66.8627%;
                --chart-1: 151.3274 66.8639% 66.8627%;
                --chart-2: 217.2193 91.2195% 59.8039%;
                --chart-3: 258.3117 89.5349% 66.2745%;
                --chart-4: 37.6923 92.1260% 50.1961%;
                --chart-5: 160.1183 84.0796% 39.4118%;
                --radius: 0.5rem;
            }}
            
            [data-theme="dark"] {{
                /* Dark theme - matching your app's index.css */
                --background: 0 0% 7.0588%;
                --foreground: 214.2857 31.8182% 91.3725%;
                --card: 0 0% 9.0196%;
                --card-foreground: 214.2857 31.8182% 91.3725%;
                --popover: 0 0% 14.1176%;
                --popover-foreground: 0 0% 66.2745%;
                --primary: 154.8980 100.0000% 19.2157%;
                --primary-foreground: 152.7273 19.2982% 88.8235%;
                --secondary: 0 0% 14.1176%;
                --secondary-foreground: 0 0% 98.0392%;
                --muted: 0 0% 12.1569%;
                --muted-foreground: 0 0% 63.5294%;
                --accent: 0 0% 19.2157%;
                --accent-foreground: 0 0% 98.0392%;
                --destructive: 12.0000 45.0000% 45.0000%;
                --destructive-foreground: 12.0000 12.1951% 91.9608%;
                --border: 0 0% 16.0784%;
                --input: 0 0% 14.1176%;
                --ring: 141.8919 69.1589% 58.0392%;
                --chart-1: 141.8919 69.1589% 58.0392%;
                --chart-2: 213.1169 93.9024% 67.8431%;
                --chart-3: 255.1351 91.7355% 76.2745%;
                --chart-4: 43.2558 96.4126% 56.2745%;
                --chart-5: 172.4551 66.0079% 50.3922%;
            }}
            
            * {{
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                line-height: 1.6;
                color: hsl(var(--foreground));
                background: hsl(var(--background));
                margin: 0;
                padding: 0;
                transition: all 0.3s ease;
                min-height: 100vh;
                letter-spacing: 0.025em;
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 2rem;
                animation: containerSlideIn 0.8s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                z-index: 1;
            }}
            
            @keyframes containerSlideIn {{
                from {{
                    opacity: 0;
                    transform: translateY(30px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .header {{
                text-align: center;
                margin-bottom: 3rem;
                padding: 2rem;
                background: hsl(var(--card));
                border: 1px solid hsl(var(--border));
                border-radius: var(--radius);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                position: relative;
                animation: headerSlideDown 0.6s ease-out 0.2s both;
            }}
            
            .header::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: hsl(var(--primary));
            }}
            
            @keyframes headerSlideDown {{
                from {{
                    opacity: 0;
                    transform: translateY(-20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .header h1 {{
                margin: 0 0 0.5rem 0;
                font-size: 2.5rem;
                font-weight: 700;
                color: hsl(var(--foreground));
                animation: titleBounceIn 0.8s ease-out 0.4s both;
            }}
            
            @keyframes titleBounceIn {{
                from {{
                    opacity: 0;
                    transform: translateY(-20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .header p {{
                margin: 0;
                font-size: 1.1rem;
                color: hsl(var(--muted-foreground));
                font-weight: 500;
                animation: subtitleFadeIn 0.6s ease-out 0.6s both;
                position: relative;
                z-index: 2;
            }}
            
            @keyframes subtitleFadeIn {{
                from {{
                    opacity: 0;
                    transform: translateY(10px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .theme-toggle {{
                position: absolute;
                top: 1rem;
                right: 1rem;
                background: hsl(var(--secondary));
                border: 1px solid hsl(var(--border));
                border-radius: var(--radius);
                padding: 0.5rem;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.9rem;
                color: hsl(var(--foreground));
                animation: toggleSlideIn 0.5s ease-out 0.8s both;
                z-index: 3;
            }}
            
            .theme-toggle:hover {{
                background: hsl(var(--accent));
                border-color: hsl(var(--primary));
                transform: translateY(-1px);
            }}
            
            @keyframes toggleSlideIn {{
                from {{
                    opacity: 0;
                    transform: translateX(20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateX(0);
                }}
            }}
            
            .changelog-entries {{
                display: flex;
                flex-direction: column;
                gap: 2rem;
                animation: entriesSlideIn 0.6s ease-out 1s both;
            }}
            
            @keyframes entriesSlideIn {{
                from {{
                    opacity: 0;
                    transform: translateY(20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .changelog-entry {{
                background: hsl(var(--card));
                border: 1px solid hsl(var(--border));
                border-radius: var(--radius);
                padding: 2rem;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                transition: all 0.3s ease;
                position: relative;
                animation: entrySlideUp var(--entry-delay, 1.2s) ease-out both;
            }}
            
            .changelog-entry::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: hsl(var(--primary));
                opacity: 0;
                transition: opacity 0.3s ease;
            }}
            
            .changelog-entry:hover {{
                border-color: hsl(var(--primary));
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
                transform: translateY(-2px);
            }}
            
            .changelog-entry:hover::before {{
                opacity: 1;
            }}
            
            @keyframes entrySlideUp {{
                from {{
                    opacity: 0;
                    transform: translateY(30px) scale(0.95);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }}
            }}
            
            .entry-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1.5rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid hsl(var(--border));
            }}
            
            .version-badge {{
                background: hsl(var(--primary));
                color: hsl(var(--primary-foreground));
                padding: 0.5rem 1rem;
                border-radius: var(--radius);
                font-size: 1.1rem;
                font-weight: 600;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                transition: all 0.3s ease;
            }}
            
            .version-badge:hover {{
                transform: scale(1.05);
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
            }}
            
            .entry-date {{
                color: hsl(var(--muted-foreground));
                font-size: 0.9rem;
                font-weight: 500;
            }}
            
            .content {{
                color: hsl(var(--foreground));
                line-height: 1.7;
                position: relative;
                z-index: 1;
                animation: contentFadeIn 0.5s ease-out 0.3s both;
            }}
            
            @keyframes contentFadeIn {{
                from {{
                    opacity: 0;
                    transform: translateY(10px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {{
                color: hsl(var(--foreground));
                margin-top: 2rem;
                margin-bottom: 1rem;
                font-weight: 600;
            }}
            
            .content h1 {{
                font-size: 2rem;
                border-bottom: 2px solid hsl(var(--border));
                padding-bottom: 0.5rem;
            }}
            
            .content h2 {{
                font-size: 1.5rem;
                color: hsl(var(--chart-1));
            }}
            
            .content h3 {{
                font-size: 1.2rem;
                color: hsl(var(--foreground));
            }}
            
            .content p {{
                margin-bottom: 1rem;
            }}
            
            .content ul, .content ol {{
                margin: 1rem 0;
                padding-left: 2rem;
            }}
            
            .content li {{
                margin-bottom: 0.5rem;
            }}
            
            .content strong {{
                color: hsl(var(--foreground));
                font-weight: 600;
            }}
            
            .content em {{
                color: hsl(var(--chart-1));
                font-style: italic;
            }}
            
            .content code {{
                background: hsl(var(--muted));
                color: hsl(var(--chart-2));
                padding: 0.2rem 0.4rem;
                border-radius: calc(var(--radius) * 0.5);
                font-size: 0.9em;
                font-family: 'Monaco', 'Cascadia Code', 'Roboto Mono', monospace;
            }}
            
            .content pre {{
                background: hsl(var(--muted));
                border: 1px solid hsl(var(--border));
                border-radius: var(--radius);
                padding: 1rem;
                overflow-x: auto;
                margin: 1rem 0;
            }}
            
            .content blockquote {{
                border-left: 4px solid hsl(var(--chart-1));
                background: hsl(var(--muted) / 0.5);
                padding: 1rem;
                margin: 1rem 0;
                border-radius: var(--radius);
            }}
            
            .content a {{
                color: hsl(var(--chart-1));
                text-decoration: none;
                border-bottom: 1px solid transparent;
                transition: all 0.3s ease;
            }}
            
            .content a:hover {{
                border-bottom-color: hsl(var(--chart-1));
            }}
            
            .content hr {{
                border: none;
                height: 1px;
                background: linear-gradient(90deg, transparent, hsl(var(--border)), transparent);
                margin: 2rem 0;
            }}
            
            .empty-state {{
                text-align: center;
                padding: 4rem 2rem;
                color: hsl(var(--muted-foreground));
            }}
            
            .empty-state h2 {{
                color: hsl(var(--foreground));
                margin-bottom: 1rem;
            }}
            
            .footer {{
                text-align: center;
                margin-top: 3rem;
                padding: 2rem;
                background: hsl(var(--card));
                border: 1px solid hsl(var(--border));
                border-radius: var(--radius);
                color: hsl(var(--muted-foreground));
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                animation: footerSlideUp 0.6s ease-out 1.4s both;
            }}
            
            @keyframes footerSlideUp {{
                from {{
                    opacity: 0;
                    transform: translateY(20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            .footer p {{
                margin: 0;
                font-size: 0.9rem;
            }}
            
            /* Responsive Design */
            @media (max-width: 768px) {{
                .container {{
                    padding: 1rem;
                }}
                
                .header h1 {{
                    font-size: 2rem;
                }}
                
                .entry-header {{
                    flex-direction: column;
                    gap: 1rem;
                    align-items: flex-start;
                }}
                
                .changelog-entry {{
                    padding: 1.5rem;
                }}
                
                .theme-toggle {{
                    position: static;
                    margin-top: 1rem;
                }}
            }}
            
            /* Animation for theme transitions */
            * {{
                transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="theme-toggle" onclick="toggleTheme()">
                    <span id="theme-text">Dark Mode</span>
                </div>
                <h1>{repo_owner}/{repo_name}</h1>
                <p>Project Changelog</p>
            </div>
            
            <div class="changelog-entries">
    """
    
    if not changelog_history:
        html_content += """
                <div class="empty-state">
                    <h2>No Published Changelog Entries</h2>
                    <p>This repository doesn't have any published changelog entries yet.</p>
                    <p>Check back later for updates!</p>
                </div>
        """
    else:
        for index, entry in enumerate(changelog_history):
            version = entry.get('version', 'Unknown Version')
            date = entry.get('date', 'Unknown Date')
            content = entry.get('content', 'No content available')
            
            # Calculate staggered animation delay
            animation_delay = 1.2 + (index * 0.15)  # Start at 1.2s, then 0.15s apart
            
            # Parse date if it's ISO format
            try:
                if 'T' in date:
                    parsed_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
                    formatted_date = parsed_date.strftime('%B %d, %Y')
                else:
                    formatted_date = date
            except:
                formatted_date = date
            
            # Convert markdown to HTML server-side
            rendered_content = simple_markdown_to_html(content)
            
            html_content += f"""
                <div class="changelog-entry" style="--entry-delay: {animation_delay}s;">
                    <div class="content">
                        {rendered_content}
                    </div>
                </div>
            """
    
    html_content += """
            </div>
            
            <div class="footer">
                <p>Generated by CompassChat</p>
            </div>
        </div>
        
        <script>
            function toggleTheme() {
                const html = document.documentElement;
                const themeText = document.getElementById('theme-text');
                
                // Add transition class for smooth theme switching
                document.body.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
                
                if (html.getAttribute('data-theme') === 'dark') {
                    html.setAttribute('data-theme', 'light');
                    themeText.textContent = 'Light Mode';
                    localStorage.setItem('theme', 'light');
                } else {
                    html.setAttribute('data-theme', 'dark');
                    themeText.textContent = 'Dark Mode';
                    localStorage.setItem('theme', 'dark');
                }
                
                // Remove transition after animation
                setTimeout(() => {
                    document.body.style.transition = '';
                }, 400);
            }
            
            // Load saved theme or default to dark
            const savedTheme = localStorage.getItem('theme') || 'dark';
            const html = document.documentElement;
            const themeText = document.getElementById('theme-text');
            
            html.setAttribute('data-theme', savedTheme);
            if (savedTheme === 'light') {
                themeText.textContent = 'Light Mode';
            } else {
                themeText.textContent = 'Dark Mode';
            }
            
            // Add scroll animations for better UX
            function addScrollAnimations() {
                const entries = document.querySelectorAll('.changelog-entry');
                
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.style.opacity = '1';
                            entry.target.style.transform = 'translateY(0) scale(1)';
                        }
                    });
                }, {
                    threshold: 0.1,
                    rootMargin: '0px 0px -50px 0px'
                });
                
                entries.forEach(entry => {
                    observer.observe(entry);
                });
            }
            
            // Add smooth scrolling for anchor links
            function addSmoothScrolling() {
                document.querySelectorAll('a[href^="#"]').forEach(anchor => {
                    anchor.addEventListener('click', function (e) {
                        e.preventDefault();
                        const target = document.querySelector(this.getAttribute('href'));
                        if (target) {
                            target.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start'
                            });
                        }
                    });
                });
            }
            
            // Enhanced theme toggle with visual feedback
            document.querySelector('.theme-toggle')?.addEventListener('click', function() {
                this.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    this.style.transform = '';
                }, 150);
            });
            
            // Add loading animation completion
            document.addEventListener('DOMContentLoaded', function() {
                // Mark page as loaded for CSS animations
                document.body.classList.add('loaded');
                
                // Initialize scroll animations after page load
                setTimeout(() => {
                    addScrollAnimations();
                    addSmoothScrolling();
                }, 100);
                
                // Add hover effects for code blocks
                document.querySelectorAll('pre code').forEach(code => {
                    code.addEventListener('mouseenter', function() {
                        this.style.transform = 'scale(1.01)';
                    });
                    code.addEventListener('mouseleave', function() {
                        this.style.transform = 'scale(1)';
                    });
                });
            });
        </script>
    </body>
    </html>
    """
    
    return html_content


@router.get("/cache/stats")
async def get_cache_stats(current_user: User = Depends(get_current_user)):
    """Get changelog generation cache statistics"""
    try:
        changelog_service = ChangelogService()
        cache_stats = changelog_service.get_cache_info()
        
        return {
            "cache_statistics": cache_stats,
            "optimization_info": {
                "description": "File context caching reduces LLM calls for repeated file analysis",
                "benefits": [
                    "Faster changelog generation for files analyzed before",
                    "Reduced OpenAI API costs",
                    "Better performance for repositories with overlapping file changes"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cache statistics")


@router.post("/cache/clear")
async def clear_cache(repo_name: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """Clear changelog generation cache (admin function)"""
    try:
        changelog_service = ChangelogService()
        
        if repo_name:
            changelog_service.clear_cache(repo_name)
            return {"message": f"Cache cleared for repository: {repo_name}"}
        else:
            changelog_service.clear_cache()
            return {"message": "All cache cleared successfully"}
            
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")