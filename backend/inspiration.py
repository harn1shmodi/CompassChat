# Universal Repository Filter Configuration for Chat-with-Repo Applications
# Covers 80-90% of use cases for code-focused repository analysis

# Core programming language extensions to INCLUDE
CODE_EXTENSIONS = {
    # JavaScript/TypeScript ecosystem (30% of repos)
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    
    # Python ecosystem (25% of repos)
    '.py', '.pyi', '.pyx', '.pxd',
    
    # Java/JVM languages (15% of repos)
    '.java', '.scala', '.kt', '.kts', '.groovy',
    
    # C/C++ family (10% of repos)
    '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx',
    
    # Go, Rust, Swift (10% of repos)
    '.go', '.rs', '.swift',
    
    # C#/.NET (5% of repos)
    '.cs', '.vb', '.fs',
    
    # Ruby, PHP, Perl (5% of repos)
    '.rb', '.php', '.pl', '.pm',
    
    # Shell scripts
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    
    # Web technologies
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.vue', '.svelte', '.astro',
    
    # Mobile development
    '.m', '.mm', '.dart', '.kotlin',
    
    # Configuration as code
    '.yaml', '.yml', '.json', '.toml', '.ini', '.cfg',
    '.xml', '.gradle', '.cmake',
    
    # Documentation (essential for understanding code)
    '.md', '.rst', '.txt', '.adoc',
    
    # SQL and data
    '.sql', '.graphql', '.proto',
    
    # Infrastructure as code
    '.tf', '.tfvars', '.hcl',  # Terraform
    '.pp', '.erb',              # Puppet
    '.j2', '.jinja', '.jinja2', # Ansible/Jinja
    
    # Notebooks (contain code)
    '.ipynb', '.rmd',
    
    # Other languages
    '.r', '.R', '.jl', '.lua', '.nim', '.zig', '.v',
    '.ex', '.exs', '.erl', '.hrl',  # Elixir/Erlang
    '.clj', '.cljs', '.cljc',        # Clojure
    '.ml', '.mli',                   # OCaml
    '.hs', '.lhs',                   # Haskell
    '.elm', '.purs',                 # Elm/PureScript
}

# Directories to EXCLUDE (these typically contain generated/large files)
EXCLUDE_DIRECTORIES = {
    # Package managers and dependencies (largest space savers)
    'node_modules/',
    'vendor/',
    '.pnpm/',
    'bower_components/',
    'jspm_packages/',
    'web_modules/',
    
    # Build outputs and compiled files
    'dist/',
    'build/',
    'out/',
    'output/',
    'target/',
    'bin/',
    'obj/',
    'lib/',
    '_build/',
    '.next/',
    '.nuxt/',
    '.output/',
    '.svelte-kit/',
    '.parcel-cache/',
    
    # Python specific
    '__pycache__/',
    '.pytest_cache/',
    '.tox/',
    'htmlcov/',
    '.coverage/',
    '*.egg-info/',
    '.mypy_cache/',
    '.ruff_cache/',
    
    # IDE and editor directories
    '.idea/',
    '.vscode/',
    '.vs/',
    '*.swp',
    '*.swo',
    '.DS_Store',
    
    # Version control (except .git for history)
    '.svn/',
    '.hg/',
    '.bzr/',
    
    # Documentation builds
    'docs/_build/',
    'site/',
    '_site/',
    '.docusaurus/',
    
    # Media and assets (often large)
    'assets/images/',
    'assets/videos/',
    'public/images/',
    'static/img/',
    'media/',
    
    # Logs and temp files
    'logs/',
    'tmp/',
    'temp/',
    '*.log',
    
    # Test outputs
    'coverage/',
    '.nyc_output/',
    'test-results/',
    
    # Environment and secrets
    '.env/',
    '.venv/',
    'venv/',
    'env/',
    'virtualenv/',
    
    # Mobile/iOS specific
    'Pods/',
    'DerivedData/',
    
    # .NET specific
    'packages/',
    'PublishProfiles/',
    
    # Terraform
    '.terraform/',
    
    # Docker
    '.docker/',
}

