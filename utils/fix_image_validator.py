#!/usr/bin/env python3
"""
Script to automatically fix the image_validator.py file
Run this in the same directory as image_validator.py
"""

import re
import sys
from pathlib import Path


def apply_fixes(filepath="image_validator.py"):
    """Apply fixes to the image_validator.py file"""

    file_path = Path(filepath)
    if not file_path.exists():
        print(f"Error: {filepath} not found!")
        return False

    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()

    # Backup the original
    backup_path = file_path.with_suffix('.py.backup')
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup: {backup_path}")

    # Fix 1: Update ImageValidationResult dataclass to include default values
    # Find the class definition and update the file existence fields
    pattern1 = r'(class ImageValidationResult:.*?# File existence checks\s*\n)(.*?)(# Pixel integrity checks)'

    replacement1 = r'''\1    metadata_exists: bool = False
    diagnostic_tiff_exists: bool = False
    diagnostic_png_exists: bool = False
    thumbnail_exists: bool = False
    sharpened_tiff_exists: bool = False
    smooth_tiff_exists: bool = False

    \3'''

    content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)

    # Fix 2: Update print_summary to handle division by zero
    # Find the print statements with division
    old_lines = [
        'print(f"  ✅ Passed:            {report.total_images_passed} "',
        '      f"({report.total_images_passed/report.total_images_validated*100:.1f}%)")',
        'print(f"  ⚠️  With Warnings:     {report.total_images_with_warnings} "',
        '      f"({report.total_images_with_warnings/report.total_images_validated*100:.1f}%)")',
        'print(f"  ❌ Failed:            {report.total_images_failed} "',
        '      f"({report.total_images_failed/report.total_images_validated*100:.1f}%)")'
    ]

    # Create the replacement with proper indentation
    new_block = '''
    # Handle division by zero
    if report.total_images_validated > 0:
        print(f"  ✅ Passed:            {report.total_images_passed} "
              f"({report.total_images_passed/report.total_images_validated*100:.1f}%)")
        print(f"  ⚠️  With Warnings:     {report.total_images_with_warnings} "
              f"({report.total_images_with_warnings/report.total_images_validated*100:.1f}%)")
        print(f"  ❌ Failed:            {report.total_images_failed} "
              f"({report.total_images_failed/report.total_images_validated*100:.1f}%)")
    else:
        print("  ⚠️  No images were successfully validated!")
        print("  Check the metadata directory and ensure processed images exist.")'''

    # Find and replace the problematic section
    pattern2 = r'print\(f"Total Images Validated: \{report\.total_images_validated\}"\)\s*\n\s*print.*?Failed:.*?\)\)"?\)'

    replacement2 = f'print(f"Total Images Validated: {{report.total_images_validated}}")' + new_block

    content = re.sub(pattern2, replacement2, content, flags=re.DOTALL)

    # Fix 3: Add safety check in _compile_statistics
    pattern3 = r'(def _compile_statistics\(self, report: PipelineValidationReport\):.*?\n.*?""".*?"""\s*\n)(.*?)(total = len\(report\.validation_results\))'

    replacement3 = r'''\1    if not report.validation_results:
        logger.warning("No validation results to compile statistics from")
        return

    \3'''

    content = re.sub(pattern3, replacement3, content, flags=re.DOTALL)

    # Add another safety check after total calculation
    content = content.replace(
        'report.total_images_validated = total',
        '''if total == 0:
        logger.warning("Total validation results is 0, skipping statistics")
        return

    report.total_images_validated = total'''
    )

    # Fix the modality stats division by zero
    content = content.replace(
        "print(f\"  Passed: {stats['passed']} ({stats['passed']/total*100:.1f}%)\")",
        "if total > 0:\n                print(f\"  Passed: {stats['passed']} ({stats['passed']/total*100:.1f}%)\")"
    )

    # Write the fixed content
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"✅ Successfully applied fixes to {filepath}")
    print("\nFixed issues:")
    print("1. Added default values to ImageValidationResult fields")
    print("2. Added division by zero protection in print_summary")
    print("3. Added safety checks in _compile_statistics")

    return True


if __name__ == "__main__":
    # Check if a custom path was provided
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "image_validator.py"

    success = apply_fixes(filepath)

    if success:
        print("\n🎉 Fixes applied successfully!")
        print("You can now run the validator again.")
    else:
        print("\n❌ Failed to apply fixes.")
        sys.exit(1)