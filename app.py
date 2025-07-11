"""
B2B Sales Intelligence Platform - Flask Backend
Integrates AI Link Scraper with B2B Vault functionality
"""

import os
import sys
import json
import csv
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import pandas as pd
from pathlib import Path
import threading
import time
import logging
import subprocess

# Add the src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'b2bvault-repo'))

# Import B2B Vault scraper
try:
    from b2b_vault_integration import B2BVaultIntegration
    B2B_VAULT_AVAILABLE = True
except ImportError as e:
    print(f"B2B Vault integration not available: {e}")
    B2B_VAULT_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# Configuration
SCRAPED_LINKS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scraped_links')
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'sales_intelligence.db')
B2B_VAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'b2bvault-repo', 'scraped_data')

# Global variables for B2B Vault scraping status
b2b_scraping_status = {
    'is_running': False,
    'progress': 0,
    'current_step': '',
    'results': None,
    'error': None,
    'log_messages': []
}

# Available B2B Vault tags
B2B_TAGS = [
    "All", "Content Marketing", "Demand Generation", "ABM & GTM", 
    "Paid Marketing", "Marketing Ops", "Event Marketing", "AI", 
    "Product Marketing", "Sales", "General", "Affiliate & Partnerships", 
    "Copy & Positioning"
]

class SalesIntelligenceDB:
    """Database manager for the sales intelligence platform"""
    
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # AI Links table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                domain TEXT,
                content TEXT,
                content_type TEXT,
                category TEXT,
                word_count INTEGER,
                slack_user TEXT,
                date_scraped TEXT,
                date_shared TEXT,
                brief_description TEXT,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Add brief_description column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE ai_links ADD COLUMN brief_description TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # B2B Vault articles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS b2b_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                publisher TEXT,
                category TEXT,
                content TEXT,
                summary TEXT,
                word_count INTEGER,
                date_published TEXT,
                date_scraped TEXT,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_ai_links(self, limit=100):
        """Get AI links from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM ai_links 
            WHERE status = 'active' 
            ORDER BY date_scraped DESC 
            LIMIT ?
        ''', (limit,))
        
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
    def add_ai_link(self, link_data):
        """Add an AI link to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO ai_links 
            (title, url, domain, content, content_type, category, word_count, slack_user, date_scraped, date_shared, brief_description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            link_data.get('title', ''),
            link_data.get('url', ''),
            link_data.get('domain', ''),
            link_data.get('content', ''),
            link_data.get('content_type', ''),
            link_data.get('category', ''),
            link_data.get('word_count', 0),
            link_data.get('slack_user', ''),
            link_data.get('date_scraped', datetime.now().isoformat()),
            link_data.get('date_shared', ''),
            link_data.get('brief_description', '')
        ))
        
        conn.commit()
        conn.close()
    
    def get_b2b_articles(self, limit=100, category=None):
        """Get B2B Vault articles from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT * FROM b2b_articles 
            WHERE status = 'active'
        '''
        params = []
        
        if category and category != 'All':
            query += ' AND category = ?'
            params.append(category)
        
        query += ' ORDER BY date_scraped DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results
    
    def add_b2b_article(self, article_data):
        """Add a B2B Vault article to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO b2b_articles 
            (title, url, publisher, category, content, summary, word_count, date_scraped)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            article_data.get('title', ''),
            article_data.get('url', ''),
            article_data.get('publisher', ''),
            article_data.get('category', ''),
            article_data.get('content', ''),
            article_data.get('summary', ''),
            article_data.get('word_count', 0),
            article_data.get('date_scraped', datetime.now().isoformat())
        ))
        
        conn.commit()
        conn.close()
    
    def search_articles(self, query, article_type='all'):
        """Search articles by query"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        search_query = f"%{query}%"
        
        if article_type == 'ai_links':
            cursor.execute('''
                SELECT * FROM ai_links 
                WHERE status = 'active' 
                AND (title LIKE ? OR content LIKE ? OR category LIKE ?)
                ORDER BY date_scraped DESC
            ''', (search_query, search_query, search_query))
        elif article_type == 'b2b_vault':
            cursor.execute('''
                SELECT * FROM b2b_articles 
                WHERE status = 'active' 
                AND (title LIKE ? OR content LIKE ? OR summary LIKE ? OR category LIKE ?)
                ORDER BY date_scraped DESC
            ''', (search_query, search_query, search_query, search_query))
        else:
            # Search both tables
            cursor.execute('''
                SELECT 'ai_links' as source, * FROM ai_links 
                WHERE status = 'active' 
                AND (title LIKE ? OR content LIKE ? OR category LIKE ?)
                UNION ALL
                SELECT 'b2b_vault' as source, id, title, url, publisher as domain, 
                       content, category as content_type, category, word_count, 
                       '', date_published as date_shared, date_scraped, status
                FROM b2b_articles 
                WHERE status = 'active' 
                AND (title LIKE ? OR content LIKE ? OR summary LIKE ? OR category LIKE ?)
                ORDER BY date_scraped DESC
            ''', (search_query, search_query, search_query, 
                  search_query, search_query, search_query, search_query))
        
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results

class B2BVaultManager:
    """Manager for B2B Vault scraping operations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
    
    def start_scraping(self, tags=['All'], max_articles_per_tag=50):
        """Start B2B Vault scraping in background thread"""
        if b2b_scraping_status['is_running']:
            return False, "Scraping is already running"
        
        # Check if we're in a serverless environment
        is_serverless = os.environ.get('VERCEL') or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER')
        
        if is_serverless:
            return False, "Live scraping is not available in serverless deployments. Demo articles are automatically loaded on startup."
        
        def scraping_thread():
            try:
                b2b_scraping_status['is_running'] = True
                b2b_scraping_status['progress'] = 0
                b2b_scraping_status['current_step'] = 'Initializing B2B Vault scraper...'
                b2b_scraping_status['error'] = None
                b2b_scraping_status['log_messages'] = []
                
                # Import and initialize B2B Vault scraper
                if not B2B_VAULT_AVAILABLE:
                    raise Exception("B2B Vault scraper not available")
                
                b2b_scraping_status['current_step'] = 'Starting scraper...'
                b2b_scraping_status['progress'] = 10
                
                # Initialize the B2B Vault integration
                integration = B2BVaultIntegration()
                
                b2b_scraping_status['current_step'] = 'Scraping articles...'
                b2b_scraping_status['progress'] = 30
                
                # Scrape real articles
                all_articles = scrape_b2b_vault()
                
                b2b_scraping_status['current_step'] = 'Processing articles...'
                b2b_scraping_status['progress'] = 75
                
                b2b_scraping_status['current_step'] = 'Saving to database...'
                b2b_scraping_status['progress'] = 90
                
                # Save to database
                for article in all_articles:
                    self.db.add_b2b_article(article)
                
                b2b_scraping_status['current_step'] = 'Complete!'
                b2b_scraping_status['progress'] = 100
                b2b_scraping_status['results'] = {
                    'total_articles': len(all_articles),
                    'tags_scraped': tags,
                    'timestamp': datetime.now().isoformat()
                }
                
            except Exception as e:
                self.logger.error(f"B2B Vault scraping error: {e}")
                b2b_scraping_status['error'] = str(e)
                b2b_scraping_status['current_step'] = 'Error occurred'
            finally:
                b2b_scraping_status['is_running'] = False
        
        thread = threading.Thread(target=scraping_thread)
        thread.daemon = True
        thread.start()
        
        return True, "Scraping started successfully"
    
    def get_scraping_status(self):
        """Get current scraping status"""
        return b2b_scraping_status.copy()
    
    def load_cached_data(self):
        """Load cached B2B Vault data from files"""
        try:
            # Look for cached data in the B2B Vault data directory
            data_files = []
            if os.path.exists(B2B_VAULT_DATA_DIR):
                for file in os.listdir(B2B_VAULT_DATA_DIR):
                    if file.endswith('.json'):
                        data_files.append(os.path.join(B2B_VAULT_DATA_DIR, file))
            
            if not data_files:
                return []
            
            # Load the most recent data file
            latest_file = max(data_files, key=os.path.getctime)
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            
            # Save to database
            for article in articles:
                self.db.add_b2b_article(article)
            
            return articles
            
        except Exception as e:
            self.logger.error(f"Error loading cached B2B Vault data: {e}")
            return []