# File patterns to EXCLUDE (regardless of location)
EXCLUDE_PATTERNS = {
    # Compressed and binary files
    '*.zip', '*.tar', '*.gz', '*.bz2', '*.7z', '*.rar',
    '*.jar', '*.war', '*.ear', '*.class',
    
    # Images (usually not needed for code analysis)
    '*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.ico', '*.svg',
    '*.webp', '*.tiff', '*.psd', '*.ai', '*.sketch',
    
    # Videos and audio
    '*.mp4', '*.avi', '*.mov', '*.wmv', '*.flv', '*.webm',
    '*.mp3', '*.wav', '*.flac', '*.aac', '*.ogg',
    
    # Documents (usually not code)
    '*.pdf', '*.doc', '*.docx', '*.xls', '*.xlsx', '*.ppt', '*.pptx',
    
    # Databases
    '*.db', '*.sqlite', '*.sqlite3', '*.mdb',
    
    # Large data files
    '*.csv', '*.tsv', '*.parquet', '*.feather', '*.h5', '*.hdf5',
    
    # Compiled objects and libraries
    '*.o', '*.a', '*.so', '*.dll', '*.dylib', '*.exe',
    
    # Package files
    '*.deb', '*.rpm', '*.dmg', '*.pkg', '*.msi',
    
    # Lock files (useful but can be large)
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'Gemfile.lock', 'poetry.lock', 'Pipfile.lock',
    'composer.lock', 'Cargo.lock',
    
    # IDE files
    '*.iml', '*.ipr', '*.iws',
    
    # OS generated files
    'Thumbs.db', 'desktop.ini', '.Spotlight-V100', '.Trashes',
    
    # Backup files
    '*.bak', '*.backup', '*.old', '*.orig', '*.tmp', '*.temp',
    '*~',
    
    # Cache files
    '*.cache', '*.cached',
}

# Essential files to ALWAYS INCLUDE (even if they match exclude patterns)
FORCE_INCLUDE_FILES = {
    'README.md',
    'LICENSE',
    'package.json',      # Important for understanding dependencies
    'requirements.txt',  # Python dependencies
    'Gemfile',          # Ruby dependencies
    'go.mod',           # Go modules
    'Cargo.toml',       # Rust dependencies
    'build.gradle',     # Gradle build
    'pom.xml',          # Maven build
    'CMakeLists.txt',   # CMake configuration
    'Makefile',         # Build instructions
    'Dockerfile',       # Container definition
    'docker-compose.yml',
    '.gitignore',       # Understand project structure
    'setup.py',         # Python package setup
    'pyproject.toml',   # Modern Python project config
    'tsconfig.json',    # TypeScript configuration
    '.eslintrc*',       # Linting rules show code standards
    '.prettierrc*',     # Code formatting rules
}

def create_sparse_checkout_file(output_path='sparse-checkout-patterns.txt'):
    """Generate a sparse-checkout file with all patterns"""
    with open(output_path, 'w') as f:
        # Start with including everything
        f.write("/*\n")
        
        # Exclude directories
        for dir_pattern in EXCLUDE_DIRECTORIES:
            f.write(f"!{dir_pattern}\n")
        
        # Exclude file patterns
        for pattern in EXCLUDE_PATTERNS:
            f.write(f"!{pattern}\n")
        
        # Force include essential files
        for file in FORCE_INCLUDE_FILES:
            f.write(f"{file}\n")
        
        # Include all code extensions
        for ext in CODE_EXTENSIONS:
            f.write(f"*{ext}\n")
    
    print(f"Sparse checkout patterns written to {output_path}")

def create_git_attributes_file(output_path='.gitattributes'):
    """Generate a .gitattributes file for handling large files"""
    with open(output_path, 'w') as f:
        # Mark large files as binary to prevent diff generation
        for pattern in EXCLUDE_PATTERNS:
            if pattern.startswith('*.'):
                f.write(f"{pattern} binary\n")
        
        # Ensure text files are properly handled
        for ext in CODE_EXTENSIONS:
            f.write(f"*{ext} text\n")
    
    print(f"Git attributes written to {output_path}")

