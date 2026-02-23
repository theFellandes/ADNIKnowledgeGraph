
# ADNI Knowledge Graph Performance Metrics - IEEE Paper Artifacts

This directory contains all performance metrics, figures, and tables for the IEEE paper
"Performance Evaluation of ADNI Knowledge Graph for Biomedical Data Querying"

## Directory Structure

- `figures/`: Publication-quality PDF figures
  - figure1_performance_complexity.pdf: Query performance by complexity class
  - figure2_scalability.pdf: Scalability analysis with curve fitting
  - figure3_throughput_latency.pdf: Throughput and latency under concurrent load
  - figure4_index_effectiveness.pdf: Index usage and effectiveness
  - figure5_resource_utilization.pdf: CPU and memory utilization patterns
  - figure6_comparative_analysis.pdf: Comparison with existing systems

- `tables/`: LaTeX table definitions
  - table1_query_classification.tex: Query complexity classification
  - table2_performance_summary.tex: Performance metrics summary
  - table3_scalability.tex: Scalability test results
  - table4_index_statistics.tex: Index usage statistics
  - table5_comparative_analysis.tex: Comparative analysis

- `latex/`: LaTeX source files for tables

- `ieee_report.json`: Complete performance analysis report

## Usage

1. Include figures in your LaTeX document:
   ```latex
   \includegraphics[width=\columnwidth]{figures/figure1_performance_complexity.pdf}
   ```

2. Include tables:
   ```latex
   \input{tables/table1_query_classification.tex}
   ```

## Citation

If you use these metrics in your research, please cite:
```
@inproceedings{adni_kg_2024,
  title={Performance Evaluation of ADNI Knowledge Graph for Biomedical Data Querying},
  author={Your Name},
  booktitle={IEEE International Conference on Big Data},
  year={2024}
}
```
