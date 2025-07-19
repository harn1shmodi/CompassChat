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
                changelog_result,
                current_user.username
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
            :root {{
                /* Light theme */
                --background: 0 0% 100%;
                --foreground: 240 10% 3.9%;
                --card: 0 0% 100%;
                --card-foreground: 240 10% 3.9%;
                --popover: 0 0% 100%;
                --popover-foreground: 240 10% 3.9%;
                --primary: 240 5.9% 10%;
                --primary-foreground: 0 0% 98%;
                --secondary: 240 4.8% 95.9%;
                --secondary-foreground: 240 5.9% 10%;
                --muted: 240 4.8% 95.9%;
                --muted-foreground: 240 3.8% 46.1%;
                --accent: 240 4.8% 95.9%;
                --accent-foreground: 240 5.9% 10%;
                --destructive: 0 84.2% 60.2%;
                --destructive-foreground: 0 0% 98%;
                --border: 240 5.9% 90%;
                --input: 240 5.9% 90%;
                --ring: 240 10% 3.9%;
                --chart-1: 12 76% 61%;
                --chart-2: 173 58% 39%;
                --chart-3: 197 37% 24%;
                --chart-4: 43 74% 66%;
                --chart-5: 27 87% 67%;
                --radius: 0.5rem;
            }}
            
            [data-theme="dark"] {{
                /* Dark theme */
                --background: 240 10% 3.9%;
                --foreground: 0 0% 98%;
                --card: 240 10% 3.9%;
                --card-foreground: 0 0% 98%;
                --popover: 240 10% 3.9%;
                --popover-foreground: 0 0% 98%;
                --primary: 0 0% 98%;
                --primary-foreground: 240 5.9% 10%;
                --secondary: 240 3.7% 15.9%;
                --secondary-foreground: 0 0% 98%;
                --muted: 240 3.7% 15.9%;
                --muted-foreground: 240 5% 64.9%;
                --accent: 240 3.7% 15.9%;
                --accent-foreground: 0 0% 98%;
                --destructive: 0 62.8% 30.6%;
                --destructive-foreground: 0 0% 98%;
                --border: 240 3.7% 15.9%;
                --input: 240 3.7% 15.9%;
                --ring: 240 4.9% 83.9%;
                --chart-1: 220 70% 50%;
                --chart-2: 160 60% 45%;
                --chart-3: 30 80% 55%;
                --chart-4: 280 65% 60%;
                --chart-5: 340 75% 55%;
            }}
            
            * {{
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                line-height: 1.6;
                color: hsl(var(--foreground));
                background: hsl(var(--background));
                margin: 0;
                padding: 0;
                transition: all 0.3s ease;
                min-height: 100vh;
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 2rem;
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
                overflow: hidden;
            }}
            
            .header::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(90deg, hsl(var(--chart-1)), hsl(var(--chart-2)), hsl(var(--chart-3)));
            }}
            
            .header h1 {{
                margin: 0 0 0.5rem 0;
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, hsl(var(--primary)), hsl(var(--chart-1)));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .header p {{
                margin: 0;
                font-size: 1.1rem;
                color: hsl(var(--muted-foreground));
                font-weight: 500;
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
            }}
            
            .theme-toggle:hover {{
                background: hsl(var(--accent));
                border-color: hsl(var(--primary));
                transform: translateY(-1px);
            }}
            
            .changelog-entries {{
                display: flex;
                flex-direction: column;
                gap: 2rem;
            }}
            
            .changelog-entry {{
                background: hsl(var(--card));
                border: 1px solid hsl(var(--border));
                border-radius: var(--radius);
                padding: 2rem;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                transition: all 0.3s ease;
                position: relative;
            }}
            
            .changelog-entry:hover {{
                border-color: hsl(var(--primary));
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
                transform: translateY(-2px);
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
                background: linear-gradient(135deg, hsl(var(--primary)), hsl(var(--chart-1)));
                color: hsl(var(--primary-foreground));
                padding: 0.5rem 1rem;
                border-radius: var(--radius);
                font-size: 1.1rem;
                font-weight: 600;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            
            .entry-date {{
                color: hsl(var(--muted-foreground));
                font-size: 0.9rem;
                font-weight: 500;
            }}
            
            .content {{
                color: hsl(var(--foreground));
                line-height: 1.7;
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
                color: hsl(var(--chart-2));
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
                color: hsl(var(--primary));
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
            
            # Convert markdown to HTML server-side
            rendered_content = simple_markdown_to_html(content)
            
            html_content += f"""
                <div class="changelog-entry">
                    <div class="entry-header">
                        <div class="version-badge">{html.escape(version)}</div>
                        <div class="entry-date">{html.escape(formatted_date)}</div>
                    </div>
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
                
                if (html.getAttribute('data-theme') === 'dark') {
                    html.setAttribute('data-theme', 'light');
                    themeText.textContent = 'Light Mode';
                    localStorage.setItem('theme', 'light');
                } else {
                    html.setAttribute('data-theme', 'dark');
                    themeText.textContent = 'Dark Mode';
                    localStorage.setItem('theme', 'dark');
                }
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
        </script>
    </body>
    </html>
    """
    
    return html_content