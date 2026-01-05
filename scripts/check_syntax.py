import os
import sys
import compileall

def check_syntax(directory):
    print(f"Checking syntax for Python files in {directory}...")
    success = compileall.compile_dir(directory, force=True, quiet=1)
    if success:
        print("Syntax check passed for all files.")
    else:
        print("Syntax errors found.")

if __name__ == "__main__":
    check_syntax(".")
