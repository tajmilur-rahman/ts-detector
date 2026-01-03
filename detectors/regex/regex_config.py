spread_toggle_patterns = {
    "toggle_definition": r"^\s*([\w\.]+)\s*=\s*(.+)$",  
    "env_variable_reference": r"\${\?\w+}", 
    "comment": r"^\s*#",  
    "empty_line": r"^\s*$",
    "parent_finder": r"^\s*([\w\.]+)\s*=\s*\${\?([\w_]+)}"  
}