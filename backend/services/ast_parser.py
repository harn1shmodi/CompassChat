import tree_sitter_language_pack
from tree_sitter import Language, Parser, Node
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ASTParser:
    def __init__(self):
        self.parsers = {}
        self.language_map = {
            '.py': 'python',
            '.js': 'javascript', 
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp'
        }
        self._initialize_parsers()
    
    def _initialize_parsers(self):
        """Initialize tree-sitter parsers for supported languages"""
        for ext, lang_name in self.language_map.items():
            try:
                language = tree_sitter_language_pack.get_language(lang_name)
                parser = Parser()
                parser.language = language  # Use property assignment instead of set_language method
                self.parsers[ext] = parser
                logger.info(f"Initialized parser for {lang_name}")
            except Exception as e:
                logger.warning(f"Could not initialize parser for {lang_name}: {e}")
    
    def parse_file(self, file_path: str, repo_root: str = None) -> Optional[Dict[str, Any]]:
        """Parse a source file and extract AST information"""
        try:
            path = Path(file_path)
            extension = path.suffix.lower()
            file_name = path.name
            
            # Skip documentation files - they will be handled by documentation parser
            if extension in ['.md', '.json', '.txt', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf']:
                logger.debug(f"Skipping documentation file: {file_name}")
                return None
                
            if extension not in self.parsers:
                logger.debug(f"No parser available for {extension}")
                return None
            
            # Normalize file path to relative path from repo root
            normalized_path = str(path)
            if repo_root:
                repo_root_path = Path(repo_root).resolve()
                file_abs_path = path.resolve()
                try:
                    relative_path = file_abs_path.relative_to(repo_root_path)
                    normalized_path = str(relative_path)
                except ValueError:
                    # File is not under repo root, use original path
                    normalized_path = str(path)
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse with tree-sitter
            parser = self.parsers[extension]
            tree = parser.parse(bytes(content, 'utf8'))
            
            # Extract semantic information
            ast_info = {
                'file_path': normalized_path,  # Use normalized path
                'absolute_path': str(path),    # Keep absolute path for file operations
                'language': self.language_map[extension],
                'content': content,
                'functions': self._extract_functions(tree.root_node, content),
                'classes': self._extract_classes(tree.root_node, content),
                'imports': self._extract_imports(tree.root_node, content),
                'variables': self._extract_variables(tree.root_node, content)
            }
            
            return ast_info
            
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}")
            return None
    
    def _extract_functions(self, node: Node, content: str) -> List[Dict[str, Any]]:
        """Extract function definitions from AST"""
        functions = []
        
        def traverse(node: Node):
            if node.type in ['function_definition', 'function_declaration', 'method_definition', 'arrow_function']:
                func_info = self._extract_function_info(node, content)
                if func_info:
                    functions.append(func_info)
            
            for child in node.children:
                traverse(child)
        
        traverse(node)
        return functions
    
    def _extract_classes(self, node: Node, content: str) -> List[Dict[str, Any]]:
        """Extract class definitions from AST"""
        classes = []
        
        def traverse(node: Node):
            if node.type in ['class_definition', 'class_declaration']:
                class_info = self._extract_class_info(node, content)
                if class_info:
                    classes.append(class_info)
            
            for child in node.children:
                traverse(child)
        
        traverse(node)
        return classes
    
    def _extract_imports(self, node: Node, content: str) -> List[Dict[str, Any]]:
        """Extract import statements from AST"""
        imports = []
        
        def traverse(node: Node):
            if node.type in ['import_statement', 'import_from_statement', 'import_declaration']:
                import_info = self._extract_import_info(node, content)
                if import_info:
                    imports.append(import_info)
            
            for child in node.children:
                traverse(child)
        
        traverse(node)
        return imports
    
    def _extract_variables(self, node: Node, content: str) -> List[Dict[str, Any]]:
        """Extract variable declarations from AST"""
        variables = []
        
        def traverse(node: Node):
            if node.type in ['variable_declaration', 'assignment_expression', 'assignment']:
                var_info = self._extract_variable_info(node, content)
                if var_info:
                    variables.append(var_info)
            
            for child in node.children:
                traverse(child)
        
        traverse(node)
        return variables
    
    def _extract_function_info(self, node: Node, content: str) -> Optional[Dict[str, Any]]:
        """Extract detailed information about a function"""
        try:
            name = self._get_node_text(self._find_child_by_type(node, 'identifier'), content)
            if not name:
                name = "anonymous"
            
            return {
                'name': name,
                'start_byte': node.start_byte,
                'end_byte': node.end_byte,
                'start_point': node.start_point,
                'end_point': node.end_point,
                'content': self._get_node_text(node, content),
                'parameters': self._extract_parameters(node, content),
                'docstring': self._extract_docstring(node, content)
            }
        except Exception as e:
            logger.warning(f"Error extracting function info: {e}")
            return None
    
    def _extract_class_info(self, node: Node, content: str) -> Optional[Dict[str, Any]]:
        """Extract detailed information about a class"""
        try:
            name = self._get_node_text(self._find_child_by_type(node, 'identifier'), content)
            if not name:
                name = "anonymous"
            
            return {
                'name': name,
                'start_byte': node.start_byte,
                'end_byte': node.end_byte,
                'start_point': node.start_point,
                'end_point': node.end_point,
                'content': self._get_node_text(node, content),
                'methods': self._extract_class_methods(node, content),
                'docstring': self._extract_docstring(node, content)
            }
        except Exception as e:
            logger.warning(f"Error extracting class info: {e}")
            return None
    
    def _extract_import_info(self, node: Node, content: str) -> Optional[Dict[str, Any]]:
        """Extract import information"""
        try:
            return {
                'content': self._get_node_text(node, content),
                'start_byte': node.start_byte,
                'end_byte': node.end_byte,
                'type': node.type
            }
        except Exception as e:
            logger.warning(f"Error extracting import info: {e}")
            return None
    
    def _extract_variable_info(self, node: Node, content: str) -> Optional[Dict[str, Any]]:
        """Extract variable information"""
        try:
            return {
                'content': self._get_node_text(node, content),
                'start_byte': node.start_byte,
                'end_byte': node.end_byte,
                'type': node.type
            }
        except Exception as e:
            logger.warning(f"Error extracting variable info: {e}")
            return None
    
    def _extract_parameters(self, func_node: Node, content: str) -> List[str]:
        """Extract function parameters"""
        params = []
        params_node = self._find_child_by_type(func_node, 'parameters')
        if params_node:
            for child in params_node.children:
                if child.type == 'identifier':
                    param_name = self._get_node_text(child, content)
                    if param_name:
                        params.append(param_name)
        return params
    
    def _extract_class_methods(self, class_node: Node, content: str) -> List[str]:
        """Extract method names from a class"""
        methods = []
        for child in class_node.children:
            if child.type in ['function_definition', 'method_definition']:
                name = self._get_node_text(self._find_child_by_type(child, 'identifier'), content)
                if name:
                    methods.append(name)
        return methods
    
    def _extract_docstring(self, node: Node, content: str) -> Optional[str]:
        """Extract docstring from function or class"""
        # Look for string literal as first statement in body
        body = self._find_child_by_type(node, 'block') or self._find_child_by_type(node, 'suite')
        if body and body.children:
            first_stmt = body.children[0] if body.children else None
            if first_stmt and first_stmt.type in ['expression_statement', 'string']:
                string_node = self._find_child_by_type(first_stmt, 'string') or first_stmt
                if string_node and string_node.type == 'string':
                    return self._get_node_text(string_node, content)
        return None
    
    def _find_child_by_type(self, node: Node, node_type: str) -> Optional[Node]:
        """Find first child node of specified type"""
        for child in node.children:
            if child.type == node_type:
                return child
        return None
    
    def _get_node_text(self, node: Optional[Node], content: str) -> Optional[str]:
        """Get text content of a node"""
        if not node:
            return None
        try:
            return content[node.start_byte:node.end_byte]
        except:
            return None
