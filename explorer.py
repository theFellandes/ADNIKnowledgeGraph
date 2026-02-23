"""
ADNI Data Explorer - Comprehensive Analysis Tool
Helps identify available tables, columns, and diagnose data issues
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import logging
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class ADNIDataExplorer:
    """Comprehensive ADNI data exploration and validation tool"""

    def __init__(self, tables_path: str):
        self.tables_path = Path(tables_path)
        self.table_data = {}
        self.report = {
            'timestamp': datetime.now().isoformat(),
            'tables_found': [],
            'diagnosis_sources': {},
            'missing_critical_tables': [],
            'data_quality_issues': [],
            'recommendations': []
        }

    def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run complete analysis of ADNI data"""

        print("\n" + "=" * 80)
        print("ADNI DATA EXPLORER - COMPREHENSIVE ANALYSIS")
        print("=" * 80 + "\n")

        # Step 1: Load all tables
        self._load_all_tables()

        # Step 2: Identify critical tables
        self._identify_critical_tables()

        # Step 3: Analyze diagnosis data
        self._analyze_diagnosis_availability()

        # Step 4: Analyze cognitive assessments
        self._analyze_cognitive_assessments()

        # Step 5: Analyze biomarkers
        self._analyze_biomarkers()

        # Step 6: Analyze patient demographics
        self._analyze_demographics()

        # Step 7: Check data completeness
        self._check_data_completeness()

        # Step 8: Generate recommendations
        self._generate_recommendations()

        # Step 9: Export detailed report
        self._export_report()

        return self.report

    def _load_all_tables(self):
        """Load all CSV tables from the directory"""
        print("📂 Loading tables from:", self.tables_path)

        csv_files = list(self.tables_path.glob("*.csv"))
        print(f"Found {len(csv_files)} CSV files")

        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file, low_memory=False, nrows=1000)  # Sample for analysis
                table_name = csv_file.stem
                self.table_data[table_name] = df

                self.report['tables_found'].append({
                    'name': table_name,
                    'rows': len(pd.read_csv(csv_file, usecols=[0])),  # Count rows efficiently
                    'columns': list(df.columns),
                    'column_count': len(df.columns)
                })

                print(f"  ✓ Loaded {table_name}: {len(df.columns)} columns")

            except Exception as e:
                print(f"  ✗ Failed to load {csv_file.name}: {e}")
                self.report['data_quality_issues'].append(f"Failed to load {csv_file.name}: {e}")

    def _identify_critical_tables(self):
        """Identify which critical ADNI tables are present"""
        print("\n🔍 Checking for critical ADNI tables...")

        # Define critical tables based on ADNI documentation
        critical_tables = {
            'Diagnosis': ['DXSUM', 'DXSUM_PDXCONV_ADNIALL', 'ARM', 'REGISTRY', 'ADNIMERGE'],
            'Demographics': ['PTDEMOG', 'DEMO', 'DEMOGRAPHICS'],
            'Cognitive': ['MMSE', 'CDR', 'ADAS', 'MOCA', 'FAQ', 'NEUROBAT'],
            'Biomarkers': ['UPENNBIOMK', 'UPENNBIOMK_MASTER', 'UPENNBIOMK_ROCHE_ELECSYS',
                           'APOERES', 'CSF', 'BIOMARK'],
            'Imaging': ['MRILIST', 'PETLIST', 'UCBERKELEYAV45', 'UCBERKELEYAV1451', 'UCSFFSX'],
            'Family': ['FAMXHPAR', 'FAMXHSIB', 'FHQ'],
            'Visits': ['VISITS', 'REGISTRY', 'SCHEDULE']
        }

        found_critical = {}
        missing_critical = {}

        for category, table_patterns in critical_tables.items():
            found_critical[category] = []
            missing_critical[category] = []

            for pattern in table_patterns:
                found = False
                for table_name in self.table_data.keys():
                    if pattern.upper() in table_name.upper():
                        found_critical[category].append(table_name)
                        found = True
                        break

                if not found:
                    missing_critical[category].append(pattern)

        # Print results
        print("\n  Critical Tables Found:")
        for category, tables in found_critical.items():
            if tables:
                print(f"    {category}: {', '.join(tables)}")

        print("\n  ⚠️ Missing Critical Tables:")
        for category, tables in missing_critical.items():
            if tables:
                print(f"    {category}: {', '.join(tables)}")
                self.report['missing_critical_tables'].extend(tables)

    def _analyze_diagnosis_availability(self):
        """Detailed analysis of diagnosis data availability"""
        print("\n🏥 Analyzing Diagnosis Data...")

        diagnosis_analysis = {
            'tables_with_diagnosis': [],
            'diagnosis_columns_found': {},
            'sample_diagnosis_values': {},
            'patient_counts': {}
        }

        # ADNI diagnosis column patterns
        diagnosis_columns = [
            'DIAGNOSIS', 'DX', 'DXCHANGE', 'DXCURREN', 'DXCONV', 'DXCONTYP',
            'DXAD', 'DXMCI', 'DXNORM', 'DXCN', 'DXSMC', 'DXEMCI', 'DXLMCI',
            'ARM', 'ORIGPROT', 'DXBL', 'DX_bl', 'ENROLL_DX', 'ENROLLDX'
        ]

        for table_name, df in self.table_data.items():
            found_dx_cols = []

            for col in df.columns:
                col_upper = col.upper()
                for dx_pattern in diagnosis_columns:
                    if dx_pattern in col_upper:
                        found_dx_cols.append(col)

                        # Sample values
                        sample_values = df[col].value_counts().head(10).to_dict()
                        if table_name not in diagnosis_analysis['sample_diagnosis_values']:
                            diagnosis_analysis['sample_diagnosis_values'][table_name] = {}
                        diagnosis_analysis['sample_diagnosis_values'][table_name][col] = sample_values
                        break

            if found_dx_cols:
                diagnosis_analysis['tables_with_diagnosis'].append(table_name)
                diagnosis_analysis['diagnosis_columns_found'][table_name] = found_dx_cols

                # Count patients with diagnosis
                if 'PTID' in df.columns or 'RID' in df.columns:
                    id_col = 'PTID' if 'PTID' in df.columns else 'RID'
                    unique_patients = df[id_col].nunique()
                    diagnosis_analysis['patient_counts'][table_name] = unique_patients

        # Print analysis
        print(f"\n  Tables with diagnosis data: {len(diagnosis_analysis['tables_with_diagnosis'])}")
        for table in diagnosis_analysis['tables_with_diagnosis']:
            cols = diagnosis_analysis['diagnosis_columns_found'][table]
            count = diagnosis_analysis['patient_counts'].get(table, 'Unknown')
            print(f"    • {table}: {cols} (Patients: {count})")

        # Check for DXSUM specifically
        if 'DXSUM' not in self.table_data:
            print("\n  ⚠️ CRITICAL: DXSUM table is missing!")
            print("     According to ADNI documentation, diagnoses should be extracted from:")
            print("     - DXSUM table (primary source)")
            print("     - ARM table (for screening diagnoses)")
            print("     - REGISTRY table (for enrollment diagnoses)")

            self.report['data_quality_issues'].append(
                "DXSUM table missing - this is the primary diagnosis source"
            )

        self.report['diagnosis_sources'] = diagnosis_analysis

    def _analyze_cognitive_assessments(self):
        """Analyze available cognitive assessment data"""
        print("\n🧠 Analyzing Cognitive Assessments...")

        cognitive_tests = {
            'MMSE': ['MMSCORE', 'MMSE', 'TOTAL', 'TOTSCORE'],
            'CDR': ['CDGLOBAL', 'CDRSB', 'CDR'],
            'ADAS': ['TOTSCORE', 'TOTAL13', 'ADAS'],
            'MOCA': ['MOCA', 'MOCATOTS'],
            'FAQ': ['FAQTOTAL', 'FAQ']
        }

        found_assessments = {}

        for table_name, df in self.table_data.items():
            for test_name, score_patterns in cognitive_tests.items():
                if test_name in table_name.upper():
                    # Look for score columns
                    score_cols = []
                    for col in df.columns:
                        for pattern in score_patterns:
                            if pattern in col.upper():
                                score_cols.append(col)
                                break

                    if score_cols:
                        found_assessments[table_name] = {
                            'test': test_name,
                            'score_columns': score_cols,
                            'sample_count': len(df)
                        }

        print(f"  Found {len(found_assessments)} cognitive assessment tables:")
        for table, info in found_assessments.items():
            print(f"    • {table}: {info['test']} test, columns: {info['score_columns']}")

    def _analyze_biomarkers(self):
        """Analyze available biomarker data"""
        print("\n🧪 Analyzing Biomarker Data...")

        biomarker_patterns = {
            'CSF': ['ABETA', 'TAU', 'PTAU'],
            'APOE': ['APOE', 'APGEN'],
            'Blood': ['PLASMA', 'SERUM']
        }

        found_biomarkers = {}

        for table_name, df in self.table_data.items():
            if any(pattern in table_name.upper() for pattern in ['BIOMK', 'BIOMARK', 'APOE', 'CSF']):
                biomarker_cols = []

                for col in df.columns:
                    col_upper = col.upper()
                    for category, patterns in biomarker_patterns.items():
                        if any(p in col_upper for p in patterns):
                            biomarker_cols.append((col, category))
                            break

                if biomarker_cols:
                    found_biomarkers[table_name] = biomarker_cols

        print(f"  Found {len(found_biomarkers)} biomarker tables:")
        for table, cols in found_biomarkers.items():
            unique_categories = set(cat for _, cat in cols)
            print(f"    • {table}: {', '.join(unique_categories)} biomarkers")

    def _analyze_demographics(self):
        """Analyze patient demographic data"""
        print("\n👥 Analyzing Demographics...")

        demo_cols = ['AGE', 'GENDER', 'SEX', 'RACE', 'ETHNIC', 'EDUCAT']
        found_demo = {}

        for table_name, df in self.table_data.items():
            if any(pattern in table_name.upper() for pattern in ['DEMOG', 'DEMO', 'REGISTRY']):
                demo_info = []
                for col in df.columns:
                    col_upper = col.upper()
                    for demo_pattern in demo_cols:
                        if demo_pattern in col_upper:
                            demo_info.append(col)
                            break

                if demo_info:
                    found_demo[table_name] = demo_info

                    # Count unique patients
                    if 'PTID' in df.columns:
                        unique_pts = df['PTID'].nunique()
                        print(f"    • {table_name}: {unique_pts} patients, fields: {demo_info}")

    def _check_data_completeness(self):
        """Check overall data completeness"""
        print("\n✅ Checking Data Completeness...")

        # Count total unique patients across all tables
        all_patient_ids = set()

        for table_name, df in self.table_data.items():
            for id_col in ['PTID', 'RID', 'SUBJID']:
                if id_col in df.columns:
                    ids = df[id_col].dropna().unique()
                    all_patient_ids.update(str(id) for id in ids)
                    break

        print(f"  Total unique patients found: {len(all_patient_ids)}")

        # Check key data availability
        patients_with_diagnosis = 0
        patients_with_cognitive = 0
        patients_with_biomarkers = 0

        # This is simplified - in reality would need to join tables
        for table_name in self.report['diagnosis_sources']['tables_with_diagnosis']:
            if table_name in self.table_data:
                df = self.table_data[table_name]
                if 'PTID' in df.columns:
                    patients_with_diagnosis = max(patients_with_diagnosis, df['PTID'].nunique())

        print(f"  Patients with diagnosis data: {patients_with_diagnosis}")

        # Calculate completeness percentage
        if len(all_patient_ids) > 0:
            completeness = (patients_with_diagnosis / len(all_patient_ids)) * 100
            print(f"  Diagnosis coverage: {completeness:.1f}%")

            if completeness < 50:
                self.report['data_quality_issues'].append(
                    f"Low diagnosis coverage: only {completeness:.1f}% of patients have diagnosis data"
                )

    def _generate_recommendations(self):
        """Generate specific recommendations based on analysis"""
        print("\n💡 Generating Recommendations...")

        recommendations = []

        # Check for missing DXSUM
        if 'DXSUM' not in self.table_data and 'DXSUM_PDXCONV_ADNIALL' not in self.table_data:
            recommendations.append({
                'priority': 'CRITICAL',
                'issue': 'Missing DXSUM table',
                'action': 'Download DXSUM_PDXCONV_ADNIALL.csv from ADNI website',
                'details': 'This is the primary source for diagnosis data. Without it, disease classification is impossible.'
            })

        # Check for missing ARM
        if 'ARM' not in self.table_data:
            recommendations.append({
                'priority': 'HIGH',
                'issue': 'Missing ARM table',
                'action': 'Download ARM.csv from ADNI website',
                'details': 'ARM table contains screening diagnoses for ADNI1/GO/2 participants.'
            })

        # Check for missing REGISTRY
        if 'REGISTRY' not in self.table_data:
            recommendations.append({
                'priority': 'HIGH',
                'issue': 'Missing REGISTRY table',
                'action': 'Download REGISTRY.csv from ADNI website',
                'details': 'REGISTRY contains enrollment data and exam dates necessary for temporal analysis.'
            })

        # Check for biomarker data
        if not any('BIOMK' in t.upper() for t in self.table_data.keys()):
            recommendations.append({
                'priority': 'MEDIUM',
                'issue': 'No biomarker data found',
                'action': 'Download UPENNBIOMK tables from ADNI',
                'details': 'Biomarker data (CSF Aβ42, Tau, p-Tau) is crucial for AD research.'
            })

        # Check diagnosis column mapping
        if self.report['diagnosis_sources']['tables_with_diagnosis']:
            recommendations.append({
                'priority': 'INFO',
                'issue': 'Complex diagnosis mapping required',
                'action': 'Use the enhanced Step 6 extractor provided',
                'details': 'ADNI uses different diagnosis variables across phases. The enhanced extractor handles this.'
            })

        self.report['recommendations'] = recommendations

        # Print recommendations
        for rec in recommendations:
            icon = "🔴" if rec['priority'] == 'CRITICAL' else "🟡" if rec['priority'] == 'HIGH' else "🟢"
            print(f"\n  {icon} [{rec['priority']}] {rec['issue']}")
            print(f"     Action: {rec['action']}")
            print(f"     Details: {rec['details']}")

    def _export_report(self):
        """Export detailed analysis report"""
        report_file = Path("adni_data_analysis_report.json")

        with open(report_file, 'w') as f:
            json.dump(self.report, f, indent=2, default=str)

        print(f"\n📄 Detailed report saved to: {report_file}")

        # Also create a summary CSV
        summary_data = []
        for table_info in self.report['tables_found']:
            summary_data.append({
                'Table': table_info['name'],
                'Rows': table_info['rows'],
                'Columns': table_info['column_count'],
                'Has_Diagnosis': table_info['name'] in self.report['diagnosis_sources']['tables_with_diagnosis'],
                'Critical': table_info['name'] in ['DXSUM', 'ARM', 'REGISTRY', 'PTDEMOG']
            })

        summary_df = pd.DataFrame(summary_data)
        summary_df.to_csv('adni_tables_summary.csv', index=False)
        print(f"📊 Summary saved to: adni_tables_summary.csv")

    def generate_diagnosis_mapping_guide(self):
        """Generate a guide for mapping diagnosis codes based on ADNI phase"""
        print("\n📖 Generating Diagnosis Mapping Guide...")

        guide = """
        ADNI DIAGNOSIS MAPPING GUIDE
        ============================

        Based on ADNI documentation, diagnosis extraction varies by study phase:

        1. ADNI-1 Participants:
           - Primary: DXCURREN (1=NL, 2=MCI, 3=AD)
           - Conversion: DXCONV (0=No, 1=Conversion, 2=Reversion)
           - Conversion Type: DXCONTYP (1=NL→MCI, 2=NL→AD, 3=MCI→AD)
           - Reversion: DXREV (1=MCI→NL, 2=AD→MCI, 3=AD→NL)

        2. ADNI-GO/2 Participants:
           - Single variable: DXCHANGE
             1 = Stable: NL to NL
             2 = Stable: MCI to MCI
             3 = Stable: AD to AD
             4 = Conversion: NL to MCI
             5 = Conversion: MCI to AD
             6 = Conversion: NL to AD
             7 = Reversion: MCI to NL
             8 = Reversion: AD to MCI
             9 = Reversion: AD to NL

        3. ADNI-3 Participants:
           - Primary: DIAGNOSIS variable in DXSUM
           - Values: 1=CN, 2=MCI, 3=AD

        4. Screening Diagnoses:
           - ADNI-1/GO/2: Use ARM table, column 'ARM'
           - ADNI-3: Use DXSUM table
           - Look for: CN, EMCI, LMCI, SMC, AD

        5. Special Classifications:
           - EMCI: Early MCI (only at baseline/screening)
           - LMCI: Late MCI (only at baseline/screening)
           - SMC: Subjective Memory Concern
           - These revert to generic 'MCI' at follow-up

        RECOMMENDED EXTRACTION ORDER:
        1. Check DXSUM for visit diagnoses
        2. Check ARM for screening/baseline diagnoses
        3. Check REGISTRY for enrollment diagnoses
        4. Derive from CDR/MMSE scores if needed
        """

        guide_file = Path("adni_diagnosis_mapping_guide.txt")
        with open(guide_file, 'w') as f:
            f.write(guide)

        print(f"  Guide saved to: {guide_file}")
        print("\n  Key insight: You need both DXSUM and ARM tables for complete diagnosis coverage!")


