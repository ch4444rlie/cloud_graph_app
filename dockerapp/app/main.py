from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import kuzu
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
from ollama import Client
import re
import io
import csv
from celery import Celery

app = Flask(__name__, template_folder='templates')
app.secret_key = 'your_secret_key_here_change_me_please'  # ← CHANGE THIS in production!

# ────────────────────────────────────────────────────────────────────────────────
#  Celery configuration
# ────────────────────────────────────────────────────────────────────────────────

def make_celery(flask_app):
    celery_app = Celery(
        flask_app.import_name,
        backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0'),
        broker=os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
    )
    celery_app.conf.update(flask_app.config)
    return celery_app

celery = make_celery(app)

# ────────────────────────────────────────────────────────────────────────────────
#  Kùzu Database Initialization
# ────────────────────────────────────────────────────────────────────────────────

db_path = "/app/db/kuzu.db"
try:
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    conn.execute("CREATE NODE TABLE IF NOT EXISTS Link (url STRING, title STRING, raw_category STRING, suggested_category STRING, raw_content STRING, cleaned_content STRING, keywords STRING, category_explanation STRING, keyword_explanation STRING, PRIMARY KEY (url))")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Category (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE NODE TABLE IF NOT EXISTS Keyword (name STRING, PRIMARY KEY (name))")
    conn.execute("CREATE REL TABLE IF NOT EXISTS BELONGS_TO (FROM Link TO Category)")
    conn.execute("CREATE REL TABLE IF NOT EXISTS HAS_KEYWORD (FROM Link TO Keyword)")

    result = conn.execute("MATCH (l:Link) RETURN COUNT(l) AS cnt")
    count = result.get_next()[0]
    if count == 0:
        conn.execute("MERGE (:Link {url: 'https://kuzudb.com', title: 'Kùzu Database', raw_category: 'Database', suggested_category: 'Database', raw_content: 'Graph database platform', cleaned_content: 'Graph database platform', keywords: 'graph database', category_explanation: 'None', keyword_explanation: 'None'})")
        conn.execute("MERGE (:Link {url: 'https://example.com', title: 'Example Site', raw_category: 'Example', suggested_category: 'Example', raw_content: 'Example content', cleaned_content: 'Example content', keywords: 'example', category_explanation: 'None', keyword_explanation: 'None'})")
        conn.execute("MERGE (:Category {name: 'Database'})")
        conn.execute("MERGE (:Keyword {name: 'graph database'})")
        conn.execute("MATCH (l:Link {url: 'https://kuzudb.com'}), (c:Category {name: 'Database'}) MERGE (l)-[:BELONGS_TO]->(c)")
        conn.execute("MATCH (l:Link {url: 'https://example.com'}), (c:Category {name: 'Database'}) MERGE (l)-[:BELONGS_TO]->(c)")
        conn.execute("MATCH (l:Link {url: 'https://kuzudb.com'}), (k:Keyword {name: 'graph database'}) MERGE (l)-[:HAS_KEYWORD]->(k)")
        print("Kùzu database initialized with sample data")

except Exception as e:
    print(f"Error initializing Kùzu: {e}")
    raise

# ────────────────────────────────────────────────────────────────────────────────
#  Helper Functions
# ────────────────────────────────────────────────────────────────────────────────

def clean_content_with_ollama(content, ollama_host):
    if not content or len(content.strip()) < 100:
        return ""
    prompt = f"Extract the main meaningful content from the following text, up to 500 characters: {content[:2000]}"
    try:
        client = Client(host=ollama_host, timeout=20)
        response = client.chat(model='mistral:7b-instruct-v0.3-q4_0', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip()[:500]
    except Exception as e:
        print(f"Failed to clean content with Ollama: {e}")
        return content[:500]


def parse_category_and_keywords(response):
    categories = [
        'general tools', 'graph technologies', 'healthcare data', 'ai and legal systems',
        'federated search', 'organized crime analysis', 'beneficial ownership',
        'financial crime technology', 'corporate governance', 'power and utilities',
        'Social Media', 'Community Platform', 'Database', 'News', 'Blog', 'E-commerce',
        'International Economics/Policy', 'Data Analysis', 'Machine Learning / AI'
    ]
    category = 'Uncategorized'
    suggested_category = 'Uncategorized'
    keywords = ['none']

    if not response:
        return category, suggested_category, keywords

    match = re.search(r'Category:\s*([A-Za-z\s/]+)(?:\s*Keywords:|$)', response)
    if match:
        suggested_category = match.group(1).strip()

    for cat in categories:
        if cat.lower() == suggested_category.lower() or cat.lower() in response.lower():
            category = cat
            break

    match = re.search(r'Keywords:\s*([^.]+)', response)
    if match:
        keyword_str = match.group(1).strip()
        keywords = [k.strip() for k in keyword_str.split(',') if k.strip()][:3]

    if not keywords or keywords == ['none']:
        keywords = re.findall(r'\b[A-Z][a-zA-Z\s-]+\b', response)
        keywords = [k.strip() for k in keywords if len(k.split()) <= 2 and k.lower() not in category.lower() and k.lower() not in suggested_category.lower()][:3]

    return category, suggested_category, keywords if keywords else ['none']


def preload_metadata_csv():
    csv_path = "/app/links_with_metadata.csv"
    if not os.path.exists(csv_path):
        print("No links_with_metadata.csv found, skipping preload")
        return 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            required_fields = ['url', 'title', 'content', 'category', 'keyword', 'category_explanation', 'keyword_explanation']
            if not all(field in csv_reader.fieldnames for field in required_fields):
                print(f"links_with_metadata.csv missing required columns, skipping preload")
                return 0
            processed = 0
            for row in csv_reader:
                url = row['url'].strip()
                if not url:
                    continue
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                parsed_url = urllib.parse.urlparse(url)
                normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}".rstrip('/')
                url = urllib.parse.quote(normalized_url, safe=':/?=&')
                result = conn.execute("MATCH (l:Link {url: $url}) RETURN l.url", {"url": url})
                if result.has_next():
                    continue
                title = row['title'].strip() or url
                raw_content = row['content'][:5000].strip() if row['content'] else ""
                cleaned_content = raw_content[:500]
                raw_category = row['category'].strip() or 'Uncategorized'
                suggested_category = raw_category
                category_explanation = row['category_explanation'].strip() or 'None'
                keyword_explanation = row['keyword_explanation'].strip() or 'None'
                keywords = [k.strip() for k in row['keyword'].split(',') if k.strip()][:3] if row['keyword'] else ['none']
                category, _, _ = parse_category_and_keywords(f"Category: {raw_category}")
                keywords_str = ', '.join(keywords) if keywords and keywords != ['none'] else 'none'

                conn.execute(
                    "MERGE (:Link {url: $url, title: $title, raw_category: $raw_category, suggested_category: $suggested_category, "
                    "raw_content: $raw_content, cleaned_content: $cleaned_content, keywords: $keywords, "
                    "category_explanation: $category_explanation, keyword_explanation: $keyword_explanation})",
                    {
                        "url": url, "title": title, "raw_category": raw_category, "suggested_category": suggested_category,
                        "raw_content": raw_content, "cleaned_content": cleaned_content, "keywords": keywords_str,
                        "category_explanation": category_explanation, "keyword_explanation": keyword_explanation
                    }
                )
                conn.execute("MERGE (c:Category {name: $name})", {"name": category})
                conn.execute("MATCH (l:Link {url: $url}), (c:Category {name: $name}) MERGE (l)-[:BELONGS_TO]->(c)", {"url": url, "name": category})
                for keyword in keywords:
                    if keyword != 'none':
                        conn.execute("MERGE (k:Keyword {name: $name})", {"name": keyword})
                        conn.execute("MATCH (l:Link {url: $url}), (k:Keyword {name: $name}) MERGE (l)-[:HAS_KEYWORD]->(k)", {"url": url, "name": keyword})
                processed += 1
            print(f"Preloaded {processed} links from CSV")
            return processed
    except Exception as e:
        print(f"Error preloading CSV: {e}")
        return 0


def save_to_csv():
    csv_path = "/app/links_with_metadata.csv"
    try:
        result = conn.execute("MATCH (l:Link) RETURN l.url, l.title, l.raw_content, l.raw_category, l.keywords, l.category_explanation, l.keyword_explanation")
        links = [{
            "url": row[0],
            "title": row[1] or '',
            "content": row[2] or '',
            "category": row[3] or '',
            "keyword": row[4] or '',
            "category_explanation": row[5] or '',
            "keyword_explanation": row[6] or ''
        } for row in result]
        with open(csv_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['url', 'title', 'content', 'category', 'keyword', 'category_explanation', 'keyword_explanation'])
            writer.writeheader()
            writer.writerows(links)
        print(f"Saved {len(links)} links to CSV")
    except Exception as e:
        print(f"Error saving CSV: {e}")

# ────────────────────────────────────────────────────────────────────────────────
#  Celery Task – Process single link addition
# ────────────────────────────────────────────────────────────────────────────────

@celery.task
def process_single_link(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        parsed_url = urllib.parse.urlparse(url)
        normalized_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}".rstrip('/')
        url = urllib.parse.quote(normalized_url, safe=':/?=&')

        result = conn.execute("MATCH (l:Link {url: $url}) RETURN l.url", {"url": url})
        if result.has_next():
            return f"Skipped (already exists): {url}"

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            title = soup.title.string.strip() if soup.title else url
            text_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            raw_content = ' '.join(el.get_text(strip=True) for el in text_elements)[:5000]
        except Exception as e:
            print(f"Fetch failed {url}: {e}")
            title = url
            raw_content = "Failed to fetch content"

        ollama_host = os.getenv('OLLAMA_HOST', 'http://host.docker.internal:11434')
        cleaned_content = clean_content_with_ollama(raw_content, ollama_host)

        try:
            client = Client(host=ollama_host, timeout=20)
            prompt_content = cleaned_content or raw_content[:1000]
            prompt = (
                f"Given the webpage title '{title}' and the following content excerpt: '{prompt_content[:1000]}', "
                f"suggest a single category (e.g., Social Media, Database, News) and up to three keywords (1-2 words each)."
            )
            response = client.chat(model='mistral:7b-instruct-v0.3-q4_0', messages=[{'role': 'user', 'content': prompt}])
            raw_response = response['message']['content'].strip()
            category, suggested_category, keywords = parse_category_and_keywords(raw_response)
            keywords_str = ', '.join(keywords) if keywords and keywords != ['none'] else 'none'
            cat_exp = kw_exp = 'Generated by LLM'
        except Exception as e:
            print(f"Ollama failed for {url}: {e}")
            category = suggested_category = 'Uncategorized'
            keywords = ['none']
            keywords_str = 'none'
            cat_exp = kw_exp = 'Ollama connection failure'

        conn.execute(
            "MERGE (:Link {url: $url, title: $title, raw_category: $raw_category, suggested_category: $suggested_category, "
            "raw_content: $raw_content, cleaned_content: $cleaned_content, keywords: $keywords, "
            "category_explanation: $cat_exp, keyword_explanation: $kw_exp})",
            {
                "url": url, "title": title, "raw_category": raw_response or 'Failed', "suggested_category": suggested_category,
                "raw_content": raw_content, "cleaned_content": cleaned_content, "keywords": keywords_str,
                "cat_exp": cat_exp, "kw_exp": kw_exp
            }
        )
        conn.execute("MERGE (c:Category {name: $name})", {"name": category})
        conn.execute("MATCH (l:Link {url: $url}), (c:Category {name: $name}) MERGE (l)-[:BELONGS_TO]->(c)", {"url": url, "name": category})

        for kw in keywords:
            if kw != 'none':
                conn.execute("MERGE (k:Keyword {name: $name})", {"name": kw})
                conn.execute("MATCH (l:Link {url: $url}), (k:Keyword {name: $name}) MERGE (l)-[:HAS_KEYWORD]->(k)", {"url": url, "name": kw})

        save_to_csv()
        return f"Added: {url} → {category} ({keywords})"
    except Exception as e:
        return f"Error processing {url}: {str(e)}"


# ────────────────────────────────────────────────────────────────────────────────
#  Routes
# ────────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
def index():
    try:
        result = conn.execute("MATCH (l:Link)-[:BELONGS_TO]->(c:Category) RETURN l.url, l.title, c.name, l.raw_category, l.suggested_category, l.raw_content, l.cleaned_content, l.keywords, l.category_explanation, l.keyword_explanation")
        links = [{
            "url": row[0],
            "title": row[1],
            "category": row[2],
            "raw_category": row[3],
            "suggested_category": row[4] or 'None',
            "raw_content": row[5] or 'Failed to fetch',
            "cleaned_content": row[6] or 'Failed to clean',
            "keywords": row[7] or 'none',
            "category_explanation": row[8] or 'None',
            "keyword_explanation": row[9] or 'None'
        } for row in result]

        result = conn.execute("""
            MATCH (l1:Link)-[:HAS_KEYWORD]->(k:Keyword)<-[:HAS_KEYWORD]-(l2:Link),
                  (l1)-[:BELONGS_TO]->(c1:Category), (l2)-[:BELONGS_TO]->(c2:Category)
            WHERE l1.url <> l2.url AND c1.name <> c2.name
            RETURN l1.url, l2.url, k.name, c1.name, c2.name
        """)
        interconnections = [{
            "link1": r[0], "link2": r[1], "keyword": r[2],
            "category1": r[3], "category2": r[4]
        } for r in result]

        return render_template("index.html", links=links, interconnections=interconnections)
    except Exception as e:
        print(f"Error in index: {e}")
        return f"Error: {str(e)}", 500


@app.route("/add_link", methods=["POST"])
def add_link():
    url = request.form.get("url")
    if not url:
        flash("No URL provided")
        return redirect(url_for("index"))

    process_single_link.delay(url)
    flash("Link queued for background processing")
    return redirect(url_for("index"))




if __name__ == "__main__":
    mode = os.getenv("APP_MODE", "development").lower()
    if mode == "production":
        print("Production mode — started by Gunicorn")
    else:
        preload_metadata_csv()
        app.run(host="0.0.0.0", port=5000, debug=True)