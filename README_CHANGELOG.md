# CompassChat AI-Powered Changelog Generator

An intelligent changelog generation system that leverages GraphRAG and Large Language Models to automatically create user-friendly changelogs from Git commits.

## Overview

The CompassChat Changelog Generator is a comprehensive solution that analyzes Git repositories and generates intelligent changelogs tailored to different audiences. It combines the power of GraphRAG for code understanding with GPT-4 for natural language generation.

## Features

### 🚀 Core Features

- **AI-Powered Analysis**: Uses GraphRAG to understand code changes and their impact
- **Multi-Audience Support**: Generates changelogs for users, developers, business stakeholders, or mixed audiences
- **Intelligent Commit Analysis**: Categorizes commits by type (features, fixes, breaking changes)
- **Breaking Change Detection**: Automatically identifies and highlights breaking changes
- **Multiple Output Formats**: Supports Markdown and JSON formats
- **Version Management**: Automatically generates semantic version numbers
- **Contributor Recognition**: Tracks and acknowledges contributors

### 🛠️ Technical Features

- **GraphRAG Integration**: Leverages existing code analysis infrastructure
- **Neo4j Storage**: Stores changelog history in graph database
- **RESTful API**: Complete API for changelog management
- **Real-time Generation**: Fast changelog generation with progress tracking
- **CLI Tool**: Command-line interface for developer workflow integration

## Architecture

### Backend Components

1. **Git Analysis Service** (`services/git_analysis.py`)
   - Analyzes Git commits and repository structure
   - Extracts commit metadata, file changes, and relationships
   - Categorizes commits by type and impact

2. **Changelog Service** (`services/changelog_service.py`)
   - Core service for AI-powered changelog generation
   - Integrates with GraphRAG for code context understanding
   - Manages changelog storage and retrieval

3. **API Endpoints** (`api/changelog.py`)
   - RESTful endpoints for changelog operations
   - Public changelog viewing
   - Template management

4. **Neo4j Schema Extensions** (`core/neo4j_conn.py`)
   - Changelog storage in graph database
   - Indexes for fast retrieval and search

### Frontend Components

1. **Changelog Generator** (`components/ChangelogGenerator.tsx`)
   - Interactive UI for changelog configuration
   - Real-time preview functionality
   - Export and download capabilities

2. **Changelog History** (`components/ChangelogHistory.tsx`)
   - View and manage changelog history
   - Public changelog access
   - Search and filtering

### CLI Tool

- **Command-line Interface** (`cli/changelog_cli.py`)
- Direct integration with developer workflows
- Batch processing capabilities
- Multiple output options

## API Reference

### Generate Changelog

```http
POST /api/changelog/generate
Content-Type: application/json

{
  "repo_owner": "owner",
  "repo_name": "repository",
  "since_version": "v1.0.0",
  "target_audience": "users",
  "changelog_format": "markdown"
}
```

### Get Changelog History

```http
GET /api/changelog/history/{owner}/{repo}
```

### Public Changelog

```http
GET /api/changelog/public/{owner}/{repo}?format=html
```

## CLI Usage

### Basic Usage

```bash
# Generate changelog for current directory
python cli/changelog_cli.py .

# Generate changelog since specific version
python cli/changelog_cli.py /path/to/repo --since-version v1.0.0

# Generate changelog for developers
python cli/changelog_cli.py . --audience developers --format json

# Save to file
python cli/changelog_cli.py . --output CHANGELOG.md
```

### Advanced Options

```bash
# Generate changelog since date
python cli/changelog_cli.py . --since-date 2024-01-01

# Dry run (show what would be generated)
python cli/changelog_cli.py . --dry-run

# Verbose output
python cli/changelog_cli.py . --verbose
```

## Installation and Setup

### Prerequisites

- Python 3.8+
- Neo4j Database
- OpenAI API Key
- Node.js 16+ (for frontend)

### Backend Setup

1. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. Configure environment variables:
```bash
# .env file
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
OPENAI_API_KEY=your_openai_key
```

3. Start the backend:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Configure API URL:
```bash
# .env file
VITE_API_URL=http://localhost:8000
```

3. Start the frontend:
```bash
npm run dev
```

### Database Setup

The Neo4j schema is automatically created when the backend starts. The changelog extension adds:

- `Changelog` nodes with version, content, and metadata
- `HAS_CHANGELOG` relationships linking repositories to changelogs
- Indexes for efficient querying and search

## Usage Examples

### Web Interface

1. Navigate to the CompassChat application
2. Analyze a repository using the repository input
3. Switch to the "Generate Changelog" tab
4. Configure your changelog settings:
   - Select target audience
   - Choose output format
   - Set version range or date range
5. Generate and download your changelog

### API Integration

```python
import requests

# Generate changelog
response = requests.post('http://localhost:8000/api/changelog/generate', json={
    'repo_owner': 'microsoft',
    'repo_name': 'vscode',
    'target_audience': 'users',
    'changelog_format': 'markdown'
})

changelog = response.json()
print(changelog['content'])
```

### CLI Integration

```bash
# Add to your CI/CD pipeline
python cli/changelog_cli.py . --since-version $(git describe --tags --abbrev=0) --output CHANGELOG.md

# Generate release notes
python cli/changelog_cli.py . --audience business --format json > release-notes.json
```

## Audience-Specific Outputs

### Users
- Focus on new features and bug fixes
- User-friendly language
- Highlight UI/UX improvements
- Explain impact in non-technical terms

### Developers
- API changes and new endpoints
- Breaking changes with migration notes
- Technical debt improvements
- Performance optimizations with metrics

### Business
- Revenue-impacting features
- Customer-requested improvements
- Market competitive advantages
- ROI and business metrics

## Configuration

### Changelog Templates

The system supports customizable templates for different audiences:

```json
{
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
    }
  }
}
```

### AI Prompts

The system uses audience-specific prompts to generate appropriate content:

- **Users**: Focus on user benefits and experience improvements
- **Developers**: Include technical details and code examples
- **Business**: Emphasize business value and competitive advantages

## Best Practices

### Commit Messages

For best results, use conventional commit messages:

```
feat(auth): add OAuth2 support
fix(api): resolve user session timeout
docs(readme): update installation instructions
breaking(api): change authentication endpoint
```

### Version Management

- Use semantic versioning (semver)
- Tag releases consistently
- Include version tags in commit messages when appropriate

### Changelog Organization

- Group related changes together
- Highlight breaking changes prominently
- Include migration notes for major changes
- Acknowledge contributors

## Troubleshooting

### Common Issues

1. **OpenAI API Rate Limits**
   - Reduce the number of commits analyzed
   - Implement exponential backoff
   - Use caching for repeated requests

2. **Neo4j Connection Issues**
   - Verify connection parameters
   - Check database is running
   - Ensure indexes are created

3. **Git Repository Access**
   - Verify repository path is correct
   - Ensure Git repository is properly initialized
   - Check file permissions

### Performance Optimization

- Limit commit analysis to relevant time periods
- Use caching for expensive operations
- Implement pagination for large repositories
- Consider async processing for bulk operations

## Contributing

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

### Code Style

- Follow PEP 8 for Python code
- Use TypeScript for frontend components
- Include docstrings for all public methods
- Add type hints where appropriate

## License

This project is part of CompassChat and follows the same licensing terms.

## Support

For issues and support:
- Check the troubleshooting section
- Review existing GitHub issues
- Create a new issue with detailed information
- Include relevant logs and error messages

---

*Generated with CompassChat AI-Powered Changelog Generator* 🤖