def generate_expanded_summary(content, title, category):
    """Generate a more detailed 4-5 sentence summary from article content"""
    # Extract key sentences from the content
    sentences = content.split('. ')
    
    # Create a 4-5 sentence summary based on the content
    if len(sentences) >= 4:
        # Use the first few sentences and add category-specific insights
        summary_parts = []
        
        # Add the main point
        summary_parts.append(sentences[0].strip())
        
        # Add supporting details
        if len(sentences) > 1:
            summary_parts.append(sentences[1].strip())
        
        # Add category-specific insights
        if category == "AI":
            summary_parts.append("This represents a significant shift in how AI technology is being adopted across B2B marketing and sales operations.")
        elif category == "Sales":
            summary_parts.append("Sales teams implementing these strategies report measurable improvements in conversion rates and deal velocity.")
        elif category == "ABM & GTM":
            summary_parts.append("Account-based marketing approaches like this require alignment between sales and marketing teams for maximum effectiveness.")
        elif category == "Content Marketing":
            summary_parts.append("Content marketing strategies must evolve to meet changing buyer expectations and consumption patterns.")
        else:
            summary_parts.append("This approach demonstrates the importance of strategic thinking in modern B2B marketing.")
        
        # Add implementation insight
        summary_parts.append("Companies that adopt these methods early often gain significant competitive advantages in their markets.")
        
        # Add future outlook
        summary_parts.append("The trend toward more sophisticated, data-driven approaches will likely accelerate as technology continues to evolve.")
        
        return '. '.join(summary_parts[:5]) + '.'
    else:
        # Fallback for short content
        return content[:200] + "..." if len(content) > 200 else content

