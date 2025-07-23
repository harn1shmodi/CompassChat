#!/bin/bash

# Ready-to-Use Git Repository Filtering for Chat-with-Repo Apps
# This script implements the 80-90% use case filtering patterns

# OPTION 1: Ultra-fast partial clone with filtering (Recommended)
clone_for_code_analysis() {
    local repo_url=$1
    local target_dir=${2:-"repo"}
    
    echo "🚀 Performing optimized clone for code analysis..."
    
    # Step 1: Blobless clone (only downloads commit history, not file contents)
    git clone --filter=blob:none --no-checkout "$repo_url" "$target_dir"
    cd "$target_dir"
    
    # Step 2: Initialize sparse-checkout in cone mode for performance
    git sparse-checkout init --cone --sparse-index
    
    # Step 3: Set directories to include (common source code locations)
    git sparse-checkout set \
        src \
        source \
        lib \
        app \
        apps \
        packages \
        core \
        components \
        modules \
        services \
        api \
        server \
        client \
        frontend \
        backend \
        cmd \
        internal \
        pkg \
        tests \
        test \
        spec \
        __tests__ \
        scripts \
        tools \
        utils \
        helpers \
        config \
        .github
    
    # Step 4: Checkout the files
    git checkout main || git checkout master
    
    echo "✅ Clone complete! Repository filtered to code-only content."
}

# OPTION 2: Create .gitignore style exclude file for various tools
create_exclude_file() {
    cat > .repo-exclude << 'EOF'
# Dependencies and package managers (biggest space savers)
node_modules/
vendor/
.pnpm/
bower_components/
jspm_packages/
Pods/
packages/
.yarn/

# Build outputs
dist/
build/
out/
output/
target/
bin/
obj/
*.exe
*.dll
*.so
*.dylib
_build/
.next/
.nuxt/
.output/
.svelte-kit/

# IDE and editors
.idea/
.vscode/
.vs/
*.swp
.DS_Store

# Python
__pycache__/
*.pyc
.pytest_cache/
.tox/
venv/
.venv/
env/
*.egg-info/

# Media files
*.jpg
*.jpeg
*.png
*.gif
*.mp4
*.mov
*.avi
*.mp3
*.wav
*.pdf
*.zip
*.tar.gz
*.rar

# Large data files  
*.csv
*.sqlite
*.db
*.h5

# Logs and temp
*.log
logs/
tmp/
temp/
*.tmp

# Lock files (optional - include if you need dependency info)
# package-lock.json
# yarn.lock
# Gemfile.lock
# poetry.lock
# Cargo.lock
EOF
    echo "✅ Created .repo-exclude file"
}

# OPTION 3: Git filter-repo command for existing repos (most thorough)
filter_existing_repo() {
    local repo_path=${1:-.}
    
    echo "🔧 Filtering existing repository to code-only content..."
    echo "⚠️  This will rewrite history - make sure you have a backup!"
    
    # Install git-filter-repo if not available
    if ! command -v git-filter-repo &> /dev/null; then
        echo "Installing git-filter-repo..."
        pip install git-filter-repo
    fi
    
    cd "$repo_path"
    
    # Remove all non-code files and large files
    git filter-repo \
        --path-glob '*.py' \
        --path-glob '*.js' \
        --path-glob '*.jsx' \
        --path-glob '*.ts' \
        --path-glob '*.tsx' \
        --path-glob '*.java' \
        --path-glob '*.cpp' \
        --path-glob '*.c' \
        --path-glob '*.h' \
        --path-glob '*.go' \
        --path-glob '*.rs' \
        --path-glob '*.rb' \
        --path-glob '*.php' \
        --path-glob '*.cs' \
        --path-glob '*.swift' \
        --path-glob '*.kt' \
        --path-glob '*.scala' \
        --path-glob '*.r' \
        --path-glob '*.R' \
        --path-glob '*.sh' \
        --path-glob '*.bash' \
        --path-glob '*.yml' \
        --path-glob '*.yaml' \
        --path-glob '*.json' \
        --path-glob '*.xml' \
        --path-glob '*.md' \
        --path-glob '*.txt' \
        --path-glob '*.sql' \
        --path-glob '*.graphql' \
        --path-glob 'Dockerfile*' \
        --path-glob 'Makefile' \
        --path-glob '.gitignore' \
        --path src/ \
        --path lib/ \
        --path app/ \
        --path packages/ \
        --path-glob '!node_modules/' \
        --path-glob '!vendor/' \
        --path-glob '!*.jpg' \
        --path-glob '!*.png' \
        --path-glob '!*.gif' \
        --path-glob '!*.mp4' \
        --path-glob '!*.zip' \
        --path-glob '!*.pdf' \
        --strip-blobs-bigger-than 10M
}

