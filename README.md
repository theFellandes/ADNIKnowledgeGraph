# ADNI Knowledge Graph System

## Prerequisites

1. **Neo4j Database**
   - Ensure Docker is installed and running
   - Start Neo4j using the provided docker-compose.yml:
   ```bash
   docker-compose up -d
   ```
   - Neo4j will be available at http://localhost:7474
   - Default credentials: neo4j / your_password

2. **Python Environment**
   - Python 3.8 or higher
   - Virtual environment recommended

## Installation

1. **Clone the repository** (if not already done)

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create configuration files**
   - Copy `config.yaml` to your project root
   - Update paths in `config.yaml` to match your system
   - Create `.streamlit/secrets.toml` for the UI

## Running the Pipeline

### Option 1: Run with configuration file
```bash
python pipeline.py --config config.yaml
```

### Option 2: Run with command-line arguments
```bash
python pipeline.py \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password your_password \
  --base-path "D:/Programming/Python/ADNIKnowledgeGraph/inputs" \
  --clear-database
```

### Option 3: Run specific steps only
```bash
# Skip image processing (useful for testing)
python pipeline.py --config config.yaml --skip-image-processing

# Run only database setup and table loading
python pipeline.py --config config.yaml \
  --skip-patient-creation \
  --skip-family-extraction \
  --skip-image-processing \
  --skip-findings-extraction \
  --skip-batch-insertion \
  --skip-relationship-creation
```

## Running the Streamlit UI

1. **Ensure Neo4j is running and populated with data**

2. **Update Streamlit secrets**
   - Edit `.streamlit/secrets.toml` with your Neo4j credentials

3. **Launch the Streamlit app**
   ```bash
   streamlit run streamlit_app.py
   ```

4. **Access the UI**
   - Open your browser to http://localhost:8501
   - The UI will automatically connect to Neo4j

## UI Features

- **Dashboard**: Overview statistics and visualizations
- **Patient Explorer**: Search and view individual patient data
- **Cognitive Assessments**: Analyze cognitive test results over time
- **Biomarkers**: Explore CSF and plasma biomarker trends
- **Imaging**: View imaging studies and brain volumetric data
- **Family Relationships**: Visualize family history networks
- **Advanced Query**: Execute custom Cypher queries
- **Data Export**: Export data in CSV or JSON format

## Troubleshooting

### Neo4j Connection Issues
- Verify Neo4j is running: `docker ps`
- Check Neo4j logs: `docker logs adni-kg-dev`
- Ensure correct password in config files

### Memory Issues
- For large datasets, increase Neo4j heap memory in docker-compose.yml
- Reduce batch sizes in config.yaml
- Set `store_image_blobs: false` to skip storing image data

### Image Processing Issues
- Verify image paths in config.yaml are correct
- Check file permissions
- For testing, use `--skip-image-processing` flag

### Streamlit Issues
- Clear Streamlit cache: `streamlit cache clear`
- Check console for error messages
- Verify Neo4j has data before running UI

## Performance Tips

1. **Initial Load**
   - First run with `clear_database: true`
   - Subsequent runs with `clear_database: false`

2. **Large Datasets**
   - Process images separately with reduced workers
   - Use batch processing for better memory management

3. **Quick Testing**
   - Skip image processing for faster testing
   - Load only specific table categories

## Data Requirements

Ensure you have the following ADNI data structure:
```
inputs/
├── Tables/          # CSV files (PTDEMOG.csv, MMSE.csv, etc.)
├── Updated/         # Converted MRI images
├── Updated_PET/     # Converted PET images
├── Images/          # Original MRI DICOM files (optional)
└── PET/            # Original PET DICOM files (optional)
```