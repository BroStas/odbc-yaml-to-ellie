# ODBC Yaml to Ellie Importer

A modern Streamlit app to import database schema definitions from YAML (ODBC/ODCS style) into Ellie.ai, with ER diagram preview and rich metadata mapping.

## Features
- Upload a YAML file describing your database schema (ODCS/ODBC style)
- Visualize the schema as an interactive ER diagram (with PK, FK, unique, not null, and descriptions)
- Flexible handling of duplicate table names: add postfix, ignore, or combine attributes
- Select which tables to import (all or a custom subset)
- Maintains only valid relationships between selected tables
- Imports the model directly into Ellie.ai via their REST API
- Supports all major attribute metadata fields

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the app:**
   ```bash
   streamlit run app.py
   ```

3. **Usage:**
   - Upload your YAML file.
   - Enter your Ellie subdomain (slug) and API key, then press Connect.
   - Choose duplicate table handling and (optionally) select which tables to import.
   - Preview the ER diagram and adjust settings as needed.
   - Select the target folder, model name, and progress status, then click "Create Model in Ellie".

## Configuration
- **Ellie Subdomain (slug):** The subdomain for your Ellie.ai instance (e.g., `demoslug.trial` for `demoslug.trial.ellie.ai`).
- **Ellie API Key:** Your environment API key for Ellie.ai.
- **Duplicate Table Handling:**
  - *Add Postfix*: All tables included, duplicates get `_2`, `_3`, etc.
  - *Ignore Duplicates*: Only the first table with a given name is included.
  - *Combine Attributes*: All attributes from tables with the same name are merged.
- **Table Selection:**
  - By default, all tables are imported. Uncheck "Import all tables" to select a subset.
- **Progress Status:**
  - Work in Progress, Waiting for Approval, Approved, In Production

## Notes
- Only relationships between selected tables are imported.
- The diagram preview always matches the actual import payload.
- No data is stored server-side; all processing is local.

## License
MIT 