def scrape_b2b_vault():
    """Scrape real articles from B2B Vault website"""
    try:
        import requests
        from bs4 import BeautifulSoup
        import re
        from urllib.parse import urljoin, urlparse
        
        articles = []
        base_url = 'https://www.theb2bvault.com'
        
        print("🔍 Scraping B2B Vault website for real articles...")
        
        # Scrape the main homepage where articles are displayed (not any specific tab)
        main_url = base_url  # This should be just the homepage: https://www.theb2bvault.com
        print(f"📡 Requesting URL: {main_url}")
        
        response = requests.get(main_url, timeout=15)
        response.raise_for_status()
        
        # Check if we were redirected
        if response.url != main_url:
            print(f"⚠️  Redirected from {main_url} to {response.url}")
        else:
            print(f"✅ Successfully loaded homepage: {response.url}")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check if we're on the right page by looking for homepage indicators
        page_title = soup.find('title')
        if page_title:
            print(f"📄 Page title: {page_title.get_text().strip()}")
        
        # Look for navigation elements to confirm we're on the homepage
        nav_elements = soup.find_all('a', href=True)
        sales_links = [link for link in nav_elements if 'sales' in link.get('href', '').lower()]
        if sales_links:
            print(f"🔍 Found {len(sales_links)} navigation links with 'sales' - confirming we're on main page with all tabs")
        
        # Check for tab indicators in the page
        tab_indicators = soup.find_all(string=re.compile(r'(All|Content Marketing|Sales|AI|Product Marketing)', re.IGNORECASE))
        if tab_indicators:
            print(f"🏷️  Found tab indicators: {tab_indicators[:5]}")  # Show first 5
        
        print(f"📊 Total page content length: {len(soup.get_text())} characters")
        
        # Find article sections - based on the actual HTML structure
        # Articles are structured as text blocks with "Read Full Article" and "Read Summary" links
        article_sections = []
        
        # Look for patterns that indicate article content
        # The pattern seems to be category/publisher info followed by article content and links
        potential_articles = []
        
        # Find all text blocks that contain "Read Full Article" or "Read Summary"
        read_full_links = soup.find_all('a', string=re.compile(r'Read Full Article', re.IGNORECASE))
        read_summary_links = soup.find_all('a', string=re.compile(r'Read Summary', re.IGNORECASE))
        
        print(f"📄 Found {len(read_full_links)} 'Read Full Article' links")
        print(f"📄 Found {len(read_summary_links)} 'Read Summary' links")
        
        # Process "Read Full Article" links to extract article information
        for link in read_full_links:
            try:
                # Find the parent section that contains the article
                parent = link.parent
                
                # Look for the article container by walking up the DOM
                article_container = parent
                for _ in range(5):  # Try up to 5 levels up
                    if article_container is None:
                        break
                    
                    # Check if this container seems to have article content
                    container_text = article_container.get_text()
                    if len(container_text) > 100:  # Substantial content
                        break
                    
                    article_container = article_container.parent
                
                if article_container:
                    potential_articles.append({
                        'container': article_container,
                        'read_full_link': link.get('href'),
                        'link_element': link
                    })
            except Exception as e:
                print(f"    ❌ Error processing Read Full Article link: {e}")
                continue
        
        # Also look for "Read Summary" links and match them to articles
        summary_links_dict = {}
        for link in read_summary_links:
            try:
                href = link.get('href')
                if href:
                    summary_links_dict[href] = link
            except:
                continue
        
        print(f"📄 Found {len(potential_articles)} potential article containers")
        
        # Use the potential articles as our article_cards
        article_cards = potential_articles
        
        # Process each article
        for i, article_data in enumerate(article_cards[:50]):  # Limit to 50 articles
            try:
                print(f"📖 Processing article {i+1}/{min(len(article_cards), 50)}")
                
                container = article_data['container']
                read_full_link = article_data['read_full_link']
                
                # Get the full text content from the container
                container_text = container.get_text()
                
                # Extract title - use multiple strategies to find article titles
                title = ""
                text_blocks = container_text.split('\n')
                
                # Strategy 1: Look for title in structured patterns around the links
                # Find the position of the "Read Full Article" text to locate nearby title
                link_text_blocks = []
                for i, block in enumerate(text_blocks):
                    block = block.strip()
                    if 'read full article' in block.lower():
                        # Look at surrounding blocks for title
                        start_idx = max(0, i - 3)
                        end_idx = min(len(text_blocks), i + 1)
                        link_text_blocks.extend(text_blocks[start_idx:end_idx])
                        break
                
                # Strategy 2: Look for title patterns in the container
                excluded_patterns = [
                    'read full article', 'read summary', 'published by', 'check the video',
                    'see the exact process', 'http', 'www.', '.com', '.org', '.io',
                    'utm_source', 'tldrmarketing', 'newsletter', 'subscribe'
                ]
                
                # First try to find title in the blocks around the link
                for block in link_text_blocks:
                    block = block.strip()
                    if (len(block) > 15 and len(block) < 300 and
                        not any(pattern in block.lower() for pattern in excluded_patterns) and
                        not block.lower().startswith(('all', 'content marketing', 'ai', 'sales', 'general'))):
                        title = block
                        break
                
                # Strategy 3: Look for any substantial text block that could be a title
                if not title:
                    for block in text_blocks:
                        block = block.strip()
                        if (len(block) > 15 and len(block) < 300 and
                            not any(pattern in block.lower() for pattern in excluded_patterns) and
                            not block.lower().startswith(('all', 'content marketing', 'ai', 'sales', 'general')) and
                            # Make sure it's not just category text
                            not re.match(r'^[A-Z\s&;]+Published by:', block)):
                            title = block
                            break
                
                # Strategy 4: Look for text that comes after category/publisher info
                if not title:
                    for i, block in enumerate(text_blocks):
                        block = block.strip()
                        if 'published by:' in block.lower() and i + 1 < len(text_blocks):
                            next_block = text_blocks[i + 1].strip()
                            if (len(next_block) > 15 and len(next_block) < 300 and
                                not any(pattern in next_block.lower() for pattern in excluded_patterns)):
                                title = next_block
                                break
                
                # Strategy 5: Look for text between category and description
                if not title:
                    # Find patterns like "Category Published by: Publisher TITLE Description"
                    full_text = ' '.join(text_blocks)
                    title_pattern = r'Published by:\s*[^\.]+?\s+([^\.]{20,200}?)\s+[A-Z][a-z]'
                    match = re.search(title_pattern, full_text, re.DOTALL)
                    if match:
                        potential_title = match.group(1).strip()
                        if not any(pattern in potential_title.lower() for pattern in excluded_patterns):
                            title = potential_title
                
                # Strategy 6: Extract from URL if all else fails
                if not title and read_full_link:
                    # Extract a reasonable title from the URL
                    url_path = read_full_link.split('/')[-1]
                    if url_path:
                        title = url_path.replace('-', ' ').replace('_', ' ').title()
                        title = title.split('?')[0]  # Remove query parameters
                        # Clean up common URL artifacts
                        title = re.sub(r'\.(html?|php|aspx?)$', '', title, re.IGNORECASE)
                
                # Strategy 7: As a last resort, use a generic title based on the URL domain
                if not title and read_full_link:
                    from urllib.parse import urlparse
                    domain = urlparse(read_full_link).netloc
                    title = f"Article from {domain.replace('www.', '')}"
                
                if not title:
                    print(f"    ❌ No title found for article {i+1}")
                    continue
                
                # Clean the title
                title = re.sub(r'\s+', ' ', title).strip()
                
                # Find the "Read Summary" link for this article
                read_summary_link = None
                for summary_href, summary_link in summary_links_dict.items():
                    if summary_link.parent == article_data['link_element'].parent:
                        read_summary_link = summary_href
                        break
                
                # If we can't find a matching summary link, try to find one nearby
                if not read_summary_link:
                    summary_links_nearby = container.find_all('a', string=re.compile(r'Read Summary', re.IGNORECASE))
                    if summary_links_nearby:
                        read_summary_link = summary_links_nearby[0].get('href')
                
                # Extract content/description from the container
                # Look for descriptive text that's not a title or link
                summary = ""
                
                # Try to find the description that comes after the title
                title_found = False
                for block in text_blocks:
                    block = block.strip()
                    
                    # Skip until we find something that looks like our title
                    if not title_found and title and title.lower() in block.lower():
                        title_found = True
                        continue
                    
                    # Look for a good description block
                    if (title_found and len(block) > 50 and len(block) < 500 and 
                        block != title and
                        not any(pattern in block.lower() for pattern in excluded_patterns)):
                        summary = block
                        break
                
                # If we didn't find a summary using the title method, try a different approach
                if not summary:
                    for block in text_blocks:
                        block = block.strip()
                        if (len(block) > 50 and len(block) < 500 and 
                            block != title and
                            not any(pattern in block.lower() for pattern in excluded_patterns)):
                            summary = block
                            break
                
                # Extract category and publisher info
                category = "General"
                publisher = "B2B Vault"
                
                # Look for category information in the text
                category_keywords = {
                    'AI': ['ai', 'artificial intelligence', 'machine learning', 'chatgpt', 'llm'],
                    'Sales': ['sales', 'selling', 'revenue', 'deals', 'prospects'],
                    'Content Marketing': ['content', 'marketing', 'seo', 'blog', 'social media'],
                    'ABM & GTM': ['abm', 'account based', 'go-to-market', 'gtm'],
                    'Demand Generation': ['demand', 'leads', 'generation', 'pipeline'],
                    'Product Marketing': ['product', 'pmm', 'positioning', 'messaging'],
                    'Paid Marketing': ['paid', 'ads', 'advertising', 'ppc'],
                    'Marketing Ops': ['ops', 'operations', 'attribution', 'analytics']
                }
                
                text_to_analyze = (title + " " + summary).lower()
                for cat, keywords in category_keywords.items():
                    if any(keyword in text_to_analyze for keyword in keywords):
                        category = cat
                        break
                
                # Try to extract publisher from text
                publisher_patterns = [
                    r'Published by:\s*([^\\n]+)',
                    r'by\s+([A-Za-z\s]+)',
                    r'from\s+([A-Za-z\s]+)'
                ]
                
                for pattern in publisher_patterns:
                    match = re.search(pattern, container_text, re.IGNORECASE)
                    if match:
                        potential_publisher = match.group(1).strip()
                        if len(potential_publisher) > 2 and len(potential_publisher) < 50:
                            publisher = potential_publisher
                            break
                
                # Convert relative URLs to absolute
                if read_full_link and not read_full_link.startswith('http'):
                    read_full_link = urljoin(base_url, read_full_link)
                
                if read_summary_link and not read_summary_link.startswith('http'):
                    read_summary_link = urljoin(base_url, read_summary_link)
                
                # Try to scrape full content if we have a link
                content = summary  # Default to summary
                if read_full_link:
                    try:
                        print(f"    📖 Scraping full content from: {read_full_link}")
                        article_response = requests.get(read_full_link, timeout=10)
                        if article_response.status_code == 200:
                            article_soup = BeautifulSoup(article_response.content, 'html.parser')
                            
                            # Extract full content
                            content_selectors = [
                                '.content', '.post-content', '.article-content', 
                                '.entry-content', '.main-content', 'main', 
                                '.text-content', 'article', 'body'
                            ]
                            
                            for selector in content_selectors:
                                content_elem = article_soup.select_one(selector)
                                if content_elem:
                                    # Remove script and style elements
                                    for script in content_elem(["script", "style"]):
                                        script.decompose()
                                    full_content = content_elem.get_text().strip()
                                    if len(full_content) > 200:  # Only use if substantial content
                                        content = full_content
                                        break
                    except Exception as e:
                        print(f"    ⚠️  Could not scrape full content: {e}")
                
                # Clean up content
                content = re.sub(r'\s+', ' ', content)
                content = content[:2000]  # Limit content length
                
                # Calculate word count
                word_count = len(content.split()) if content else 0
                
                # Create article data
                article_data = {
                    'title': title,
                    'url': read_full_link or read_summary_link or f"{base_url}#{i+1}",
                    'publisher': publisher,
                    'category': category,
                    'content': content,
                    'summary': summary if summary else content[:200] + "..." if len(content) > 200 else content,
                    'word_count': word_count,
                    'date_scraped': datetime.now().isoformat(),
                    'read_full_link': read_full_link,
                    'read_summary_link': read_summary_link
                }
                
                articles.append(article_data)
                print(f"    ✅ Added: {title[:60]}... ({word_count} words)")
                
            except Exception as e:
                print(f"    ❌ Error processing article {i+1}: {e}")
                continue
        
        # Report what we actually found - no fake articles
        if len(articles) == 0:
            print("❌ No articles were successfully scraped from B2B Vault website")
            print("   This could be due to:")
            print("   - Website structure changes")
            print("   - Network connectivity issues") 
            print("   - Anti-scraping protection")
            print("   - Invalid selectors or parsing logic")
        elif len(articles) < 10:
            print(f"⚠️  Only found {len(articles)} articles (fewer than expected)")
            print("   The website may have limited content or the scraping logic needs adjustment")
        else:
            print(f"✅ Successfully found {len(articles)} articles")
        
        # Generate expanded summaries for all articles
        for article in articles:
            article['summary'] = generate_expanded_summary(
                article['content'], 
                article['title'], 
                article['category']
            )
        
        print(f"✅ Successfully scraped {len(articles)} real B2B Vault articles")
        return articles
        
    except Exception as e:
        print(f"❌ Error scraping B2B Vault: {e}")
        print("   Unable to scrape articles from the website.")
        print("   Please check:")
        print("   - Internet connectivity")
        print("   - Website availability")
        print("   - Scraping selectors and logic")
        return []

