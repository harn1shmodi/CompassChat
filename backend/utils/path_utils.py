from pathlib import Path
import re
from typing import Dict, Any, List

def normalize_file_path(file_path: str, repo_root: str = None) -> str:
    """
    Normalize file path to a clean relative path for display
    
    Args:
        file_path: The file path to normalize
        repo_root: The repository root directory (if available)
    
    Returns:
        Clean relative path without temporary directory prefixes
    """
    if not file_path:
        return ""
    
    # Remove temporary directory patterns
    temp_patterns = [
        r'/var/folders/[^/]+/[^/]+/T/compass_chat_[^/]+/',
        r'/tmp/compass_chat_[^/]+/',
        r'C:\\Users\\[^\\]+\\AppData\\Local\\Temp\\compass_chat_[^\\]+\\',
    ]
    
    normalized = file_path
    for pattern in temp_patterns:
        normalized = re.sub(pattern, '', normalized)
    
    # Remove leading slashes/backslashes
    normalized = normalized.lstrip('/\\')
    
    # If we have a repo root, make sure path is relative to it
    if repo_root:
        try:
            path_obj = Path(file_path)
            root_obj = Path(repo_root)
            if path_obj.is_absolute() and root_obj.is_absolute():
                relative = path_obj.relative_to(root_obj)
                normalized = str(relative)
        except (ValueError, OSError):
            # If relative_to fails, keep the normalized version
            pass
    
    return normalized

def clean_search_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Clean file paths in search results for better display
    
    Args:
        results: List of search result dictionaries
    
    Returns:
        Results with cleaned file paths
    """
    cleaned_results = []
    
    for result in results:
        cleaned_result = result.copy()
        if 'file_path' in cleaned_result:
            cleaned_result['file_path'] = normalize_file_path(cleaned_result['file_path'])
        cleaned_results.append(cleaned_result)
    
    return cleaned_results

def extract_repo_name_from_path(file_path: str) -> str:
    """
    Extract likely repository name from file path
    
    Args:
        file_path: File path that may contain repo name
    
    Returns:
        Likely repository name or empty string
    """
    if not file_path:
        return ""
    
    # Look for common repo name patterns
    path_parts = file_path.split('/')
    
    # Look for GitHub-style patterns
    for i, part in enumerate(path_parts):
        if part in ['repos', 'repositories', 'projects']:
            if i + 1 < len(path_parts):
                return path_parts[i + 1]
    
    # Look for temp directory patterns with repo names
    temp_match = re.search(r'compass_chat_([^/]+)', file_path)
    if temp_match:
        return temp_match.group(1)
    
    # Default to first non-empty path component
    for part in path_parts:
        if part and part not in ['.', '..', 'tmp', 'var', 'folders']:
            return part
    
    return ""
