#!/usr/bin/env python3
"""
CompassChat Changelog Generator CLI

A command-line tool for generating AI-powered changelogs from Git repositories.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add the backend directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.changelog_service import ChangelogService
from services.git_analysis import GitAnalysisService
from core.config import settings


class ChangelogCLI:
    """Command-line interface for changelog generation"""
    
    def __init__(self):
        self.changelog_service = ChangelogService()
        self.git_service = GitAnalysisService()
    
    def parse_args(self):
        """Parse command-line arguments"""
        parser = argparse.ArgumentParser(
            description="Generate AI-powered changelogs from Git repositories",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Generate changelog for current directory (auto-detect best comparison)
  python changelog_cli.py .
  
  # Generate changelog since last tag
  python changelog_cli.py . --comparison-type since_tag --from-ref v1.0.0
  
  # Generate changelog between two tags
  python changelog_cli.py . --comparison-type tag_to_tag --from-ref v1.0.0 --to-ref v2.0.0
  
  # Generate changelog for branch comparison
  python changelog_cli.py . --comparison-type branch_to_branch --from-ref main --to-ref feature-branch
  
  # Generate changelog using direct range
  python changelog_cli.py . --comparison-range "v1.0.0..HEAD"
  
  # Generate changelog for developers
  python changelog_cli.py . --audience developers --format json
  
  # Generate changelog since specific date
  python changelog_cli.py . --since-date 2024-01-01
  
  # Save changelog to file
  python changelog_cli.py . --output changelog.md
            """
        )
        
        parser.add_argument(
            'repo_path',
            help='Path to the Git repository'
        )
        
        parser.add_argument(
            '--comparison-type',
            choices=['auto', 'since_tag', 'tag_to_tag', 'branch_to_branch', 'commit_count', 'since_date'],
            default='auto',
            help='Type of comparison to perform (default: auto)'
        )
        
        parser.add_argument(
            '--from-ref',
            help='Starting reference (tag, branch, or commit hash)'
        )
        
        parser.add_argument(
            '--to-ref',
            default='HEAD',
            help='Ending reference (tag, branch, or commit hash) (default: HEAD)'
        )
        
        parser.add_argument(
            '--comparison-range',
            help='Direct comparison range (e.g., "v1.0.0..HEAD", "main..feature-branch")'
        )
        
        parser.add_argument(
            '--since-version',
            help='Generate changelog since this version tag (e.g., v1.0.0) [deprecated: use --from-ref]'
        )
        
        parser.add_argument(
            '--since-date',
            help='Generate changelog since this date (YYYY-MM-DD)'
        )
        
        parser.add_argument(
            '--audience',
            choices=['users', 'developers', 'business', 'mixed'],
            default='users',
            help='Target audience for the changelog (default: users)'
        )
        
        parser.add_argument(
            '--format',
            choices=['markdown', 'json'],
            default='markdown',
            help='Output format (default: markdown)'
        )
        
        parser.add_argument(
            '--output', '-o',
            help='Output file path (default: print to stdout)'
        )
        
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Enable verbose output'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without actually generating'
        )
        
        return parser.parse_args()
    
    def validate_args(self, args):
        """Validate command-line arguments"""
        # Check if repo path exists and is a git repository
        repo_path = Path(args.repo_path).resolve()
        if not repo_path.exists():
            print(f"Error: Repository path '{repo_path}' does not exist", file=sys.stderr)
            sys.exit(1)
        
        if not (repo_path / '.git').exists():
            print(f"Error: '{repo_path}' is not a Git repository", file=sys.stderr)
            sys.exit(1)
        
        # Validate since_date format
        if args.since_date:
            try:
                datetime.strptime(args.since_date, '%Y-%m-%d')
            except ValueError:
                print(f"Error: Invalid date format '{args.since_date}'. Use YYYY-MM-DD", file=sys.stderr)
                sys.exit(1)
        
        # Check if OpenAI API key is configured
        if not settings.openai_api_key:
            print("Error: OpenAI API key not configured. Set OPENAI_API_KEY environment variable.", file=sys.stderr)
            sys.exit(1)
        
        return repo_path
    
    def get_repo_info(self, repo_path: Path):
        """Get repository information"""
        try:
            # Get basic repository info
            repo_info = self.git_service.analyze_repository(str(repo_path))
            
            # Extract repo name from path or remote URL
            repo_name = repo_path.name
            repo_owner = "local"
            
            # Try to get owner/name from remote URL
            if repo_info.get('repository_info', {}).get('remote_url'):
                remote_url = repo_info['repository_info']['remote_url']
                if 'github.com' in remote_url:
                    # Extract owner/name from GitHub URL
                    if remote_url.startswith('https://github.com/'):
                        parts = remote_url.replace('https://github.com/', '').replace('.git', '').split('/')
                    elif remote_url.startswith('git@github.com:'):
                        parts = remote_url.replace('git@github.com:', '').replace('.git', '').split('/')
                    else:
                        parts = []
                    
                    if len(parts) >= 2:
                        repo_owner = parts[0]
                        repo_name = parts[1]
            
            return {
                'owner': repo_owner,
                'name': repo_name,
                'full_name': f"{repo_owner}/{repo_name}",
                'path': str(repo_path),
                'info': repo_info
            }
        except Exception as e:
            print(f"Error analyzing repository: {e}", file=sys.stderr)
            sys.exit(1)
    
    async def generate_changelog(self, args, repo_info):
        """Generate changelog using the service"""
        try:
            # Parse since_date if provided
            since_date = None
            if args.since_date:
                since_date = datetime.strptime(args.since_date, '%Y-%m-%d')
            
            # Determine comparison range
            comparison_range = None
            if args.comparison_range:
                comparison_range = args.comparison_range
            elif args.comparison_type == "since_tag" and args.from_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            elif args.comparison_type == "tag_to_tag" and args.from_ref and args.to_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            elif args.comparison_type == "branch_to_branch" and args.from_ref and args.to_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            elif args.comparison_type == "commit_count" and args.from_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            
            if args.verbose:
                print(f"Generating changelog for {repo_info['full_name']}...")
                print(f"  Repository path: {repo_info['path']}")
                print(f"  Comparison type: {args.comparison_type}")
                print(f"  Comparison range: {comparison_range or 'auto-detect'}")
                print(f"  Since version: {args.since_version or 'N/A'}")
                print(f"  Since date: {args.since_date or 'N/A'}")
                print(f"  Target audience: {args.audience}")
                print(f"  Format: {args.format}")
            
            # Generate changelog
            changelog_result = await self.changelog_service.generate_changelog(
                repo_path=repo_info['path'],
                repo_name=repo_info['full_name'],
                comparison_range=comparison_range,
                since_version=args.since_version,
                since_date=since_date,
                target_audience=args.audience,
                changelog_format=args.format
            )
            
            return changelog_result
            
        except Exception as e:
            print(f"Error generating changelog: {e}", file=sys.stderr)
            sys.exit(1)
    
    def output_changelog(self, changelog_result, args):
        """Output the changelog to file or stdout"""
        if changelog_result.get('error'):
            print(f"Error: {changelog_result['error']}", file=sys.stderr)
            sys.exit(1)
        
        content = changelog_result.get('content', '')
        
        if args.output:
            # Write to file
            output_path = Path(args.output)
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content, encoding='utf-8')
                print(f"Changelog written to {output_path}")
            except Exception as e:
                print(f"Error writing to file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Print to stdout
            print(content)
        
        # Print metadata if verbose
        if args.verbose:
            metadata = changelog_result.get('metadata', {})
            print(f"\nMetadata:", file=sys.stderr)
            print(f"  Version: {changelog_result.get('version', 'N/A')}", file=sys.stderr)
            print(f"  Commits analyzed: {changelog_result.get('commits_analyzed', 0)}", file=sys.stderr)
            print(f"  Breaking changes: {len(metadata.get('breaking_changes', []))}", file=sys.stderr)
            print(f"  Contributors: {len(metadata.get('contributors', []))}", file=sys.stderr)
    
    def show_dry_run(self, args, repo_info):
        """Show what would be generated without actually generating"""
        print("Dry run mode - would generate changelog with the following parameters:")
        print(f"  Repository: {repo_info['full_name']}")
        print(f"  Path: {repo_info['path']}")
        print(f"  Comparison type: {args.comparison_type}")
        print(f"  Comparison range: {args.comparison_range or 'auto-detect'}")
        print(f"  From ref: {args.from_ref or 'N/A'}")
        print(f"  To ref: {args.to_ref}")
        print(f"  Since version: {args.since_version or 'N/A'}")
        print(f"  Since date: {args.since_date or 'N/A'}")
        print(f"  Target audience: {args.audience}")
        print(f"  Format: {args.format}")
        print(f"  Output: {args.output or 'stdout'}")
        
        # Show available comparison points
        try:
            comparison_info = self.git_service.detect_comparison_range(repo_info['path'])
            print(f"\nRepository information:")
            repo_info_data = comparison_info.get('repository_info', {})
            print(f"  Current branch: {repo_info_data.get('current_branch', 'N/A')}")
            print(f"  Main branch: {repo_info_data.get('main_branch', 'N/A')}")
            print(f"  Latest tag: {repo_info_data.get('latest_tag', 'N/A')}")
            print(f"  Previous tag: {repo_info_data.get('previous_tag', 'N/A')}")
            print(f"  Total tags: {repo_info_data.get('total_tags', 0)}")
            
            print(f"\nRecommended comparison: {comparison_info.get('recommended_range', 'N/A')}")
            
        except Exception as e:
            print(f"  Error getting repository info: {e}")
        
        # Show commits that would be analyzed
        try:
            # Determine the range to show
            if args.comparison_range:
                comparison_range = args.comparison_range
            elif args.comparison_type == "since_tag" and args.from_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            elif args.comparison_type == "tag_to_tag" and args.from_ref and args.to_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            elif args.comparison_type == "branch_to_branch" and args.from_ref and args.to_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            elif args.comparison_type == "commit_count" and args.from_ref:
                comparison_range = f"{args.from_ref}..{args.to_ref}"
            else:
                # Auto-detect
                comparison_info = self.git_service.detect_comparison_range(repo_info['path'])
                comparison_range = comparison_info.get('recommended_range', 'HEAD~10..HEAD')
            
            commits = self.git_service.get_commits_in_range(repo_info['path'], comparison_range)
            
            print(f"\nWould analyze {len(commits)} commits in range '{comparison_range}':")
            for commit in commits[:5]:  # Show first 5 commits
                print(f"  - {commit.get('short_sha', 'N/A')}: {commit.get('summary', 'N/A')}")
            
            if len(commits) > 5:
                print(f"  ... and {len(commits) - 5} more commits")
                
        except Exception as e:
            print(f"  Error getting commits: {e}")
    
    async def run(self):
        """Main entry point"""
        args = self.parse_args()
        repo_path = self.validate_args(args)
        repo_info = self.get_repo_info(repo_path)
        
        if args.dry_run:
            self.show_dry_run(args, repo_info)
            return
        
        # Generate changelog
        changelog_result = await self.generate_changelog(args, repo_info)
        
        # Output result
        self.output_changelog(changelog_result, args)


async def main():
    """Main function"""
    cli = ChangelogCLI()
    await cli.run()


if __name__ == '__main__':
    asyncio.run(main())