# OPTION 4: Simple directory-based sparse checkout (fastest setup)
quick_sparse_checkout() {
    local repo_url=$1
    
    git clone --no-checkout "$repo_url" repo-sparse
    cd repo-sparse
    
    # Enable sparse checkout
    git sparse-checkout init
    
    # Quick patterns that cover most code
    cat > .git/info/sparse-checkout << 'EOF'
/*
!/node_modules/
!/vendor/
!/build/
!/dist/
!/target/
!/__pycache__/
!/.idea/
!/.vscode/
!/venv/
!*.jpg
!*.png
!*.mp4
!*.pdf
!*.zip
EOF
    
    git checkout main || git checkout master
}

# OPTION 5: Memory-safe configuration for Digital Ocean
configure_git_for_digital_ocean() {
    echo "⚙️  Configuring Git for memory-constrained environments..."
    
    # Limit memory usage
    git config --global pack.windowMemory "100m"
    git config --global pack.packSizeLimit "100m"
    git config --global pack.threads "1"
    git config --global pack.deltaCacheSize "25m"
    git config --global core.packedGitWindowSize "32m"
    git config --global core.packedGitLimit "128m"
    git config --global core.bigFileThreshold "50m"
    git config --global http.postBuffer "524288000"  # 500MB
    
    # Performance optimizations
    git config --global core.preloadIndex true
    git config --global core.fscache true
    git config --global gc.auto 256
    
    echo "✅ Git configured for memory efficiency"
}

# OPTION 6: Python implementation for programmatic filtering
create_python_filter() {
    cat > repo_filter.py << 'EOF'
import os
import shutil
import subprocess
from pathlib import Path
from typing import Set, List

class RepoFilter:
    def __init__(self):
        # File extensions to keep (covers 90% of code)
        self.keep_extensions = {
            # Web
            '.js', '.jsx', '.ts', '.tsx', '.vue', '.svelte',
            # Backend
            '.py', '.java', '.go', '.rs', '.rb', '.php', '.cs',
            # Systems
            '.c', '.cpp', '.h', '.hpp', '.swift', '.kt',
            # Config
            '.json', '.yaml', '.yml', '.toml', '.xml',
            # Docs
            '.md', '.rst', '.txt',
            # Scripts
            '.sh', '.bash', '.ps1', '.bat',
            # Other
            '.sql', '.graphql', '.proto', '.dockerfile'
        }
        
        # Directories to exclude
        self.exclude_dirs = {
            'node_modules', 'vendor', 'build', 'dist', 'target',
            '__pycache__', '.git', '.idea', '.vscode', 'venv',
            'coverage', 'tmp', 'temp', 'logs', 'assets/images'
        }
    
    def should_include_file(self, file_path: Path) -> bool:
        # Check if in excluded directory
        for part in file_path.parts:
            if part in self.exclude_dirs:
                return False
        
        # Check extension
        return file_path.suffix.lower() in self.keep_extensions
    
    def filter_directory(self, source_dir: str, target_dir: str):
        source = Path(source_dir)
        target = Path(target_dir)
        
        for file_path in source.rglob('*'):
            if file_path.is_file() and self.should_include_file(file_path):
                relative_path = file_path.relative_to(source)
                target_path = target / relative_path
                
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_path)
    
    def clone_and_filter(self, repo_url: str, target_dir: str = 'filtered_repo'):
        # Clone with minimal data
        subprocess.run([
            'git', 'clone', '--depth=1', '--single-branch',
            '--filter=blob:none', repo_url, 'temp_repo'
        ])
        
        # Filter files
        self.filter_directory('temp_repo', target_dir)
        
        # Cleanup
        shutil.rmtree('temp_repo')
        
        print(f"✅ Filtered repository saved to {target_dir}")

# Usage
if __name__ == "__main__":
    filter = RepoFilter()
    filter.clone_and_filter("https://github.com/example/repo.git")
EOF
    echo "✅ Created repo_filter.py"
}

# Main menu
echo "🔧 Git Repository Code-Only Filter Tool"
echo "Choose an option:"
echo "1) Fast partial clone with filtering (recommended)"
echo "2) Create exclude file for tools"
echo "3) Filter existing repository (rewrites history)"
echo "4) Quick sparse checkout"
echo "5) Configure Git for Digital Ocean"
echo "6) Create Python filter script"
echo "7) Run all optimizations"

read -p "Enter choice (1-7): " choice

case $choice in
    1)
        read -p "Enter repository URL: " repo_url
        clone_for_code_analysis "$repo_url"
        ;;
    2)
        create_exclude_file
        ;;
    3)
        filter_existing_repo
        ;;
    4)
        read -p "Enter repository URL: " repo_url
        quick_sparse_checkout "$repo_url"
        ;;
    5)
        configure_git_for_digital_ocean
        ;;
    6)
        create_python_filter
        ;;
    7)
        echo "Running all optimizations..."
        configure_git_for_digital_ocean
        create_exclude_file
        create_python_filter
        echo "✅ All configurations created!"
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac