"""
Step 2: Load and Process CSV Tables
Loads all ADNI CSV tables and categorizes them
"""

import logging
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Any
import concurrent.futures
from utils.batch_processor import BatchProcessor, DataValidator

logger = logging.getLogger(__name__)


class TableLoader:
    """Load and categorize ADNI CSV tables"""

    # Table categorization based on content
    TABLE_CATEGORIES = {
        'demographics': ['PTDEMOG', 'ARM', 'CONSENTS', 'INCLUSIO', 'EXCLUSIO'],
        'cognitive': ['MMSE', 'CDR', 'ADAS', 'MOCA', 'RAVLT', 'FAQ', 'NEUROBAT',
                      'ECOGPT', 'ECOGSP', 'FCI', 'AMNART'],
        'biomarkers': ['BIOMARK', 'CSF', 'ELECSYS', 'LABDATA', 'LOCLAB',
                       'LABTESTS', 'TAU', 'PTAU', 'ABETA'],
        'imaging': ['MRI3META', 'MRIMETA', 'PETMETA', 'PETC3', 'AMYMETA',
                    'TAUMETA', 'AV45META', 'MRIFind', 'UCSFFSX7'],
        'clinical': ['DXSUM', 'MEDHIST', 'VITALS', 'PHYSICAL', 'NEUROEXM',
                     'BLCHANGE', 'BLSCHECK'],
        'family': ['FAMHXPAR', 'FAMHXSIB', 'FHQ'],
        'genetics': ['APOERES', 'GENETIC'],
        'other': []  # Catch-all for uncategorized tables
    }

    def __init__(self, tables_path: str, batch_processor: BatchProcessor = None):
        self.tables_path = Path(tables_path)
        self.batch_processor = batch_processor or BatchProcessor()
        self.table_data = {}
        self.table_categories = {}

    def execute(self) -> Dict[str, pd.DataFrame]:
        """
        Load all tables and return categorized data

        Returns:
            Dictionary mapping table names to DataFrames
        """
        if not self.tables_path.exists():
            raise FileNotFoundError(f"Tables directory not found: {self.tables_path}")

        # Get all CSV files
        csv_files = list(self.tables_path.glob("*.csv"))
        logger.info(f"Found {len(csv_files)} CSV files to process")

        if not csv_files:
            logger.warning("No CSV files found in tables directory")
            return {}

        # Load tables in parallel
        self._load_tables_parallel(csv_files)

        # Categorize tables
        self._categorize_tables()

        # Log summary
        self._log_summary()

        return self.table_data

    def _load_tables_parallel(self, csv_files: List[Path]) -> None:
        """Load tables in parallel"""

        def load_single_table(csv_file: Path) -> Tuple[str, pd.DataFrame]:
            try:
                df = pd.read_csv(
                    csv_file,
                    low_memory=False,
                    na_values=['', 'NA', 'NaN', 'NULL', 'null', 'N/A', 'n/a', '-', '--'],
                    keep_default_na=True,
                    encoding='utf-8'
                )

                # Clean column names
                df.columns = df.columns.str.strip()

                # Basic validation
                if df.empty:
                    logger.warning(f"Empty table: {csv_file.name}")
                    return None

                table_name = csv_file.stem
                logger.info(f"Loaded {table_name}: {len(df)} rows, {len(df.columns)} columns")

                return table_name, df

            except Exception as e:
                logger.error(f"Failed to load {csv_file}: {e}")
                return None

        # Process files
        results = self.batch_processor.process_parallel(
            csv_files,
            load_single_table,
            desc="Loading CSV tables"
        )

        # Store results
        for result in results:
            if result:
                table_name, df = result
                self.table_data[table_name] = df

    def _categorize_tables(self) -> None:
        """Categorize tables based on naming patterns"""
        for table_name in self.table_data.keys():
            category = self._determine_category(table_name)
            self.table_categories[table_name] = category

            # Add to category mapping
            if category not in self.TABLE_CATEGORIES:
                self.TABLE_CATEGORIES[category] = []
            if table_name not in self.TABLE_CATEGORIES[category]:
                self.TABLE_CATEGORIES[category].append(table_name)

    def _determine_category(self, table_name: str) -> str:
        """Determine category for a table based on name"""
        table_upper = table_name.upper()

        # Check each category
        for category, patterns in self.TABLE_CATEGORIES.items():
            for pattern in patterns:
                if pattern in table_upper:
                    return category

        # Special pattern matching
        if any(term in table_upper for term in ['SCORE', 'TEST', 'SCALE']):
            return 'cognitive'
        elif any(term in table_upper for term in ['META', 'QC', 'VOLUME']):
            return 'imaging'
        elif any(term in table_upper for term in ['LAB', 'MARKER', 'PROTEIN']):
            return 'biomarkers'

        return 'other'

    def _log_summary(self) -> None:
        """Log summary of loaded tables"""
        logger.info("\n" + "=" * 60)
        logger.info("TABLE LOADING SUMMARY")
        logger.info("=" * 60)

        # Overall stats
        total_tables = len(self.table_data)
        total_rows = sum(len(df) for df in self.table_data.values())
        logger.info(f"Total tables loaded: {total_tables}")
        logger.info(f"Total data rows: {total_rows:,}")

        # By category
        logger.info("\nTables by category:")
        for category in ['demographics', 'cognitive', 'biomarkers', 'imaging',
                         'clinical', 'family', 'genetics', 'other']:
            tables = [t for t, c in self.table_categories.items() if c == category]
            if tables:
                row_count = sum(len(self.table_data[t]) for t in tables)
                logger.info(f"  {category.upper()}: {len(tables)} tables, {row_count:,} rows")
                for table in sorted(tables):
                    logger.info(f"    - {table}: {len(self.table_data[table]):,} rows")

    def get_tables_by_category(self, category: str) -> Dict[str, pd.DataFrame]:
        """Get all tables in a specific category"""
        tables = {}
        for table_name, table_category in self.table_categories.items():
            if table_category == category:
                tables[table_name] = self.table_data[table_name]
        return tables

    def get_patient_ids(self) -> List[str]:
        """Extract unique patient IDs from all tables"""
        patient_ids = set()

        # Common ID columns
        id_columns = ['PTID', 'RID', 'SUBJID']

        for table_name, df in self.table_data.items():
            for id_col in id_columns:
                if id_col in df.columns:
                    ids = df[id_col].dropna().unique()
                    # Validate and add
                    for id_val in ids:
                        id_str = str(id_val).strip()
                        if id_str and DataValidator.validate_patient_id(id_str):
                            patient_ids.add(id_str)

        logger.info(f"Found {len(patient_ids)} unique patient IDs")
        return sorted(list(patient_ids))

    def preprocess_table_data(self) -> None:
        """Preprocess tables for consistency"""
        for table_name, df in self.table_data.items():
            # Standardize patient ID columns
            if 'SUBJID' in df.columns and 'PTID' not in df.columns:
                df['PTID'] = df['SUBJID']

            # Convert visit codes to standard format
            if 'VISCODE' in df.columns:
                df['VISCODE'] = df['VISCODE'].str.strip().str.lower()
            elif 'VISCODE2' in df.columns:
                df['VISCODE'] = df['VISCODE2'].str.strip().str.lower()

            # Clean string columns
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].apply(lambda x: DataValidator.clean_string(x) if pd.notna(x) else x)


def execute_table_loading(tables_path: str) -> Dict[str, Any]:
    """
    Main execution function for table loading

    Args:
        tables_path: Path to tables directory

    Returns:
        Dictionary with loaded tables and metadata
    """
    loader = TableLoader(tables_path)

    try:
        # Load tables
        table_data = loader.execute()

        # Preprocess
        loader.preprocess_table_data()

        # Get summary info
        results = {
            'table_data': table_data,
            'table_categories': loader.table_categories,
            'patient_ids': loader.get_patient_ids(),
            'summary': {
                'total_tables': len(table_data),
                'total_rows': sum(len(df) for df in table_data.values()),
                'categories': {
                    cat: len(loader.get_tables_by_category(cat))
                    for cat in loader.TABLE_CATEGORIES.keys()
                }
            }
        }

        logger.info("✅ Table loading completed successfully")
        return results

    except Exception as e:
        logger.error(f"Table loading failed: {e}")
        raise


if __name__ == "__main__":
    # Test execution
    results = execute_table_loading("inputs/Tables")
    print(f"Loaded {results['summary']['total_tables']} tables")
    print(f"Found {len(results['patient_ids'])} patients")