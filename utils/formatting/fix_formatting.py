"""
Fix logging format issues in all Python files
This script will find and fix the "%(asctime)s" format error
"""

import os
import re
from pathlib import Path


def fix_logging_format_in_file(file_path):
    """Fix logging format strings in a single file"""

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

    # Original content for comparison
    original_content = content

    # Fix patterns with space between % and (
    patterns_to_fix = [
        (r'"%\s+\(asctime\)s', '"%(asctime)s'),  # "%(asctime)s" -> "%(asctime)s"
        (r"'%\s+\(asctime\)s", "'%(asctime)s"),  # '%(asctime)s' -> '%(asctime)s'
        (r'"%\s+\(name\)s', '"%(name)s'),  # "%(name)s" -> "%(name)s"
        (r"'%\s+\(name\)s", "'%(name)s"),  # '%(name)s' -> '%(name)s'
        (r'"%\s+\(levelname\)s', '"%(levelname)s'),  # "%(levelname)s" -> "%(levelname)s"
        (r"'%\s+\(levelname\)s", "'%(levelname)s"),  # '%(levelname)s' -> '%(levelname)s'
        (r'"%\s+\(message\)s', '"%(message)s'),  # "%(message)s" -> "%(message)s"
        (r"'%\s+\(message\)s", "'%(message)s"),  # '%(message)s' -> '%(message)s'
        (r'"%\s+\(lineno\)d', '"%(lineno)d'),  # "%(lineno)d" -> "%(lineno)d"
        (r"'%\s+\(lineno\)d", "'%(lineno)d"),  # '%(lineno)d' -> '%(lineno)d'
        (r'"%\s+\(filename\)s', '"%(filename)s'),  # "%(filename)s" -> "%(filename)s"
        (r"'%\s+\(filename\)s", "'%(filename)s"),  # '%(filename)s' -> '%(filename)s'
        (r'"%\s+\(funcName\)s', '"%(funcName)s'),  # "%(funcName)s" -> "%(funcName)s"
        (r"'%\s+\(funcName\)s", "'%(funcName)s"),  # '%(funcName)s' -> '%(funcName)s'
    ]

    for pattern, replacement in patterns_to_fix:
        content = re.sub(pattern, replacement, content)

    # Also fix any generic pattern with space after %
    # This catches any %(xxx)s or %(xxx)d patterns with spaces
    content = re.sub(r'(["\'])%\s+\((\w+)\)([sd])', r'\1%(\2)\3', content)

    # Check if we made any changes
    if content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error writing {file_path}: {e}")
            return False

    return False


def find_and_fix_all_files(root_dir):
    """Find and fix all Python files with logging format issues"""

    root_path = Path(root_dir)
    fixed_files = []
    checked_files = 0

    # Directories to check
    dirs_to_check = ['steps', 'utils', 'models', '.']

    for dir_name in dirs_to_check:
        dir_path = root_path / dir_name if dir_name != '.' else root_path

        if not dir_path.exists():
            continue

        # Find all Python files
        if dir_name == '.':
            # For root, only check direct .py files, not subdirectories
            py_files = [f for f in dir_path.glob('*.py') if f.is_file()]
        else:
            # For subdirectories, check all Python files recursively
            py_files = list(dir_path.rglob('*.py'))

        for py_file in py_files:
            checked_files += 1
            if fix_logging_format_in_file(py_file):
                fixed_files.append(py_file)
                print(f"✅ Fixed: {py_file.relative_to(root_path)}")

    return fixed_files, checked_files


def verify_logging_formats(root_dir):
    """Verify that no files have the incorrect format"""

    root_path = Path(root_dir)
    problem_files = []

    dirs_to_check = ['steps', 'utils', 'models', '.']

    for dir_name in dirs_to_check:
        dir_path = root_path / dir_name if dir_name != '.' else root_path

        if not dir_path.exists():
            continue

        if dir_name == '.':
            py_files = [f for f in dir_path.glob('*.py') if f.is_file()]
        else:
            py_files = list(dir_path.rglob('*.py'))

        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check for problematic patterns
                if re.search(r'["\']%\s+\(\w+\)[sd]', content):
                    problem_files.append(py_file)
            except Exception as e:
                continue

    return problem_files


def main():
    """Main function to fix all logging format issues"""

    print("=" * 60)
    print("FIXING LOGGING FORMAT ISSUES")
    print("=" * 60)

    # Get the root directory (current directory)
    root_dir = Path.cwd()
    print(f"Working directory: {root_dir}")

    # First, find and fix all files
    print("\nSearching for files with logging format issues...")
    fixed_files, checked_files = find_and_fix_all_files(root_dir)

    print(f"\nChecked {checked_files} files")
    print(f"Fixed {len(fixed_files)} files")

    if fixed_files:
        print("\nFixed files:")
        for f in fixed_files:
            print(f"  - {f.relative_to(root_dir)}")

    # Verify that all issues are fixed
    print("\nVerifying all files are fixed...")
    problem_files = verify_logging_formats(root_dir)

    if problem_files:
        print(f"\n⚠️  WARNING: {len(problem_files)} files still have issues:")
        for f in problem_files:
            print(f"  - {f.relative_to(root_dir)}")
        return 1
    else:
        print("\n✅ All logging format issues have been fixed!")
        print("\nYou can now run the pipeline:")
        print("  python pipeline.py --config updated_config.yaml")
        return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())