def load_scraped_links():
    """Load scraped links from CSV files with proper parsing"""
    try:
        # Find the most recent scraped links directory
        if not os.path.exists(SCRAPED_LINKS_DIR):
            print(f"Scraped links directory not found: {SCRAPED_LINKS_DIR}")
            return []
        
        # Get all export directories
        export_dirs = [d for d in os.listdir(SCRAPED_LINKS_DIR) if d.startswith('AI_Links_Export_')]
        if not export_dirs:
            print("No export directories found")
            return []
        
        # Sort by date and get the most recent
        export_dirs.sort(reverse=True)
        
        # Clear existing AI links to avoid duplicates
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_links")
        conn.commit()
        conn.close()
        
        # Try to find CSV files in all exports and load ALL data
        all_csv_files = []
        for export_dir in export_dirs:
            csv_dir = os.path.join(SCRAPED_LINKS_DIR, export_dir, '📊_CSV_Data')
            if not os.path.exists(csv_dir):
                continue
                
            csv_files = [f for f in os.listdir(csv_dir) if f.endswith('.csv')]
            for csv_file in csv_files:
                csv_path = os.path.join(csv_dir, csv_file)
                try:
                    # Get the file size as a proxy for amount of data
                    file_size = os.path.getsize(csv_path)
                    all_csv_files.append((csv_path, file_size))
                except:
                    continue
        
        if not all_csv_files:
            print("No CSV files found")
            return []
        
        # Sort by file size (largest first) and load ALL files to get maximum data
        all_csv_files.sort(key=lambda x: x[1], reverse=True)
        
        print(f"🔍 Found {len(all_csv_files)} CSV files to process:")
        for i, (csv_path, file_size) in enumerate(all_csv_files):
            print(f"  {i+1}. {os.path.basename(csv_path)} ({file_size} bytes)")
        print()
        
        all_links = []
        processed_urls = set()  # Track URLs to avoid duplicates
        
        for csv_path, file_size in all_csv_files:
            print(f"Loading AI links from: {csv_path} (size: {file_size} bytes)")
            
            try:
                # Use pandas for more robust CSV parsing
                df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip', 
                               dtype=str, na_filter=False, keep_default_na=False)
                
                new_links_count = 0
                print(f"📋 Processing {len(df)} rows in CSV file...")
                
                for idx, row in df.iterrows():
                    url = str(row.get('url', '')).strip()
                    title = str(row.get('title', '')).strip()
                    slack_user = str(row.get('slack_user', '')).strip()
                    
                    print(f"  Row {idx+1}: URL='{url[:80]}...' Title='{title[:50]}...' User='{slack_user}'")
                    
                    # Filter out invalid URLs
                    if not url:
                        print(f"    ❌ SKIP: Empty URL")
                        continue
                    
                    if url in processed_urls:
                        print(f"    ❌ SKIP: Duplicate URL")
                        continue
                    
                    if url.startswith(('http://localhost', 'https://localhost', 'http://127.0.0.1', 'https://127.0.0.1')):
                        print(f"    ❌ SKIP: Localhost URL")
                        continue
                    
                    if not url.startswith(('http://', 'https://')):
                        print(f"    ❌ SKIP: Invalid protocol")
                        continue
                    
                    if '.' not in url or len(url) <= 10:
                        print(f"    ❌ SKIP: Invalid URL format")
                        continue
                    
                    # Handle potential encoding issues
                    def safe_str(val):
                        if not val or pd.isna(val):
                            return ''
                        text = str(val)
                        # Clean up emoji encoding issues
                        text = text.replace('\ufffd', '')  # Remove replacement characters
                        return text.encode('utf-8', errors='ignore').decode('utf-8')
                    
                    # Handle word count safely
                    def safe_int(val):
                        if not val or pd.isna(val):
                            return 0
                        try:
                            return int(float(val))
                        except (ValueError, TypeError):
                            return 0
                    
                    link_data = {
                        'title': safe_str(row.get('title', '')),
                        'url': safe_str(url),
                        'domain': safe_str(row.get('domain', '')),
                        'content': safe_str(row.get('full_content', row.get('content', ''))),
                        'content_type': safe_str(row.get('content_type', 'article')),
                        'category': safe_str(row.get('category', 'General')),
                        'word_count': safe_int(row.get('word_count', 0)),
                        'slack_user': safe_str(row.get('slack_user', '')),
                        'date_scraped': safe_str(row.get('scraped_at', datetime.now().isoformat())),
                        'date_shared': safe_str(row.get('slack_timestamp', '')),
                        'brief_description': safe_str(row.get('brief_description', ''))
                    }
                    
                    print(f"    ✅ ADDED: {link_data['title'][:50]}... | {link_data['domain']} | {link_data['word_count']} words | User: {link_data['slack_user']}")
                    
                    all_links.append(link_data)
                    processed_urls.add(url)
                    new_links_count += 1
                
                print(f"Loaded {new_links_count} unique links from {len(df)} total rows in {csv_path}")
                
            except Exception as e:
                print(f"Error loading CSV file {csv_path}: {e}")
                continue
        
        # Store all unique links in database
        for link in all_links:
            try:
                db.add_ai_link(link)
            except Exception as e:
                print(f"Error adding link to database: {e}")
                continue
        
        print(f"\n📊 FINAL SUMMARY:")
        print(f"   📁 Total CSV files processed: {len(all_csv_files)}")
        print(f"   🔗 Total unique links found: {len(all_links)}")
        print(f"   💾 Links saved to database: {len(all_links)}")
        
        if all_links:
            print(f"\n🎯 Sample of links found:")
            for i, link in enumerate(all_links[:5]):
                print(f"   {i+1}. {link['title'][:60]}...")
                print(f"      URL: {link['url']}")
                print(f"      Domain: {link['domain']} | User: {link['slack_user']} | Words: {link['word_count']}")
                print()
        
        print(f"Successfully loaded {len(all_links)} unique AI links from {len(all_csv_files)} CSV files")
        return all_links
        
    except Exception as e:
        print(f"Error loading scraped links: {e}")
        return []

