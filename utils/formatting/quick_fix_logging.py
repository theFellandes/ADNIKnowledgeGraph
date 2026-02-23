"""
Quick fix for the most common files with logging format issues
Run this if the automated fix doesn't work
"""

import os
from pathlib import Path

# Files that commonly have the logging format issue
FILES_TO_FIX = [
    "steps/step1_database_setup.py",
    "steps/step2_load_tables.py",
    "steps/step3_create_patients.py",
    "steps/step4_extract_family.py",
    "steps/step5_process_images.py",
    "steps/step5_process_images_external.py",
    "steps/step6_extract_findings.py",
    "steps/step7_batch_insert.py",
    "steps/step8_create_relationships.py",
    "utils/neo4j_connector.py",
    "utils/batch_processor.py",
    "utils/quality_aware_logger.py",
    "pipeline.py"
]


def fix_file(filepath):
    """Fix a single file"""
    if not os.path.exists(filepath):
        print(f"⚠️  File not found: {filepath}")
        return False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content

        # Fix all common logging format patterns
        replacements = [
            ('"%(asctime)s', '"%(asctime)s'),
            ("'%(asctime)s", "'%(asctime)s"),
            ('"%(name)s', '"%(name)s'),
            ("'%(name)s", "'%(name)s"),
            ('"%(levelname)s', '"%(levelname)s'),
            ("'%(levelname)s", "'%(levelname)s"),
            ('"%(message)s', '"%(message)s'),
            ("'%(message)s", "'%(message)s"),
            ('"%(filename)s', '"%(filename)s'),
            ("'%(filename)s", "'%(filename)s"),
            ('"%(lineno)d', '"%(lineno)d'),
            ("'%(lineno)d", "'%(lineno)d"),
            ('"%(funcName)s', '"%(funcName)s'),
            ("'%(funcName)s", "'%(funcName)s"),
        ]

        for old, new in replacements:
            content = content.replace(old, new)

        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Fixed: {filepath}")
            return True
        else:
            print(f"✔️  No issues in: {filepath}")
            return False

    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        return False


def main():
    print("=" * 60)
    print("QUICK FIX FOR LOGGING FORMAT ISSUES")
    print("=" * 60)

    fixed_count = 0

    for filepath in FILES_TO_FIX:
        if fix_file(filepath):
            fixed_count += 1

    print("\n" + "=" * 60)
    print(f"Fixed {fixed_count} files")

    if fixed_count > 0:
        print("\n✅ Logging issues fixed! You can now run:")
        print("   python pipeline.py --config updated_config.yaml")
    else:
        print("\n✔️  No logging issues found or all were already fixed")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())