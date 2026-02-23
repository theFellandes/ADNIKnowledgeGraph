"""
Reference Verification Script
Extracts all entries from references.bib and provides verification guidance.
Run this to check which entries need manual verification on Google Scholar.
"""
import re
from pathlib import Path

def extract_entries(bib_path):
    """Extract all BibTeX entries with their key fields."""
    content = Path(bib_path).read_text(encoding='utf-8')
    
    # Pattern to match full entries
    entry_pattern = r'@(\w+)\{(\w+),(.*?)(?=\n@|\Z)'
    entries = re.findall(entry_pattern, content, re.DOTALL)
    
    results = []
    for entry_type, key, body in entries:
        # Extract fields
        author_match = re.search(r'author\s*=\s*\{([^}]+)\}', body)
        title_match = re.search(r'title\s*=\s*\{([^}]+)\}', body)
        journal_match = re.search(r'(?:journal|booktitle)\s*=\s*\{([^}]+)\}', body)
        year_match = re.search(r'year\s*=\s*\{?(\d{4})\}?', body)
        doi_match = re.search(r'doi\s*=\s*\{([^}]+)\}', body)
        note_match = re.search(r'note\s*=\s*\{([^}]+)\}', body)
        
        results.append({
            'key': key,
            'type': entry_type,
            'author': author_match.group(1)[:50] if author_match else 'N/A',
            'title': title_match.group(1)[:80] if title_match else 'N/A',
            'journal': journal_match.group(1) if journal_match else 'N/A',
            'year': year_match.group(1) if year_match else 'N/A',
            'has_doi': bool(doi_match),
            'has_note': bool(note_match),
            'note': note_match.group(1) if note_match else None
        })
    
    return results

def main():
    bib_path = 'docs/references.bib'
    entries = extract_entries(bib_path)
    
    print(f"Total entries: {len(entries)}")
    print(f"Entries with DOI: {sum(1 for e in entries if e['has_doi'])}")
    print(f"Entries with notes: {sum(1 for e in entries if e['has_note'])}")
    print()
    
    # Flag entries needing verification
    print("=" * 80)
    print("ENTRIES NEEDING VERIFICATION (no DOI or have notes):")
    print("=" * 80)
    
    needs_verification = []
    for e in entries:
        if not e['has_doi'] or e['has_note']:
            needs_verification.append(e)
            print(f"\n{e['key']} ({e['year']})")
            print(f"  Title: {e['title']}")
            print(f"  Journal: {e['journal']}")
            print(f"  Has DOI: {e['has_doi']}")
            if e['note']:
                print(f"  Note: {e['note']}")
    
    print(f"\n\nTotal needing verification: {len(needs_verification)}")
    
    # Output for manual checking
    print("\n" + "=" * 80)
    print("SEARCH QUERIES FOR GOOGLE SCHOLAR:")
    print("=" * 80)
    for e in needs_verification:
        author_first = e['author'].split(',')[0].split(' and ')[0]
        title_short = e['title'][:60].replace('{', '').replace('}', '')
        print(f'\n{e["key"]}: "{title_short}" {author_first} {e["year"]}')

if __name__ == '__main__':
    main()