# Initialize database and managers
db = SalesIntelligenceDB(DATABASE_PATH)
b2b_manager = B2BVaultManager(db)

# Load initial data on import (for both local and serverless deployment)
def initialize_data():
    """Initialize data for the application"""
    try:
        # Load scraped AI links
        load_scraped_links()
        
        # Check if we have B2B articles in the database
        existing_articles = db.get_b2b_articles(limit=1)
        
        if not existing_articles:
            print("🔄 Loading B2B Vault articles...")
            
            # Check if we're in a serverless environment (like Vercel)
            is_serverless = os.environ.get('VERCEL') or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER')
            
            if is_serverless:
                print("🌐 Detected serverless environment - loading demo data")
                # In serverless, always use demo data for reliability
                try:
                    if B2B_VAULT_AVAILABLE:
                        integration = B2BVaultIntegration()
                        demo_articles = integration.get_demo_articles("All", 20)
                        for article in demo_articles:
                            db.add_b2b_article(article)
                        print(f"✅ Loaded {len(demo_articles)} demo B2B Vault articles for serverless")
                    else:
                        # Fallback: create demo articles directly if integration not available
                        print("⚠️  B2B Vault integration not available - creating fallback demo articles")
                        demo_articles = [
                            {
                                "title": "The Future of B2B Sales: AI and Automation Revolution",
                                "url": "https://theb2bvault.com/ai-sales-revolution",
                                "publisher": "B2B Vault",
                                "category": "Sales",
                                "content": "Artificial intelligence is transforming B2B sales processes by enabling predictive analytics, intelligent lead scoring, and automated follow-up processes...",
                                "summary": "AI and automation are revolutionizing B2B sales by enabling predictive analytics, intelligent lead scoring, and automated follow-up processes. Companies adopting AI-powered sales tools report 30% higher conversion rates and 25% faster deal closure times.",
                                "word_count": 1850,
                                "date_scraped": datetime.now().isoformat()
                            },
                            {
                                "title": "Account-Based Marketing: The Complete 2024 Playbook", 
                                "url": "https://theb2bvault.com/abm-playbook-2024",
                                "publisher": "B2B Vault",
                                "category": "ABM & GTM",
                                "content": "Account-based marketing has evolved significantly with new tools and strategies for targeting high-value prospects...",
                                "summary": "ABM success requires strategic alignment between sales and marketing teams, personalized content at scale, and sophisticated intent data analysis. This comprehensive playbook covers implementation strategies and measurement frameworks.",
                                "word_count": 2100,
                                "date_scraped": datetime.now().isoformat()
                            },
                            {
                                "title": "Content Marketing ROI: Measuring What Matters in B2B",
                                "url": "https://theb2bvault.com/content-marketing-roi", 
                                "publisher": "B2B Vault",
                                "category": "Content Marketing",
                                "content": "Measuring content marketing ROI in B2B requires advanced attribution models and multi-touch analytics...",
                                "summary": "B2B content marketing ROI measurement goes beyond vanity metrics to focus on pipeline influence, deal velocity, and customer lifetime value. Advanced attribution models provide deeper insights into content performance.",
                                "word_count": 1650,
                                "date_scraped": datetime.now().isoformat()
                            }
                        ]
                        for article in demo_articles:
                            db.add_b2b_article(article)
                        print(f"✅ Loaded {len(demo_articles)} fallback demo B2B Vault articles")
                except Exception as e:
                    print(f"⚠️  Could not load demo data: {e}")
            else:
                print("🖥️  Local environment detected - attempting real scraping")
                # In local environment, try real scraping first
                try:
                    real_articles = scrape_b2b_vault()
                    for article in real_articles:
                        db.add_b2b_article(article)
                    print(f"✅ Loaded {len(real_articles)} real B2B Vault articles")
                except Exception as e:
                    print(f"⚠️  Could not load real B2B Vault data: {e}")
                    # Fallback to demo data
                    try:
                        if B2B_VAULT_AVAILABLE:
                            integration = B2BVaultIntegration()
                            demo_articles = integration.get_demo_articles("All", 20)
                            for article in demo_articles:
                                db.add_b2b_article(article)
                            print(f"✅ Loaded {len(demo_articles)} demo B2B Vault articles as fallback")
                        else:
                            print("⚠️  B2B Vault integration not available")
                    except Exception as e2:
                        print(f"⚠️  Could not load demo data either: {e2}")
        else:
            print(f"✅ Found {len(existing_articles)} existing B2B articles in database")
    except Exception as e:
        print(f"⚠️  Error during data initialization: {e}")

