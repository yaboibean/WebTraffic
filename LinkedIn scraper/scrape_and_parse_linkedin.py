#!/usr/bin/env python3
"""
Combined LinkedIn Scraper and Schema Parser

Usage:
    python scrape_and_parse_linkedin.py <linkedin_profile_url> [max_attempts] [headless]
    python scrape_and_parse_linkedin.py --csv <urls_file> [max_attempts] [headless]

- Scrapes the given LinkedIn profile URL using Selenium
- Parses the best HTML file for structured profile data
- Outputs the parsed profile as JSON
- With --csv flag: processes multiple URLs from a file and outputs CSV
"""
import sys
import os
import json
import csv
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from selenium_memory_scraper import SeleniumMultiAttemptScraper
from linkedin_schema_parser import LinkedInSchemaParser



def scrape_multiple_profiles_to_csv(urls, max_attempts=10, headless=True, output_filename=None, preview_mode=False):
    """
    Scrape multiple LinkedIn profiles and output to CSV.
    
    Args:
        urls: List of LinkedIn profile URLs
        max_attempts: Maximum number of scraping attempts per profile
        headless: Whether to run browser in headless mode
        output_filename: Output CSV filename (auto-generated if None)
        preview_mode: Whether to show live browser preview
    
    Returns:
        Output filename
    """
    if not output_filename:
        output_filename = f"linkedin_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # Force non-headless mode if preview is requested
    if preview_mode:
        headless = False
        print("👀 LIVE PREVIEW MODE: Browser window will be visible")
        print("   You can watch the scraping happen in real-time")
        print("   The browser will navigate through each LinkedIn profile")
        input("   Press Enter to start live preview...")
    
    scraper = SeleniumMultiAttemptScraper(max_attempts=max_attempts, headless=headless)
    parser = LinkedInSchemaParser()
    
    # Get all field names from the first successful scrape
    fieldnames = None
    successful_profiles = []
    
    try:
        for i, url in enumerate(urls, 1):
            print(f"\n{'='*60}")
            print(f"🔍 LIVE SCRAPING: Profile {i}/{len(urls)}")
            print(f"🌐 Target: {url}")
            print(f"{'='*60}")
            
            if preview_mode:
                print(f"👀 Watch the browser navigate to: {url}")
                print(f"   You'll see the page load in real-time...")
            
            try:
                results = scraper.scrape_profile(url)
                best_result = next((r for r in results if r.get('attempt_successful', False)), None)
                
                if not best_result:
                    print(f"❌ Failed to scrape profile: {url}")
                    continue
                
                html_file = best_result['html_filename']
                print(f"✅ Successfully scraped: {html_file}")
                
                # Parse the HTML file
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                profile_schema = parser.extract_schema_from_html(html_content, url)
                # No-op: If profile_schema is None, let the next lines handle it (may raise error or skip)
                
                # Convert to dictionary format
                profile_dict = parser.to_postgres_dict(profile_schema)
                
                # Get fieldnames from first successful profile
                if fieldnames is None:
                    fieldnames = list(profile_dict.keys())
                
                successful_profiles.append(profile_dict)
                print(f"✅ Successfully parsed profile: {profile_schema.name}")
                
                if preview_mode:
                    print(f"📊 Extracted data preview:")
                    print(f"   Name: {profile_schema.name}")
                    print(f"   Current Position: {profile_schema.current_position}")
                    print(f"   Company: {profile_schema.current_company}")
                    print(f"   Location: {profile_schema.location}")
                    input("   Press Enter to continue to next profile...")
            except Exception as e:
                print(f"❌ Error processing profile {url}: {e}")
    
    finally:
        if preview_mode:
            print("\n🏁 Scraping complete! Closing browser...")
            input("Press Enter to close the browser window...")
        scraper.close()
    
    # Write to CSV
    if successful_profiles and fieldnames:
        with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(successful_profiles)
        
        print(f"✅ Successfully processed {len(successful_profiles)}/{len(urls)} profiles")
        print(f"📄 CSV output saved to: {output_filename}")
        return output_filename
    else:
        print("❌ No profiles were successfully processed")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single profile: python scrape_and_parse_linkedin.py <linkedin_profile_url> [max_attempts] [headless]")
        print("  Multiple profiles: python scrape_and_parse_linkedin.py --csv <urls_file> [max_attempts] [headless]")
        sys.exit(1)
    
    # Check if CSV mode is requested
    if sys.argv[1] == '--csv':
        if len(sys.argv) < 3:
            print("Usage: python scrape_and_parse_linkedin.py --csv <urls_file> [max_attempts] [headless]")
            sys.exit(1)
        
        urls_file = sys.argv[2]
        max_attempts = 10
        headless = True
        
        if len(sys.argv) > 3:
            try:
                max_attempts = int(sys.argv[3])
            except ValueError:
                print("max_attempts must be an integer")
                sys.exit(1)
        if len(sys.argv) > 4:
            headless = sys.argv[4].lower() in ['true', '1', 'yes', 'y']
        
    # Read URLs from file
    try:
        print(urls_file)
        with open(urls_file, 'r', encoding='utf-8') as f:
            urls = [
                line.strip()
                for line in f
                if line.strip() and not line.startswith('#') and line.strip().lower() != 'nan'
            ]
    except FileNotFoundError:
        print(f"❌ URLs file not found: {urls_file}")
        sys.exit(1)
    
    if not urls:
        print("❌ No URLs found in file")
        sys.exit(1)
    
    print(f"Found {len(urls)} URLs to process")
    # Check for preview flag
    preview_mode = '--preview' in sys.argv
    if preview_mode:
        print("👀 LIVE PREVIEW MODE ENABLED")
        print("You will see the browser navigate through each LinkedIn profile in real-time")
    
    scrape_multiple_profiles_to_csv(urls, max_attempts, headless, preview_mode=preview_mode)
    return
    
    # Original single profile functionality
    profile_url = sys.argv[1]
    max_attempts = 10
    headless = True
    if len(sys.argv) > 2:
        try:
            max_attempts = int(sys.argv[2])
        except ValueError:
            print("max_attempts must be an integer")
            sys.exit(1)
    if len(sys.argv) > 3:
        headless = sys.argv[3].lower() in ['true', '1', 'yes', 'y']

    # 👇👇👇 Add this block to get the output filename from the command line
    output_filename = sys.argv[4] if len(sys.argv) > 4 else "processed_url.json"

    print(f"Scraping LinkedIn profile: {profile_url}")
    scraper = SeleniumMultiAttemptScraper(max_attempts=max_attempts, headless=headless)
    try:
        results = scraper.scrape_profile(profile_url)
        best_result = next((r for r in results if r.get('attempt_successful', False)), None)
        if not best_result:
            print("❌ No successful scrape found.")
            if not hasattr(main, "fail_count"):
                main.fail_count = 0
            main.fail_count += 1
            sys.exit(1)
        html_file = best_result['html_filename']
        print(f"Best HTML file: {html_file}")
    finally:
        scraper.close()

    # Parse the best HTML file
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    parser = LinkedInSchemaParser()
    profile_schema = parser.extract_schema_from_html(html_content, profile_url)
    if not profile_schema:
        print("❌ Failed to parse profile schema.")
        sys.exit(1)
    # Output as JSON
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(parser.to_postgres_dict(profile_schema), f, indent=2, ensure_ascii=False)
    print(f"✅ Parsed profile saved to {output_filename}")
    print(json.dumps(parser.to_postgres_dict(profile_schema), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()