import os

def read_env_file(path=".env"):
    """Reads the .env file and returns a dictionary of key-value pairs."""
    if not os.path.exists(path):
        return {}
    
    env_vars = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars

def update_env_file(key, value, path=".env"):
    """Updates or adds a key-value pair in the .env file."""
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    key_found = False
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f'{key}="{value}"\n')
            key_found = True
        else:
            new_lines.append(line)
            
    if not key_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f'{key}="{value}"\n')
        
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    # Reload environment variable for the current process
    os.environ[key] = value

def get_env_variable(key, path=".env"):
    """Get a specific variable directly from file or os.environ backup."""
    vars = read_env_file(path)
    return vars.get(key, os.environ.get(key, ""))