# Initialize data when the module is imported
initialize_data()

@app.route('/')
def index():
    """Serve the main dashboard"""
    return send_file('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint for deployment platforms"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/ai-links')
def get_ai_links():
    """API endpoint to get AI links with filtering and search"""
    try:
        # Get query parameters
        search = request.args.get('search', '').lower()
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        category = request.args.get('category', '')
        limit = int(request.args.get('limit', 100))
        
        # First try to get from database
        links = db.get_ai_links(limit=1000)  # Get more to filter
        
        # If no links in database, try to load from files
        if not links:
            links = load_scraped_links()
        
        # Apply filters
        filtered_links = []
        for link in links:
            # Search filter
            if search:
                searchable_text = f"{link.get('title', '')} {link.get('content', '')} {link.get('domain', '')} {link.get('slack_user', '')}".lower()
                if search not in searchable_text:
                    continue
            
            # Date range filter
            if start_date or end_date:
                link_date = link.get('date_shared', link.get('date_scraped', ''))
                if link_date:
                    try:
                        # Parse the date (handle both ISO format and Slack timestamp format)
                        if 'T' in link_date:
                            link_dt = datetime.fromisoformat(link_date.replace('Z', '+00:00'))
                        else:
                            link_dt = datetime.fromisoformat(link_date)
                        
                        if start_date:
                            start_dt = datetime.fromisoformat(start_date)
                            if link_dt < start_dt:
                                continue
                        
                        if end_date:
                            end_dt = datetime.fromisoformat(end_date)
                            if link_dt > end_dt:
                                continue
                    except:
                        continue
            
            # Category filter
            if category and category != 'All':
                if link.get('category', '').lower() != category.lower():
                    continue
            
            filtered_links.append(link)
        
        # Sort by date (most recent first)
        filtered_links.sort(key=lambda x: x.get('date_shared', x.get('date_scraped', '')), reverse=True)
        
        # Apply limit
        filtered_links = filtered_links[:limit]
        
        return jsonify(filtered_links)
        
    except Exception as e:
        print(f"Error in get_ai_links: {e}")
        return jsonify([])

