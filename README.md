# Cloud-Deployable Webpage Knowledge Graph with Kùzu and yFiles

This project builds a **graph database** using [Kùzu](https://kuzudb.com/) to store and analyze connections between webpages. It now includes **production-ready cloud deployment** features (multi-worker serving via Gunicorn, asynchronous task processing with Celery + Redis, and full Docker + docker-compose support). Interactive visualizations are powered by [yFiles](https://www.yworks.com/products/yfiles).

Originally developed to explore interconnected ideas across curated webpages and to learn Kùzu graph database workflows, the project has evolved into a scalable, cloud-friendly tool for content relationship discovery and knowledge graph experimentation.

![image](https://github.com/user-attachments/assets/1c53a0d9-b26d-484a-b903-678864697fc0)

## Project Overview

**Key Value Propositions**

- **Discover Hidden Connections** — Finds latent relationships between webpages (e.g., shared keywords across different categories)
- **Production-Ready & Cloud Deployable** — Multi-worker Gunicorn serving, Celery background tasks, Redis broker, Dockerized architecture
- **Scalable Graph Foundation** — Flexible Kùzu schema designed to grow with larger datasets; supports automated ingestion pipelines
- **Educational Kùzu Playground** — Hands-on experience with schema design, Cypher queries, and graph database operations
- **Visual Insights** — Interactive yFiles visualizations make complex relationships easy to understand

The pipeline:
1. Fetches webpage content  
2. Processes it with Mistral 7B (via Ollama) for cleaning, categorization & keyword extraction  
3. Stores structured data in Kùzu  
4. Analyzes cross-category keyword overlaps  
5. Visualizes the graph with yFiles

## Features

- **Data Collection** — URL-based fetching with BeautifulSoup  
- **Intelligent Content Processing** — LLM-powered cleaning + category/keyword extraction (up to 3 keywords per page)  
- **Graph Storage** — Kùzu nodes: `Link`, `Category`, `Keyword`; relationships: `BELONGS_TO`, `HAS_KEYWORD`  
- **Interconnection Discovery** — Cypher queries to find keyword-sharing links in different categories  
- **Web Interface** — Flask app to add links, upload CSVs, view graph data  
- **Background Processing** — Celery + Redis handles long-running tasks (scraping, LLM calls, DB writes) asynchronously  
- **Production Deployment** — Gunicorn multi-worker server, Docker + docker-compose (web + worker + redis services)  
- **Visualization** — yFiles-powered interactive graph rendering with color/shape differentiation

## Improvements in Version 2 (Cloud-Ready Edition)

- **Asynchronous Task Queue** — Celery + Redis moves scraping, LLM calls, and DB writes to background workers  
- **Production Web Server** — Replaced Flask dev server with Gunicorn (multi-worker, configurable)  
- **Containerized Deployment** — Full Docker support + docker-compose.yml for local/cloud consistency  
- **LLM Content Cleaning** — Mistral 7B cleans scraped content more intelligently  
- **More Keywords** — Up to 3 keywords per page for richer interconnections  
- **Database Reliability** — Robust connection handling to avoid `db.lock` issues in containerized environments

## Quick Start (Local Development)

1. Clone the repo
2. Create & activate virtual environment
   ```bash
   python -m venv .venv
   source .venv/bin/activate    # Linux/macOS
   .venv\Scripts\activate       # Windows
