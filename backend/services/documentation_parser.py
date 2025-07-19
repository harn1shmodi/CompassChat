import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DocumentationParser:
    """Parser for documentation and configuration files"""
    
    def __init__(self):
        self.supported_files = {
            'README.md': self.parse_readme,
            'readme.md': self.parse_readme,
            'package.json': self.parse_package_json,
            'requirements.txt': self.parse_requirements_txt,
            'Dockerfile': self.parse_dockerfile,
            'docker-compose.yml': self.parse_docker_compose,
            'docker-compose.yaml': self.parse_docker_compose,
            'pyproject.toml': self.parse_pyproject_toml,
            'Cargo.toml': self.parse_cargo_toml,
            'go.mod': self.parse_go_mod,
            'composer.json': self.parse_composer_json,
            'pom.xml': self.parse_pom_xml,
            'build.gradle': self.parse_build_gradle
        }
    
    def parse_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Parse a documentation/configuration file and extract key information"""
        file_name = Path(file_path).name
        
        if file_name in self.supported_files:
            try:
                return self.supported_files[file_name](content)
            except Exception as e:
                logger.warning(f"Error parsing {file_name}: {e}")
                return self.create_basic_chunk(file_path, content)
        
        # Generic handler for other documentation files
        return self.create_basic_chunk(file_path, content)
    
    def parse_readme(self, content: str) -> Dict[str, Any]:
        """Parse README.md to extract project description and key information"""
        lines = content.split('\n')
        
        # Extract title (usually first # heading)
        title = ""
        for line in lines:
            if line.startswith('# '):
                title = line[2:].strip()
                break
        
        # Extract description (first paragraph after title)
        description = ""
        in_description = False
        description_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                continue
            elif line and not line.startswith('#') and not line.startswith('```'):
                if not in_description and line:
                    in_description = True
                if in_description:
                    description_lines.append(line)
                    if len(description_lines) >= 3 or len(' '.join(description_lines)) > 200:
                        break
        
        description = ' '.join(description_lines).strip()
        
        # Extract features section
        features = []
        in_features = False
        for line in lines:
            line = line.strip()
            if re.match(r'^#{1,3}\s*features', line.lower()):
                in_features = True
                continue
            elif re.match(r'^#{1,3}\s', line) and in_features:
                in_features = False
                continue
            elif in_features and line.startswith('- '):
                features.append(line[2:].strip())
        
        # Extract installation section
        installation = []
        in_installation = False
        for line in lines:
            line = line.strip()
            if re.match(r'^#{1,3}\s*installation', line.lower()):
                in_installation = True
                continue
            elif re.match(r'^#{1,3}\s', line) and in_installation:
                in_installation = False
                continue
            elif in_installation and line:
                installation.append(line)
        
        return {
            'type': 'documentation',
            'file_type': 'readme',
            'title': title,
            'description': description,
            'features': features,
            'installation': '\n'.join(installation),
            'content': content,
            'summary': f"Project: {title}\nDescription: {description[:200]}..."
        }
    
    def parse_package_json(self, content: str) -> Dict[str, Any]:
        """Parse package.json to extract project metadata"""
        try:
            data = json.loads(content)
            
            return {
                'type': 'configuration',
                'file_type': 'package_json',
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'version': data.get('version', ''),
                'main': data.get('main', ''),
                'scripts': list(data.get('scripts', {}).keys()),
                'dependencies': list(data.get('dependencies', {}).keys()),
                'dev_dependencies': list(data.get('devDependencies', {}).keys()),
                'keywords': data.get('keywords', []),
                'content': content,
                'summary': f"Node.js project: {data.get('name', '')}\n{data.get('description', '')}"
            }
        except json.JSONDecodeError:
            return self.create_basic_chunk('package.json', content)
    
    def parse_requirements_txt(self, content: str) -> Dict[str, Any]:
        """Parse requirements.txt to extract Python dependencies"""
        dependencies = []
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract package name without version
                package = re.split(r'[>=<~]', line)[0].strip()
                dependencies.append(package)
        
        return {
            'type': 'configuration',
            'file_type': 'requirements_txt',
            'dependencies': dependencies,
            'content': content,
            'summary': f"Python project with {len(dependencies)} dependencies"
        }
    
    def parse_dockerfile(self, content: str) -> Dict[str, Any]:
        """Parse Dockerfile to extract base image and runtime"""
        base_image = "unknown"
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('FROM '):
                base_image = line[5:].strip()
                break
        
        return {
            'type': 'configuration',
            'file_type': 'dockerfile',
            'base_image': base_image,
            'content': content,
            'summary': f"Dockerized application using {base_image}"
        }
    
    def parse_docker_compose(self, content: str) -> Dict[str, Any]:
        """Parse docker-compose.yml to extract services"""
        try:
            import yaml
            data = yaml.safe_load(content)
            services = list(data.get('services', {}).keys()) if data else []
            
            return {
                'type': 'configuration',
                'file_type': 'docker_compose',
                'services': services,
                'content': content,
                'summary': f"Docker Compose project with {len(services)} services"
            }
        except ImportError:
            return self.create_basic_chunk('docker-compose.yml', content)
    
    def parse_pyproject_toml(self, content: str) -> Dict[str, Any]:
        """Parse pyproject.toml for Python project metadata"""
        try:
            import toml
            data = toml.loads(content)
            project = data.get('project', {})
            
            return {
                'type': 'configuration',
                'file_type': 'pyproject_toml',
                'name': project.get('name', ''),
                'description': project.get('description', ''),
                'dependencies': list(project.get('dependencies', [])),
                'content': content,
                'summary': f"Python project: {project.get('name', '')}"
            }
        except ImportError:
            return self.create_basic_chunk('pyproject.toml', content)
    
    def parse_cargo_toml(self, content: str) -> Dict[str, Any]:
        """Parse Cargo.toml for Rust project metadata"""
        try:
            import toml
            data = toml.loads(content)
            package = data.get('package', {})
            
            return {
                'type': 'configuration',
                'file_type': 'cargo_toml',
                'name': package.get('name', ''),
                'description': package.get('description', ''),
                'version': package.get('version', ''),
                'dependencies': list(data.get('dependencies', {}).keys()),
                'content': content,
                'summary': f"Rust project: {package.get('name', '')}"
            }
        except ImportError:
            return self.create_basic_chunk('Cargo.toml', content)
    
    def parse_go_mod(self, content: str) -> Dict[str, Any]:
        """Parse go.mod for Go project metadata"""
        module_name = "unknown"
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('module '):
                module_name = line[7:].strip()
                break
        
        return {
            'type': 'configuration',
            'file_type': 'go_mod',
            'module': module_name,
            'content': content,
            'summary': f"Go module: {module_name}"
        }
    
    def parse_composer_json(self, content: str) -> Dict[str, Any]:
        """Parse composer.json for PHP project metadata"""
        try:
            data = json.loads(content)
            
            return {
                'type': 'configuration',
                'file_type': 'composer_json',
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'dependencies': list(data.get('require', {}).keys()),
                'content': content,
                'summary': f"PHP project: {data.get('name', '')}"
            }
        except json.JSONDecodeError:
            return self.create_basic_chunk('composer.json', content)
    
    def parse_pom_xml(self, content: str) -> Dict[str, Any]:
        """Parse pom.xml for Java/Maven project metadata"""
        # Simple regex-based parsing for Maven POM
        name_match = re.search(r'<name>([^<]+)</name>', content)
        description_match = re.search(r'<description>([^<]+)</description>', content)
        
        name = name_match.group(1) if name_match else "unknown"
        description = description_match.group(1) if description_match else ""
        
        return {
            'type': 'configuration',
            'file_type': 'pom_xml',
            'name': name,
            'description': description,
            'content': content,
            'summary': f"Java/Maven project: {name}"
        }
    
    def parse_build_gradle(self, content: str) -> Dict[str, Any]:
        """Parse build.gradle for Gradle project metadata"""
        # Simple regex-based parsing for Gradle
        name_match = re.search(r"group\s*=\s*['\"]([^'\"]+)['\"]", content)
        description_match = re.search(r"description\s*=\s*['\"]([^'\"]+)['\"]", content)
        
        name = name_match.group(1) if name_match else "unknown"
        description = description_match.group(1) if description_match else ""
        
        return {
            'type': 'configuration',
            'file_type': 'build_gradle',
            'group': name,
            'description': description,
            'content': content,
            'summary': f"Gradle project: {name}"
        }
    
    def create_basic_chunk(self, file_path: str, content: str) -> Dict[str, Any]:
        """Create a basic chunk for unsupported documentation files"""
        file_name = Path(file_path).name
        return {
            'type': 'documentation',
            'file_type': file_name.lower().replace('.', '_'),
            'content': content,
            'summary': f"Configuration/documentation file: {file_name}"
        }
    
    def should_parse_file(self, file_path: str) -> bool:
        """Check if this file should be parsed by the documentation parser"""
        file_name = Path(file_path).name
        extension = Path(file_path).suffix.lower()
        
        return (
            file_name in self.supported_files or
            extension in ['.md', '.json', '.txt', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf'] or
            file_name.startswith('Dockerfile')
        )