@app.route('/api/b2b-articles')
def get_b2b_articles():
    """API endpoint to get B2B Vault articles"""
    try:
        category = request.args.get('category', 'All')
        limit = int(request.args.get('limit', 50))
        
        articles = db.get_b2b_articles(limit=limit, category=category)
        
        return jsonify({
            'success': True,
            'articles': articles,
            'total': len(articles)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/b2b-summary/<int:article_id>')
def get_b2b_summary(article_id):
    """API endpoint to get B2B Vault article summary"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT summary FROM b2b_articles 
            WHERE id = ? AND status = 'active'
        ''', (article_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return jsonify({
                'success': True,
                'summary': result[0]
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Article not found'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/b2b-stats')
def get_b2b_stats():
    """API endpoint to get B2B Vault statistics"""
    try:
        articles = db.get_b2b_articles(limit=1000)
        
        # Calculate stats
        total_articles = len(articles)
        total_words = sum(article.get('word_count', 0) for article in articles)
        categories = len(set(article.get('category', '') for article in articles))
        
        # Top categories
        category_counts = {}
        for article in articles:
            cat = article.get('category', 'Unknown')
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return jsonify({
            'success': True,
            'stats': {
                'total_articles': total_articles,
                'total_words': total_words,
                'categories': categories,
                'top_categories': top_categories
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/b2b-scrape', methods=['POST'])
def start_b2b_scraping():
    """API endpoint to start B2B Vault scraping"""
    try:
        data = request.json
        tags = data.get('tags', ['Sales'])
        max_articles = int(data.get('max_articles', 50))
        
        # Check if we're in a serverless environment
        is_serverless = os.environ.get('VERCEL') or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER')
        
        if is_serverless:
            # In serverless environments, provide demo articles instead of real scraping
            return jsonify({
                'success': False,
                'message': 'Real-time scraping is not available in the deployed version. The app loads curated B2B Vault articles automatically. For live scraping, please run the code locally.',
                'info': 'This is a serverless deployment limitation. Demo articles are automatically loaded on startup.'
            })
        else:
            # In local environments, allow real scraping
            success, message = b2b_manager.start_scraping(tags, max_articles)
            return jsonify({
                'success': success,
                'message': message
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/b2b-scrape-status')
def get_b2b_scrape_status():
    """API endpoint to get B2B Vault scraping status"""
    try:
        status = b2b_manager.get_scraping_status()
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/b2b-categories')
def get_b2b_categories():
    """API endpoint to get available B2B Vault categories"""
    try:
        return jsonify({
            'success': True,
            'categories': B2B_TAGS
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def get_stats():
    """API endpoint to get platform statistics"""
    try:
        ai_links = db.get_ai_links()
        b2b_articles = db.get_b2b_articles()
        
        total_words = sum(link.get('word_count', 0) for link in ai_links)
        successful_scrapes = len([link for link in ai_links if link.get('word_count', 0) > 0])
        
        stats = {
            'total_links': len(ai_links),
            'total_words': total_words,
            'successful_scrapes': successful_scrapes,
            'b2b_articles': len(b2b_articles),
            'latest_date': ai_links[0].get('date_scraped', '--')[:10] if ai_links else '--'
        }
        
        return jsonify(stats)
        
    except Exception as e:
        print(f"Error in get_stats: {e}")
        return jsonify({})

@app.route('/api/search')
def search_content():
    """API endpoint to search across all content"""
    try:
        query = request.args.get('q', '').lower()
        
        ai_links = db.get_ai_links()
        b2b_articles = db.get_b2b_articles()
        
        # Filter AI links
        filtered_links = []
        for link in ai_links:
            if (query in link.get('title', '').lower() or 
                query in link.get('domain', '').lower() or
                query in link.get('content', '').lower()):
                filtered_links.append(link)
        
        # Filter B2B articles
        filtered_articles = []
        for article in b2b_articles:
            if (query in article.get('title', '').lower() or 
                query in article.get('publisher', '').lower() or
                query in article.get('content', '').lower()):
                filtered_articles.append(article)
        
        return jsonify({
            'ai_links': filtered_links,
            'b2b_articles': filtered_articles
        })
        
    except Exception as e:
        print(f"Error in search_content: {e}")
        return jsonify({'ai_links': [], 'b2b_articles': []})

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper():
    """API endpoint to trigger the AI link scraper"""
    try:
        data = request.json
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')
        
        # Import and run the scraper
        from main import main
        import subprocess
        
        # Build command
        cmd = ['python', '../main.py', '--scrape-to-drive']
        if start_date:
            cmd.extend(['--start-date', start_date])
        if end_date:
            cmd.extend(['--end-date', end_date])
        
        # Run the scraper
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Reload links after successful scrape
            load_scraped_links()
            return jsonify({'success': True, 'message': 'Scraper completed successfully'})
        else:
            return jsonify({'success': False, 'error': result.stderr})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upload-b2b-data', methods=['POST'])
def upload_b2b_data():
    """API endpoint to upload B2B Vault data"""
    try:
        # This would handle file uploads from B2B Vault
        # For now, return a placeholder response
        return jsonify({'success': True, 'message': 'B2B Vault integration coming soon'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/export-data')
def export_data():
    """API endpoint to export all data"""
    try:
        ai_links = db.get_ai_links()
        b2b_articles = db.get_b2b_articles()
        
        export_data = {
            'ai_links': ai_links,
            'b2b_articles': b2b_articles,
            'exported_at': datetime.now().isoformat()
        }
        
        # Save to JSON file
        export_path = os.path.join(os.path.dirname(__file__), f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return send_file(export_path, as_attachment=True)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai-categories')
def get_ai_categories():
    """API endpoint to get available AI link categories"""
    try:
        links = db.get_ai_links(limit=1000)
        if not links:
            links = load_scraped_links()
        
        # Extract unique categories
        categories = set()
        for link in links:
            if link.get('category'):
                categories.add(link.get('category'))
        
        categories = sorted(list(categories))
        categories.insert(0, 'All')  # Add 'All' option at the beginning
        
        return jsonify({
            'success': True,
            'categories': categories
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



if __name__ == '__main__':
    print("🚀 Starting B2B Sales Intelligence Platform...")
    print("📊 Dashboard: http://localhost:5002")
    print("🔗 API: http://localhost:5002/api/")
    
    # Load initial data
    load_scraped_links()
    
    # Clear existing fake B2B Vault data and load real data
    try:
        # Clear existing B2B articles
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM b2b_articles")
        conn.commit()
        conn.close()
        
        # Load real B2B Vault articles
        real_articles = scrape_b2b_vault()
        for article in real_articles:
            db.add_b2b_article(article)
        
        print(f"✅ Loaded {len(real_articles)} real B2B Vault articles")
    except Exception as e:
        print(f"⚠️  Could not load B2B Vault data: {e}")
    
    # For serverless deployment (Vercel), don't run the app directly
    # The WSGI handler will be used instead
    if os.environ.get('VERCEL'):
        # Running on Vercel
        pass
    else:
        # Running locally
        app.run(debug=True, port=5002)

# Export the Flask app for WSGI/serverless deployment
# This is what Vercel will import and use
application = app
