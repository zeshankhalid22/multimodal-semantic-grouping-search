Multi-Model AI  Product Retreival Pipeline (SHOPSYNC)
======================================================

Introduction
------------
SHOPSYNC is a small service for scraping e-commerce product pages (Amazon by default), extracting product metadata and images, generating fused CLIP-style embeddings, and serving a browsable API for search and product similarity. The project combines lightweight scraping utilities, an ingestion pipeline that writes to PostgreSQL (with pgvector for vector search), and a FastAPI web app to expose data and admin operations.

Features
--------
The project supports:
- Query-based search scraping to collect product card HTML.
- Detail-page scraping and image download.
- HTML-to-JSON extraction with attribute filtering.
- Ingestion into a Postgres table with vector signatures for similarity search.
- A FastAPI backend serving product galleries, detail endpoints and admin tasks.
- ML model integration using OpenCLIP for fused image+text embeddings.

Architecture
------------
Code is organized into `src/` (API, core logic, ML, DB) and `scripts/` (scrapers, extractors, CLI helpers). The FastAPI app mounts static and data directories and exposes both public and admin routers. The ingestion path validates records, generates embeddings via the model, and inserts into `product_inventory`. Postgres uses pgvector for approximate similarity (HNSW).

Dataset preparation
-------------------
Scraping happens in two phases: search (collect listing card HTML) and detail (visit product page and save full HTML). After scraping, run the extractor to produce an ingester-compatible JSON array and download images into a consistent `Data/` layout. 

Installation
------------
Install the project dependencies in a fresh virtual environment. The main extras include FastAPI, Selenium, pandas, requests, BeautifulSoup, psycopg2-binary and open-clip-torch.  You can install torch's cpu or gpu version based on your available hardware.

```
python3 -m venv .venv
.venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

pip install fastapi uvicorn python-dotenv selenium requests beautifulsoup4 lxml pandas psycopg2-binary pgvector open-clip-torch pillow numpy
```

Environment & configuration
---------------------------
Provide a `.env` file with DB credentials, `MODEL_PATH`, `IMAGE_ROOT`, and optional `BROWSER_BINARY`. Minimal example:
```/dev/null/.env#L1-4
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
MODEL_PATH=/path/to/checkpoint.pt
BROWSER_BINARY=/usr/bin/microsoft-edge
```
The app uses `BROWSER_BINARY` to start Edge for scraping; you must also install the matching `msedgedriver` and make it discoverable on PATH.

Setting up Database
---------------
The easiest way to run Postgres with pgvector is via the official/packaged Docker image. Run a local container and expose it on the default Postgres port:

```bash
docker run --name fyp-clip-pg \
  -p 5432:5432 \
  -e POSTGRES_USER=clipuser \
  -e POSTGRES_PASSWORD=clipsecret \
  -e POSTGRES_DB=clipdb \
  -d ghcr.io/ankane/pgvector:latest
```

Once the container is up, create the pgvector extension and the table the app expects. Connect with psql (or a GUI) and run:

```sql
-- enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- product_inventory table (512-d vector column)
CREATE TABLE IF NOT EXISTS product_inventory (
  id SERIAL PRIMARY KEY,
  platform TEXT,
  category TEXT,
  image_path TEXT,
  full_metadata JSONB,
  category_group VARCHAR(20),
  product_signature vector(512)
);
```

Create a vector index appropriate for your pgvector build. If you want the default IVFFLAT index:

```sql
-- IVFFLAT index (adjust lists based on dataset size)
CREATE INDEX IF NOT EXISTS idx_product_signature_ivfflat
  ON product_inventory USING ivfflat (product_signature vector_cosine_ops)
  WITH (lists = 100);
```

If your pgvector image supports HNSW and you prefer HNSW, create the HNSW index instead (syntax depends on your pgvector build). After creating the table and index run ANALYZE:

```sql
ANALYZE product_inventory;
```

Update your `.env` (or environment) with the DB credentials used above:

```
DB_NAME=clipdb
DB_USER=clipuser
DB_PASSWORD=clipsecret
DB_HOST=localhost
DB_PORT=5432
```

Running app
---------------
Before starting the web app, ensure the database is reachable and the `.env` contains `MODEL_PATH` (path to your model checkpoint) and `IMAGE_ROOT` (where images are stored). For a quick functional test (skip heavy DB and ML model initialisation) you can start without loading the model by setting `SKIP_STARTUP=1`:

```bash
# activate your virtualenv
.venv/bin/activate

# quick dev start (skips DB pool and ML model load)
export SKIP_STARTUP=1
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

For a full run (production/dev with model and DB initialised), ensure the DB is running, `MODEL_PATH` contains a valid checkpoint, and run without `SKIP_STARTUP`:

```bash
unset SKIP_STARTUP
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Notes:
- If the model is large, startup will take time while it loads into memory. Monitor logs for the "App ready" message.
- For scraping, ensure `BROWSER_BINARY` points to your Browser binary.
- If you need a systemd or containerised deployment, run the same commands inside your container image and point environment variables to production secrets.
