from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from services.git_analysis import GitAnalysisService
from services.graph_service import GraphService
from services.github_clone import GitHubCloner
from services.ai_provider import ai_provider
from core.config import settings
from core.neo4j_conn import neo4j_conn
from openai import OpenAI
import logging
import json
import re
import uuid
import tempfile
import shutil

logger = logging.getLogger(__name__)


class ChangelogService:
    """Service for generating AI-powered changelogs"""
    
    def __init__(self):
        self.git_service = GitAnalysisService()
        self.graph_service = GraphService()
        self.github_cloner = GitHubCloner()
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
    
    async def generate_changelog(self, 
                                repo_path: str, 
                                repo_name: str,
                                since_version: Optional[str] = None,
                                since_date: Optional[datetime] = None,
                                comparison_range: Optional[str] = None,
                                target_audience: str = "users",
                                changelog_format: str = "markdown") -> Dict[str, Any]:
        """Generate an AI-powered changelog for a repository"""
        try:
            # Step 1: Get commits for changelog generation
            commits = self._get_commits_for_changelog(repo_path, since_version, since_date, comparison_range)
            
            if not commits:
                return {
                    "error": "No commits found for the specified range",
                    "version": None,
                    "date": None,
                    "content": None,
                    "commits_analyzed": 0,
                    "target_audience": target_audience,
                    "format": changelog_format,
                    "metadata": {}
                }
            
            # Step 2: Analyze code changes using GraphRAG
            code_analysis = await self._analyze_code_changes(commits, repo_name)
            
            # Step 3: Generate changelog content using AI
            changelog_content = await self._generate_changelog_content(
                commits, code_analysis, target_audience, changelog_format
            )
            
            # Step 4: Generate version number
            version = self._generate_version_number(commits, repo_path)
            
            # Step 5: Format final changelog
            formatted_changelog = self._format_changelog(
                version, changelog_content, changelog_format
            )
            
            return {
                "version": version,
                "date": datetime.now(timezone.utc).isoformat(),
                "content": formatted_changelog,
                "commits_analyzed": len(commits),
                "target_audience": target_audience,
                "format": changelog_format,
                "metadata": {
                    "breaking_changes": self._extract_breaking_changes(commits),
                    "commit_types": self._get_commit_type_summary(commits),
                    "contributors": self._get_contributors_summary(commits)
                },
                "error": None
            }
        except Exception as e:
            logger.error(f"Error generating changelog: {e}")
            return {
                "error": str(e),
                "version": None,
                "date": None,
                "content": None,
                "commits_analyzed": 0,
                "target_audience": target_audience,
                "format": changelog_format,
                "metadata": {}
            }
    
    def _get_commits_for_changelog(self, 
                                  repo_path: str, 
                                  since_version: Optional[str] = None,
                                  since_date: Optional[datetime] = None,
                                  comparison_range: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get commits for changelog generation using flexible comparison options"""
        try:
            if comparison_range:
                # Use explicit comparison range
                commits = self.git_service.get_commits_in_range(repo_path, comparison_range)
            elif since_version:
                # Get commits since a specific version/tag
                commits = self.git_service.get_commits_between_tags(repo_path, since_version)
            elif since_date:
                # Get commits since a specific date
                commits = self.git_service.get_commits_since(repo_path, since_date=since_date)
            else:
                # Auto-detect best comparison range
                comparison_info = self.git_service.detect_comparison_range(repo_path)
                recommended_range = comparison_info.get('recommended_range', 'HEAD~20..HEAD')
                commits = self.git_service.get_commits_in_range(repo_path, recommended_range)
            
            return commits
        except Exception as e:
            logger.error(f"Error getting commits for changelog: {e}")
            return []
    
    async def _analyze_code_changes(self, commits: List[Dict[str, Any]], repo_name: str) -> Dict[str, Any]:
        """Analyze code changes using GraphRAG to understand impact"""
        try:
            # Extract file paths from commits
            changed_files = set()
            for commit in commits:
                for file_info in commit.get('files_changed', []):
                    changed_files.add(file_info['path'])
            
            # Use GraphRAG to understand the context of changed files
            code_context = {}
            for file_path in list(changed_files)[:20]:  # Limit to prevent token overflow
                try:
                    # Query GraphRAG for context about this file
                    query = f"What is the purpose and functionality of {file_path}?"
                    context_results = self.graph_service.search_code(query, limit=3, repository=repo_name)
                    
                    if context_results:
                        code_context[file_path] = {
                            "purpose": context_results[0].get('summary', ''),
                            "functions": context_results[0].get('functions', []),
                            "classes": context_results[0].get('classes', []),
                            "language": context_results[0].get('language', ''),
                            "relevance_score": context_results[0].get('score', 0.0)
                        }
                except Exception as e:
                    logger.warning(f"Error analyzing file {file_path}: {e}")
            
            return {
                "changed_files": list(changed_files),
                "code_context": code_context,
                "analysis_summary": self._summarize_code_changes(code_context)
            }
        except Exception as e:
            logger.error(f"Error analyzing code changes: {e}")
            return {"changed_files": [], "code_context": {}, "analysis_summary": ""}
    
    def _summarize_code_changes(self, code_context: Dict[str, Any]) -> str:
        """Summarize the types of code changes"""
        if not code_context:
            return "No code context available"
        
        languages = set()
        components = []
        
        for file_path, context in code_context.items():
            if context.get('language'):
                languages.add(context['language'])
            
            # Identify component types
            if any(keyword in file_path.lower() for keyword in ['api', 'endpoint', 'route']):
                components.append("API")
            elif any(keyword in file_path.lower() for keyword in ['ui', 'component', 'view']):
                components.append("UI")
            elif any(keyword in file_path.lower() for keyword in ['service', 'logic', 'business']):
                components.append("Business Logic")
            elif any(keyword in file_path.lower() for keyword in ['test', 'spec']):
                components.append("Tests")
            elif any(keyword in file_path.lower() for keyword in ['config', 'settings']):
                components.append("Configuration")
        
        summary_parts = []
        if languages:
            summary_parts.append(f"Languages: {', '.join(languages)}")
        if components:
            summary_parts.append(f"Components: {', '.join(set(components))}")
        
        return "; ".join(summary_parts) if summary_parts else "Mixed code changes"
    
    async def _generate_changelog_content(self, 
                                        commits: List[Dict[str, Any]], 
                                        code_analysis: Dict[str, Any],
                                        target_audience: str,
                                        changelog_format: str) -> str:
        """Generate changelog content using AI"""
        try:
            # Prepare context for AI
            context = self._prepare_ai_context(commits, code_analysis, target_audience)
            
            # Get audience-specific prompt
            system_prompt = self._get_audience_prompt(target_audience, changelog_format)
            
            # Generate changelog using AI provider
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ]
            
            return ai_provider.generate_chat_completion(messages, max_tokens=1500, temperature=0.2)
        except Exception as e:
            logger.error(f"Error generating changelog content: {e}")
            return "Error generating changelog content"
    
    def _prepare_ai_context(self, commits: List[Dict[str, Any]], code_analysis: Dict[str, Any], target_audience: str) -> str:
        """Prepare context for AI changelog generation"""
        context_parts = []
        
        # Add repository analysis summary
        if code_analysis.get('analysis_summary'):
            context_parts.append(f"Code Analysis: {code_analysis['analysis_summary']}")
        
        # Group commits by type
        commit_groups = self._group_commits_by_type(commits)
        
        context_parts.append("\n## Commits by Type:")
        for commit_type, type_commits in commit_groups.items():
            context_parts.append(f"\n### {commit_type.upper()} ({len(type_commits)} commits):")
            for commit in type_commits[:10]:  # Limit to prevent token overflow
                context_parts.append(f"- {commit.get('summary', commit.get('message', ''))} ({commit.get('short_sha', '')})")
                
                # Add breaking changes if any
                if commit.get('breaking_changes'):
                    context_parts.append(f"  ⚠️  Breaking changes: {', '.join(commit['breaking_changes'])}")
        
        # Add file context if available
        if code_analysis.get('code_context'):
            context_parts.append("\n## Key Files Modified:")
            for file_path, context in list(code_analysis['code_context'].items())[:10]:
                if context.get('purpose'):
                    context_parts.append(f"- {file_path}: {context['purpose']}")
        
        return "\n".join(context_parts)
    
    def _group_commits_by_type(self, commits: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group commits by their type"""
        groups = {}
        for commit in commits:
            commit_type = commit.get('type', 'other')
            if commit_type not in groups:
                groups[commit_type] = []
            groups[commit_type].append(commit)
        
        return groups
    
    def _get_audience_prompt(self, target_audience: str, changelog_format: str) -> str:
        """Get AI prompt based on target audience"""
        base_prompt = f"""You are a technical writer creating a changelog in {changelog_format} format for {target_audience}. 
        
        Your task is to transform the provided commit information into a clear, well-organized changelog entry.
        
        IMPORTANT: Create a changelog that is specific to the actual code changes in the commits. Do NOT use generic placeholders or vague statements.
        
        Guidelines:
        - Focus on what matters most to {target_audience}
        - Use clear, concise language
        - Group related changes together
        - Highlight breaking changes prominently
        - Include relevant technical details where appropriate
        - Be specific about what functionality was added, changed, or fixed
        - Use actual file names, function names, and features from the commits
        - Do NOT use generic phrases like "comprehensive codebase" or "well-structured architecture"
        """
        
        audience_prompts = {
            "users": """
            Focus on:
            - New features and how they benefit users (based on actual commits)
            - Bug fixes that improve user experience (mention specific issues fixed)
            - UI/UX improvements (reference actual UI components or files changed)
            - Performance improvements users will notice (specify what got faster)
            - Avoid overly technical jargon but be specific about features
            - Explain the impact of changes in user-friendly terms
            - Use actual feature names and functionality from the commits
            """,
            "developers": """
            Focus on:
            - API changes and new endpoints (reference actual endpoints from commits)
            - Breaking changes with migration notes (specify what changed)
            - New developer tools and utilities (mention actual tools added)
            - Performance improvements with context (specify what was optimized)
            - Dependencies and library updates (list actual dependencies)
            - Technical debt improvements (reference actual refactoring)
            - Include actual function/class names and file paths where relevant
            """,
            "business": """
            Focus on:
            - Features that drive business value (based on actual feature commits)
            - Customer-requested improvements (reference actual functionality)
            - Market competitive advantages (mention specific capabilities)
            - Revenue-impacting changes (specify what business features were added)
            - Cost savings and efficiency improvements (reference actual optimizations)
            - Risk mitigation and security enhancements (mention specific security fixes)
            """,
            "mixed": """
            Focus on:
            - Balance between technical and user-facing changes (based on actual commits)
            - Categorize changes by their impact area using actual commit information
            - Use clear headings to separate concerns
            - Include both user benefits and technical details from real changes
            - Be specific about what was actually implemented, not generic descriptions
            """
        }
        
        return base_prompt + audience_prompts.get(target_audience, audience_prompts["mixed"])
    
    def _generate_version_number(self, commits: List[Dict[str, Any]], repo_path: str) -> str:
        """Generate version number based on commits"""
        try:
            # Get latest tag as base version
            latest_tag = self.git_service.get_latest_tag(repo_path)
            
            if not latest_tag:
                return "v1.0.0"
            
            # Parse version number
            version_match = re.search(r'v?(\d+)\.(\d+)\.(\d+)', latest_tag)
            if not version_match:
                return "v1.0.0"
            
            major, minor, patch = map(int, version_match.groups())
            
            # Determine version bump based on commits
            has_breaking = any(commit.get('breaking_changes') for commit in commits)
            has_features = any(commit.get('type') == 'feat' for commit in commits)
            
            if has_breaking:
                major += 1
                minor = 0
                patch = 0
            elif has_features:
                minor += 1
                patch = 0
            else:
                patch += 1
            
            return f"v{major}.{minor}.{patch}"
        except Exception as e:
            logger.error(f"Error generating version number: {e}")
            return "v1.0.0"
    
    def _format_changelog(self, version: str, content: str, changelog_format: str) -> str:
        """Format the final changelog"""
        if changelog_format == "markdown":
            return f"""# {version}

*Released: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*

{content}

---
"""
        elif changelog_format == "json":
            return json.dumps({
                "version": version,
                "date": datetime.now(timezone.utc).isoformat(),
                "content": content
            }, indent=2)
        else:
            return content
    
    def _extract_breaking_changes(self, commits: List[Dict[str, Any]]) -> List[str]:
        """Extract all breaking changes from commits"""
        breaking_changes = []
        for commit in commits:
            if commit.get('breaking_changes'):
                breaking_changes.extend(commit['breaking_changes'])
        return breaking_changes
    
    def _get_commit_type_summary(self, commits: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get summary of commit types"""
        type_counts = {}
        for commit in commits:
            commit_type = commit.get('type', 'other')
            type_counts[commit_type] = type_counts.get(commit_type, 0) + 1
        return type_counts
    
    def _get_contributors_summary(self, commits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get summary of contributors"""
        contributors = {}
        for commit in commits:
            author = commit.get('author', {})
            name = author.get('name', 'Unknown')
            email = author.get('email', 'unknown@example.com')
            
            if email not in contributors:
                contributors[email] = {
                    "name": name,
                    "email": email,
                    "commits": 0
                }
            contributors[email]["commits"] += 1
        
        return sorted(contributors.values(), key=lambda x: x['commits'], reverse=True)

    async def get_comparison_points(self, repo_path: str) -> Dict[str, Any]:
        """Get available comparison points for changelog generation"""
        try:
            # Get repository comparison information
            comparison_info = self.git_service.detect_comparison_range(repo_path)
            
            # Get all tags for tag-based comparisons
            all_tags = self.git_service.get_all_tags(repo_path)
            
            # Get branch information
            current_branch = self.git_service.get_current_branch(repo_path)
            main_branch = self.git_service.get_main_branch(repo_path)
            
            # Build comparison options
            comparison_options = {
                "recommended": {
                    "range": comparison_info.get('recommended_range'),
                    "type": comparison_info.get('recommended_type'),
                    "description": self._get_comparison_description(comparison_info.get('recommended_type'))
                },
                "tag_based": [],
                "branch_based": [],
                "commit_count": [
                    {"range": "HEAD~10..HEAD", "description": "Last 10 commits"},
                    {"range": "HEAD~20..HEAD", "description": "Last 20 commits"},
                    {"range": "HEAD~50..HEAD", "description": "Last 50 commits"}
                ],
                "repository_info": comparison_info.get('repository_info', {})
            }
            
            # Add tag-based options
            if all_tags:
                latest_tag = all_tags[0]['name'] if all_tags else None
                if latest_tag:
                    comparison_options["tag_based"].append({
                        "range": f"{latest_tag}..HEAD",
                        "description": f"Since {latest_tag} (latest tag)"
                    })
                
                # Add between-tags options
                for i in range(min(5, len(all_tags) - 1)):  # Up to 5 recent tag pairs
                    from_tag = all_tags[i + 1]['name']
                    to_tag = all_tags[i]['name']
                    comparison_options["tag_based"].append({
                        "range": f"{from_tag}..{to_tag}",
                        "description": f"Between {from_tag} and {to_tag}"
                    })
            
            # Add branch-based options
            if current_branch and current_branch != main_branch:
                comparison_options["branch_based"].extend([
                    {
                        "range": f"{main_branch}..{current_branch}",
                        "description": f"Changes in {current_branch} (vs {main_branch})"
                    },
                    {
                        "range": f"{current_branch}..{main_branch}",
                        "description": f"Changes in {main_branch} (vs {current_branch})"
                    }
                ])
            
            return comparison_options
            
        except Exception as e:
            logger.error(f"Error getting comparison points: {e}")
            return {
                "recommended": {
                    "range": "HEAD~20..HEAD",
                    "type": "commit_count",
                    "description": "Last 20 commits"
                },
                "tag_based": [],
                "branch_based": [],
                "commit_count": [],
                "repository_info": {}
            }
    
    def _get_comparison_description(self, comparison_type: str) -> str:
        """Get human-readable description for comparison type"""
        descriptions = {
            "since_tag": "Changes since the latest release tag",
            "branch_comparison": "Changes in the current branch compared to main",
            "commit_count": "Recent commits in the repository"
        }
        return descriptions.get(comparison_type, "Repository changes")

    async def generate_changelog_for_repo(self, repo_owner: str, repo_name: str, **kwargs) -> Dict[str, Any]:
        """Generate changelog for a repository that's already analyzed in the system"""
        try:
            # Check if repository exists in the graph
            repo_identifier = f"{repo_owner}/{repo_name}"
            if not self.graph_service.repository_exists(repo_identifier):
                return {
                    "error": f"Repository {repo_identifier} not found in system. Please analyze it first.",
                    "version": None,
                    "date": None,
                    "content": None,
                    "commits_analyzed": 0,
                    "target_audience": "users",
                    "format": "markdown",
                    "metadata": {}
                }
            
            # Generate changelog using repository data from Neo4j
            return await self._generate_changelog_from_graph(
                repo_owner, repo_name, **kwargs
            )
        except Exception as e:
            logger.error(f"Error generating changelog for repo {repo_owner}/{repo_name}: {e}")
            return {
                "error": str(e),
                "version": None,
                "date": None,
                "content": None,
                "commits_analyzed": 0,
                "target_audience": "users",
                "format": "markdown",
                "metadata": {}
            }
    
    def get_changelog_history(self, repo_owner: str, repo_name: str, user_id: str = None) -> List[Dict[str, Any]]:
        """Get changelog history for a repository with user isolation"""
        try:
            with neo4j_conn.get_session() as session:
                if user_id:
                    query = """
                    MATCH (repo:Repository {owner: $repo_owner, name: $repo_name, user_id: $user_id})-[:HAS_CHANGELOG]->(cl:Changelog)
                    RETURN cl.id as id, cl.version as version, cl.date as date, cl.content as content,
                           cl.target_audience as target_audience, cl.format as format,
                           cl.commits_analyzed as commits_analyzed, cl.breaking_changes as breaking_changes,
                           cl.commit_types as commit_types, cl.contributors as contributors,
                           cl.summary as summary, cl.is_published as is_published
                    ORDER BY cl.date DESC
                    """
                else:
                    query = """
                    MATCH (repo:Repository {owner: $repo_owner, name: $repo_name})-[:HAS_CHANGELOG]->(cl:Changelog)
                    WHERE cl.is_published = true
                    RETURN cl.id as id, cl.version as version, cl.date as date, cl.content as content,
                           cl.target_audience as target_audience, cl.format as format,
                           cl.commits_analyzed as commits_analyzed, cl.breaking_changes as breaking_changes,
                           cl.commit_types as commit_types, cl.contributors as contributors,
                           cl.summary as summary, cl.is_published as is_published
                    ORDER BY cl.date DESC
                    """
                
                results = session.run(query, {
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'user_id': user_id
                })
                
                changelog_entries = []
                for record in results:
                    entry = {
                        'id': record['id'],
                        'version': record['version'],
                        'date': record['date'],
                        'content': record['content'],
                        'target_audience': record['target_audience'],
                        'format': record['format'],
                        'summary': record['summary'],
                        'is_published': record['is_published'] if record['is_published'] is not None else False,
                        'metadata': {
                            'commits_analyzed': record['commits_analyzed'],
                            'breaking_changes': json.loads(record['breaking_changes']) if record['breaking_changes'] else [],
                            'commit_types': json.loads(record['commit_types']) if record['commit_types'] else {},
                            'contributors': json.loads(record['contributors']) if record['contributors'] else []
                        }
                    }
                    changelog_entries.append(entry)
                
                return changelog_entries
        except Exception as e:
            logger.error(f"Error getting changelog history: {e}")
            return []
    
    def store_changelog(self, repo_owner: str, repo_name: str, changelog_data: Dict[str, Any], user_id: str) -> bool:
        """Store changelog entry in the database"""
        try:
            with neo4j_conn.get_session() as session:
                # First, ensure the repository exists with user ownership
                repo_query = """
                MERGE (repo:Repository {owner: $repo_owner, name: $repo_name, user_id: $user_id})
                RETURN repo
                """
                session.run(repo_query, {
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'user_id': user_id
                })
                
                # Create changelog entry
                changelog_id = str(uuid.uuid4())
                changelog_query = """
                MATCH (repo:Repository {owner: $repo_owner, name: $repo_name, user_id: $user_id})
                CREATE (cl:Changelog {
                    id: $changelog_id,
                    version: $version,
                    date: $date,
                    content: $content,
                    target_audience: $target_audience,
                    format: $format,
                    commits_analyzed: $commits_analyzed,
                    breaking_changes: $breaking_changes,
                    commit_types: $commit_types,
                    contributors: $contributors,
                    summary: $summary,
                    repository_id: $repository_id,
                    is_published: $is_published,
                    created_at: datetime()
                })
                CREATE (repo)-[:HAS_CHANGELOG]->(cl)
                RETURN cl.id as id
                """
                
                metadata = changelog_data.get('metadata', {})
                
                result = session.run(changelog_query, {
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'changelog_id': changelog_id,
                    'version': changelog_data.get('version', ''),
                    'date': changelog_data.get('date', datetime.now(timezone.utc).isoformat()),
                    'content': changelog_data.get('content', ''),
                    'target_audience': changelog_data.get('target_audience', 'users'),
                    'format': changelog_data.get('format', 'markdown'),
                    'commits_analyzed': changelog_data.get('commits_analyzed', 0),
                    'breaking_changes': json.dumps(metadata.get('breaking_changes', [])),
                    'commit_types': json.dumps(metadata.get('commit_types', {})),
                    'contributors': json.dumps(metadata.get('contributors', [])),
                    'summary': self._generate_summary(changelog_data.get('content', '')),
                    'repository_id': f"{repo_owner}/{repo_name}",
                    'is_published': False,
                    'user_id': user_id
                })
                
                result.single()  # Ensure the query executed successfully
                logger.info(f"Stored changelog {changelog_data.get('version', 'unknown')} for {repo_owner}/{repo_name}")
                return True
                
        except Exception as e:
            logger.error(f"Error storing changelog: {e}")
            return False
    
    def _generate_summary(self, content: str) -> str:
        """Generate a brief summary of the changelog content"""
        if not content:
            return ""
        
        # Extract first few lines as summary
        lines = content.split('\n')
        summary_lines = []
        
        for line in lines:
            # Skip empty lines and headers
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('*Released'):
                summary_lines.append(line)
                if len(summary_lines) >= 3:
                    break
        
        summary = ' '.join(summary_lines)
        # Truncate if too long
        if len(summary) > 200:
            summary = summary[:200] + "..."
        
        return summary
    
    def delete_changelog(self, repo_owner: str, repo_name: str, changelog_id: str) -> bool:
        """Delete a changelog entry"""
        try:
            with neo4j_conn.get_session() as session:
                query = """
                MATCH (repo:Repository {owner: $repo_owner, name: $repo_name})-[:HAS_CHANGELOG]->(cl:Changelog {id: $changelog_id})
                DETACH DELETE cl
                RETURN count(cl) as deleted_count
                """
                
                result = session.run(query, {
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'changelog_id': changelog_id
                })
                
                deleted_count = result.single()['deleted_count']
                success = deleted_count > 0
                
                if success:
                    logger.info(f"Deleted changelog {changelog_id} for {repo_owner}/{repo_name}")
                else:
                    logger.warning(f"Changelog {changelog_id} not found for {repo_owner}/{repo_name}")
                
                return success
                
        except Exception as e:
            logger.error(f"Error deleting changelog: {e}")
            return False
    
    def publish_changelog(self, repo_owner: str, repo_name: str, version: str, user_id: str) -> bool:
        """Publish a specific changelog version to make it publicly accessible"""
        try:
            with neo4j_conn.get_session() as session:
                query = """
                MATCH (repo:Repository {owner: $repo_owner, name: $repo_name, user_id: $user_id})-[:HAS_CHANGELOG]->(cl:Changelog {version: $version})
                SET cl.is_published = true, cl.published_at = datetime()
                RETURN cl.id as id
                """
                
                result = session.run(query, {
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'version': version,
                    'user_id': user_id
                })
                
                record = result.single()
                success = record is not None
                
                if success:
                    logger.info(f"Published changelog {version} for {repo_owner}/{repo_name}")
                else:
                    logger.warning(f"Changelog {version} not found for {repo_owner}/{repo_name}")
                
                return success
                
        except Exception as e:
            logger.error(f"Error publishing changelog: {e}")
            return False
    
    async def _generate_changelog_from_graph(self, repo_owner: str, repo_name: str, **kwargs) -> Dict[str, Any]:
        """Generate changelog by temporarily cloning repository and analyzing Git history"""
        temp_dir = None
        try:
            # Extract parameters
            target_audience = kwargs.get('target_audience', 'users')
            changelog_format = kwargs.get('changelog_format', 'markdown')
            since_version = kwargs.get('since_version')
            since_date = kwargs.get('since_date')
            comparison_range = kwargs.get('comparison_range')
            
            # Construct GitHub URL
            github_url = f"https://github.com/{repo_owner}/{repo_name}.git"
            
            # Clone repository temporarily
            temp_dir = tempfile.mkdtemp(prefix="changelog_gen_")
            logger.info(f"Cloning repository {github_url} to {temp_dir}")
            
            try:
                import git
                repo = git.Repo.clone_from(github_url, temp_dir)
                logger.info(f"Successfully cloned repository {repo_owner}/{repo_name}")
            except Exception as clone_error:
                logger.error(f"Failed to clone repository: {clone_error}")
                return {
                    "error": f"Failed to clone repository {repo_owner}/{repo_name}. Repository may be private or not exist.",
                    "version": None,
                    "date": None,
                    "content": None,
                    "commits_analyzed": 0,
                    "target_audience": target_audience,
                    "format": changelog_format,
                    "metadata": {}
                }
            
            # Generate changelog using the cloned repository
            changelog_result = await self.generate_changelog(
                repo_path=temp_dir,
                repo_name=f"{repo_owner}/{repo_name}",
                since_version=since_version,
                since_date=since_date,
                comparison_range=comparison_range,
                target_audience=target_audience,
                changelog_format=changelog_format
            )
            
            return changelog_result
            
        except Exception as e:
            logger.error(f"Error generating changelog from graph: {e}")
            return {
                "error": str(e),
                "version": None,
                "date": None,
                "content": None,
                "commits_analyzed": 0,
                "target_audience": kwargs.get('target_audience', 'users'),
                "format": kwargs.get('changelog_format', 'markdown'),
                "metadata": {}
            }
        finally:
            # Clean up temporary directory
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temporary directory: {cleanup_error}")
    
    async def _get_repository_data(self, repo_owner: str, repo_name: str) -> Dict[str, Any]:
        """Get repository data from Neo4j graph"""
        try:
            with neo4j_conn.get_session() as session:
                query = """
                MATCH (repo:Repository {owner: $repo_owner, name: $repo_name})
                OPTIONAL MATCH (repo)-[:CONTAINS]->(file:File)
                OPTIONAL MATCH (file)-[:DEFINES]->(func:Function)
                OPTIONAL MATCH (file)-[:DEFINES]->(cls:Class)
                
                RETURN repo,
                       collect(DISTINCT {
                           path: file.path,
                           language: file.language,
                           content: file.content,
                           size: file.size
                       }) as files,
                       collect(DISTINCT {
                           name: func.name,
                           file_path: func.file_path,
                           language: func.language,
                           docstring: func.docstring
                       }) as functions,
                       collect(DISTINCT {
                           name: cls.name,
                           file_path: cls.file_path,
                           language: cls.language,
                           docstring: cls.docstring
                       }) as classes
                """
                
                result = session.run(query, {
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'user_id': user_id
                })
                
                record = result.single()
                if not record:
                    return {}
                
                return {
                    'repository': record['repo'],
                    'files': [f for f in record['files'] if f['path'] is not None],
                    'functions': [f for f in record['functions'] if f['name'] is not None],
                    'classes': [c for c in record['classes'] if c['name'] is not None]
                }
                
        except Exception as e:
            logger.error(f"Error getting repository data: {e}")
            return {}
    
    async def _generate_changelog_from_codebase(self, repo_data: Dict[str, Any], target_audience: str, changelog_format: str) -> str:
        """Generate changelog content based on codebase structure"""
        try:
            files = repo_data.get('files', [])
            functions = repo_data.get('functions', [])
            classes = repo_data.get('classes', [])
            
            # Group files by language
            files_by_language = {}
            for file in files:
                lang = file.get('language', 'unknown')
                if lang not in files_by_language:
                    files_by_language[lang] = []
                files_by_language[lang].append(file)
            
            # Generate changelog content using AI
            prompt = f"""
            Generate a changelog for a software project with the following structure:
            
            Files by language:
            {json.dumps(files_by_language, indent=2)}
            
            Functions: {len(functions)} total
            Classes: {len(classes)} total
            
            Target audience: {target_audience}
            Format: {changelog_format}
            
            Create a changelog that highlights:
            - Key features based on the codebase structure
            - Important modules and their purposes
            - Technical improvements and architecture
            
            Make it appropriate for the {target_audience} audience.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a technical writer specializing in software changelogs. Create concise, informative changelogs based on codebase analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error generating changelog content: {e}")
            return self._generate_fallback_changelog(repo_data, target_audience)
    
    def _generate_fallback_changelog(self, repo_data: Dict[str, Any], target_audience: str) -> str:
        """Generate a simple fallback changelog when AI generation fails"""
        files = repo_data.get('files', [])
        functions = repo_data.get('functions', [])
        classes = repo_data.get('classes', [])
        
        # Group files by language
        files_by_language = {}
        for file in files:
            lang = file.get('language', 'unknown')
            if lang not in files_by_language:
                files_by_language[lang] = 0
            files_by_language[lang] += 1
        
        changelog = f"""# Repository Analysis Summary

## Overview
This changelog is generated based on the current codebase structure and analysis.

## Codebase Statistics
- **Total Files**: {len(files)}
- **Functions**: {len(functions)}
- **Classes**: {len(classes)}

## Languages
"""
        
        for lang, count in files_by_language.items():
            changelog += f"- **{lang.title()}**: {count} files\n"
        
        changelog += """
## Key Features
- Comprehensive codebase with multiple programming languages
- Well-structured architecture with separated concerns
- Rich functionality across different modules

## Technical Details
- Modern software architecture patterns
- Comprehensive code organization
- Scalable design patterns
"""
        
        return changelog
    
    def _generate_version_from_history(self, repo_owner: str, repo_name: str) -> str:
        """Generate a version number based on existing changelog history"""
        try:
            history = self.get_changelog_history(repo_owner, repo_name)
            
            if not history:
                return "v1.0.0"
            
            # Find the latest version and increment
            latest_version = "v0.0.0"
            for entry in history:
                version = entry.get('version', 'v0.0.0')
                if version > latest_version:
                    latest_version = version
            
            # Simple version increment (patch version)
            if latest_version.startswith('v'):
                parts = latest_version[1:].split('.')
                if len(parts) >= 3:
                    patch = int(parts[2]) + 1
                    return f"v{parts[0]}.{parts[1]}.{patch}"
            
            return "v1.0.1"
            
        except Exception as e:
            logger.error(f"Error generating version from history: {e}")
            return "v1.0.0"