def main():
    """Main execution function"""
    import argparse

    parser = argparse.ArgumentParser(description="ADNI Data Explorer")
    parser.add_argument("--tables-path", default="inputs/Tables",
                        help="Path to ADNI tables directory")
    parser.add_argument("--export-headers", action="store_true",
                        help="Export all table headers to a single file")

    args = parser.parse_args()

    # Run explorer
    explorer = ADNIDataExplorer(args.tables_path)
    report = explorer.run_comprehensive_analysis()

    # Generate diagnosis guide
    explorer.generate_diagnosis_mapping_guide()

    # Export headers if requested
    if args.export_headers:
        headers = {}
        for table_name, df in explorer.table_data.items():
            headers[table_name] = list(df.columns)

        with open('adni_all_headers.json', 'w') as f:
            json.dump(headers, f, indent=2)
        print("\n📝 All table headers exported to: adni_all_headers.json")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE!")
    print("=" * 80)

    # Print critical action items
    critical_items = [r for r in report['recommendations'] if r['priority'] == 'CRITICAL']
    if critical_items:
        print("\n⚠️ CRITICAL ACTION ITEMS:")
        for item in critical_items:
            print(f"  • {item['action']}")

    print("\nNext steps:")
    print("1. Review adni_data_analysis_report.json for full details")
    print("2. Download missing critical tables from ADNI")
    print("3. Use the enhanced Step 6 extractor for diagnosis extraction")
    print("4. Re-run the pipeline with complete data")


if __name__ == "__main__":
    main()