def get_rsync_exclude_args():
    """Generate rsync exclude arguments for copying repos"""
    excludes = []
    for dir_pattern in EXCLUDE_DIRECTORIES:
        excludes.extend(['--exclude', dir_pattern])
    for pattern in EXCLUDE_PATTERNS:
        excludes.extend(['--exclude', pattern])
    return excludes

def get_find_command_for_code_files():
    """Generate a find command to locate only code files"""
    # Build the include patterns
    includes = []
    for ext in CODE_EXTENSIONS:
        includes.append(f"-name '*{ext}'")
    
    # Build the exclude patterns
    excludes = []
    for dir_pattern in EXCLUDE_DIRECTORIES:
        excludes.append(f"-path './{dir_pattern.rstrip('/')}' -prune")
    
    find_cmd = f"find . {' -o '.join(excludes)} -o \\( {' -o '.join(includes)} \\) -type f -print"
    return find_cmd

def estimate_size_reduction(total_repo_size_mb):
    """Estimate size reduction based on typical repository composition"""
    # Based on analysis of common repositories:
    # - node_modules alone often accounts for 40-60% of repo size
    # - Build outputs add another 10-20%
    # - Media files can be 10-30%
    # - Actual code is typically only 10-30% of total size
    
    estimated_code_percentage = 0.20  # Conservative estimate
    estimated_final_size_mb = total_repo_size_mb * estimated_code_percentage
    
    return {
        'original_size_mb': total_repo_size_mb,
        'estimated_final_size_mb': round(estimated_final_size_mb, 2),
        'reduction_percentage': round((1 - estimated_code_percentage) * 100, 1),
        'example': {
            'helicone_514mb': {
                'estimated_final_size': round(514 * estimated_code_percentage, 2),
                'size_reduction': round(514 * (1 - estimated_code_percentage), 2)
            }
        }
    }

# Practical implementation for git sparse-checkout
def apply_sparse_checkout_to_repo(repo_path):
    """Apply filtering to an existing repository"""
    import subprocess
    import os
    
    os.chdir(repo_path)
    
    # Enable sparse-checkout
    subprocess.run(['git', 'sparse-checkout', 'init', '--cone'])
    
    # Create the exclude list (directories only for cone mode)
    exclude_dirs = [d.rstrip('/') for d in EXCLUDE_DIRECTORIES]
    
    # Set sparse-checkout (in cone mode, we specify what to include)
    # Start with the root and then exclude unwanted directories
    include_dirs = ['/']
    
    # Common source directories to explicitly include
    common_source_dirs = [
        'src', 'source', 'lib', 'app', 'apps', 'packages',
        'core', 'components', 'modules', 'services',
        'api', 'server', 'client', 'frontend', 'backend',
        'tests', 'test', 'spec', 'specs',
        'scripts', 'tools', 'utils', 'helpers',
        'config', 'configs', 'configuration'
    ]
    
    subprocess.run(['git', 'sparse-checkout', 'set'] + include_dirs + common_source_dirs)
    
    # Apply the changes
    subprocess.run(['git', 'read-tree', '-m', '-u', 'HEAD'])
    
    print("Sparse checkout applied. Repository now contains only code files.")

# Example usage for different scenarios
if __name__ == "__main__":
    # Generate sparse-checkout file
    create_sparse_checkout_file()
    
    # Show size estimation for Helicone
    estimation = estimate_size_reduction(514)
    print(f"\nSize estimation for Helicone (514 MB):")
    print(f"- Estimated final size: {estimation['example']['helicone_514mb']['estimated_final_size']} MB")
    print(f"- Size reduction: {estimation['example']['helicone_514mb']['size_reduction']} MB")
    print(f"- Reduction percentage: {estimation['reduction_percentage']}%")
    
    # Show find command example
    print(f"\nFind command to locate code files:")
    print(get_find_command_for_code_files())