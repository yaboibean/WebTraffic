import time
import random
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse, quote
import re
from dataclasses import dataclass
from datetime import datetime
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import psutil
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LinkedInProfile:
    """Data class for LinkedIn profile information"""
    name: str
    headline: str
    location: str
    about: str
    experience: List[Dict[str, str]]
    education: List[Dict[str, str]]
    skills: List[str]
    url: str
    scraped_at: datetime
    memory_usage: float
    attempt_number: int

class SeleniumMultiAttemptScraper:
    """
    A LinkedIn scraper that uses Selenium to scrape profiles multiple times
    and saves each attempt to a separate file for analysis.
    
    This approach helps capture the full page content across multiple attempts,
    showing how the page content changes over time and different conditions.
    
    Note: This scraper is for educational purposes. Always respect LinkedIn's
    terms of service and robots.txt when scraping.
    """
    
    def __init__(self, max_attempts: int = 10, headless: bool = True, 
                 browser_type: str = "chrome", timeout: int = 60):
        """
        Initialize the Selenium multi-attempt scraper.
        
        Args:
            max_attempts: Maximum number of scraping attempts
            headless: Whether to run browser in headless mode
            browser_type: Browser type ('chrome', 'firefox', 'edge')
            timeout: Timeout for page loading in seconds
        """
        self.max_attempts = max_attempts
        self.headless = headless
        self.browser_type = browser_type
        self.timeout = timeout
        self.driver = None
        self.process_id = None
        
    def setup_driver(self):
        """Setup the Selenium WebDriver with appropriate options."""
        try:
            if self.browser_type.lower() == "chrome":
                options = Options()
                
                if self.headless:
                    options.add_argument("--headless")
                
                # Add realistic browser arguments
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                
                # Set user agent
                options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                # Disable images to reduce memory usage
                prefs = {
                    "profile.managed_default_content_settings.images": 2,
                    "profile.default_content_setting_values.notifications": 2
                }
                options.add_experimental_option("prefs", prefs)
                
                # Setup ChromeDriver
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                
                # Execute script to remove webdriver property
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
            else:
                raise ValueError(f"Browser type {self.browser_type} not supported yet")
            
            # Get the process ID for memory monitoring
            self.process_id = self.driver.service.process.pid
            logger.info(f"WebDriver initialized with process ID: {self.process_id}")
            
        except Exception as e:
            logger.error(f"Error setting up WebDriver: {e}")
            raise
    
    def get_memory_usage(self) -> float:
        """
        Get the current memory usage of the browser process in MB.
        
        Returns:
            Memory usage in MB
        """
        try:
            if self.process_id:
                process = psutil.Process(self.process_id)
                memory_mb = process.memory_info().rss / 1024 / 1024  # Convert bytes to MB
                return memory_mb
            return 0.0
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return 0.0
    
    def _wait_for_page_load(self, wait_time: int = 2) -> bool:
        """
        Wait for the page to load with a specified delay.
        
        Args:
            wait_time: Time to wait in seconds
            
        Returns:
            True if page loaded successfully, False otherwise
        """
        try:
            logger.info(f"Waiting {wait_time} seconds for page to load...")
            time.sleep(wait_time)
            return True
        except Exception as e:
            logger.error(f"Error waiting for page load: {e}")
            return False
    
    def _is_auth_wall(self, soup: BeautifulSoup) -> bool:
        """
        Check if the response contains an authentication wall.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            True if authentication wall is detected, False otherwise
        """
        auth_indicators = [
            'sign in to linkedin',
            'join linkedin',
            'authwall',
            'login required',
            'please sign in',
            'join to view',
            'sign up to view'
        ]
        
        page_text = soup.get_text().lower()
        
        for indicator in auth_indicators:
            if indicator in page_text:
                logger.warning(f"Authentication wall detected: {indicator}")
                return True
        
        return False
    
    def _has_meaningful_content(self, soup: BeautifulSoup) -> bool:
        """
        Check if the page contains meaningful LinkedIn profile content.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            True if meaningful content is found, False otherwise
        """
        # Look for LinkedIn-specific content indicators
        content_indicators = [
            'class="pv-text-details__left-panel"',
            'class="pv-top-card"',
            'class="experience__company-name"',
            'class="education__school-name"',
            'data-section="summary"',
            'data-section="experience"',
            'data-section="education"',
            'class="pv-top-card__non-inline-text"',
            'class="text-heading-xlarge"'
        ]
        
        page_html = str(soup)
        
        for indicator in content_indicators:
            if indicator in page_html:
                logger.info(f"Found meaningful content indicator: {indicator}")
                return True
        
        return False
    
    def _has_json_ld_schema(self, soup: BeautifulSoup) -> bool:
        """
        Check if the page contains JSON-LD schema with LinkedIn profile data.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            True if JSON-LD schema is found, False otherwise
        """
        try:
            # Look for script tags with application/ld+json type
            script_tags = soup.find_all('script', type='application/ld+json')
            
            for script in script_tags:
                script_content = script.get_text().strip()
                if script_content:
                    # Check if it contains LinkedIn profile schema indicators
                    if ('"@type":"Person"' in script_content and 
                        'linkedin.com/in/' in script_content and
                        ('"jobTitle"' in script_content or '"worksFor"' in script_content or '"alumniOf"' in script_content)):
                        logger.info("✅ Found JSON-LD schema with LinkedIn profile data")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking for JSON-LD schema: {e}")
            return False
    
    def scrape_profile(self, profile_url: str) -> List[Dict[str, Any]]:
        """
        Scrape a LinkedIn profile with JSON-LD schema detection.
        
        Args:
            profile_url: The LinkedIn profile URL to scrape
            
        Returns:
            List of dictionaries containing attempt results
        """
        if not self.driver:
            self.setup_driver()
        
        results = []
        best_attempt = None
        
        # Add live preview indicator
        if not self.headless:
            print("\n👀 LIVE PREVIEW MODE")
            print("🌐 Browser window is now visible")
            print("📍 You can watch the navigation happen in real-time")
            print(f"🎯 Target: {profile_url}")
        
        for attempt in range(1, self.max_attempts + 1):
            logger.info(f"Attempt {attempt}/{self.max_attempts} to scrape {profile_url}")
            
            if not self.headless:
                print(f"\n👀 LIVE: Attempt {attempt} - Watch the browser navigate...")
                print(f"🔄 Loading: {profile_url}")
            
            try:
                # Navigate directly to LinkedIn URL
                logger.info(f"Navigating directly to LinkedIn URL...")
                self.driver.get(profile_url)
                
                if not self.headless:
                    print(f"✅ Page loaded - You can see the LinkedIn profile in the browser")
                    print(f"🔍 Analyzing page content...")
                
                # Wait for page load with consistent delay
                wait_time = 2  # Fixed 2 seconds for all attempts
                if not self._wait_for_page_load(wait_time):
                    logger.warning("Failed to wait for page load")
                    continue
                
                # Get memory usage
                memory_usage = self.get_memory_usage()
                logger.info(f"Memory usage: {memory_usage:.2f}MB")
                
                # Get page source
                page_source = self.driver.page_source
                page_length = len(page_source)
                logger.info(f"Page source length: {page_length:,} characters")
                
                if not self.headless:
                    print(f"📊 Page analysis:")
                    print(f"   📄 Content length: {page_length:,} characters")
                    print(f"   💾 Memory usage: {memory_usage:.2f}MB")
                
                # Parse the HTML
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Save HTML file with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                html_filename = f"parsed_linkedin_profile_{attempt-1}.json"  # Use attempt-1 to match the loop index
                with open(html_filename, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                logger.info(f"HTML saved to: {html_filename}")
                
                # Check for JSON-LD schema (primary success criterion)
                has_json_ld = self._has_json_ld_schema(soup)
                
                # Check for authentication wall
                auth_wall_detected = self._is_auth_wall(soup)
                
                # Check for meaningful content
                has_meaningful_content = self._has_meaningful_content(soup)
                
                if not self.headless:
                    print(f"🔍 Content analysis:")
                    print(f"   {'✅' if has_json_ld else '❌'} JSON-LD schema found")
                    print(f"   {'❌' if auth_wall_detected else '✅'} No authentication wall")
                    print(f"   {'✅' if has_meaningful_content else '❌'} Meaningful content found")
                
                # Create result dictionary
                result = {
                    'attempt_number': attempt,
                    'timestamp': timestamp,
                    'memory_usage_mb': memory_usage,
                    'page_source_length': page_length,
                    'html_filename': html_filename,
                    'auth_wall_detected': auth_wall_detected,
                    'has_meaningful_content': has_meaningful_content,
                    'has_json_ld_schema': has_json_ld,
                    'attempt_successful': False,  # Will be determined by JSON-LD detection
                    'profile_extracted': False,
                    'profile': None
                }
                
                results.append(result)
                
                # Success criterion: JSON-LD schema found
                if has_json_ld:
                    logger.info(f"🎯 JSON-LD schema found on attempt {attempt} - stopping immediately!")
                    if not self.headless:
                        print(f"🎉 SUCCESS! Schema data found on attempt {attempt}")
                        print(f"🛑 Stopping scraping - we have what we need!")
                    best_attempt = attempt
                    break
                
                # If no JSON-LD found, continue to next attempt
                logger.info(f"No JSON-LD schema found on attempt {attempt} - continuing...")
                if not self.headless:
                    print(f"⚠️  No schema found on attempt {attempt}")
                    print(f"🔄 Will try again in 4 seconds...")
                
            except Exception as e:
                logger.error(f"Error during scraping attempt {attempt}: {e}")
                if not self.headless:
                    print(f"❌ Error on attempt {attempt}: {e}")
                
                # Create error result
                result = {
                    'attempt_number': attempt,
                    'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                    'memory_usage_mb': self.get_memory_usage(),
                    'page_source_length': 0,
                    'html_filename': None,
                    'auth_wall_detected': False,
                    'has_meaningful_content': False,
                    'has_json_ld_schema': False,
                    'attempt_successful': False,
                    'profile_extracted': False,
                    'profile': None,
                    'error': str(e)
                }
                
                results.append(result)
            
            # Add consistent delay between attempts (except for the last one)
            if attempt < self.max_attempts:
                delay = 4  # Fixed 4 seconds between attempts
                logger.info(f"Waiting {delay} seconds before next attempt...")
                if not self.headless:
                    print(f"⏱️  Waiting {delay} seconds before next attempt...")
                    for i in range(delay, 0, -1):
                        print(f"   {i}...", end='\r')
                        time.sleep(1)
                    print("   ✅ Ready for next attempt!")
                else:
                    time.sleep(delay)
        
        # Mark the best attempt as successful and extract profile
        if best_attempt and best_attempt <= len(results):
            best_result = results[best_attempt - 1]  # Convert to 0-based index
            
            # Mark as successful
            best_result['attempt_successful'] = True
            
            # Clean up other HTML files, keeping only the best one
            best_html_filename = best_result['html_filename']
            for result in results:
                if result['html_filename'] and result['html_filename'] != best_html_filename:
                    try:
                        os.remove(result['html_filename'])
                        logger.info(f"Cleaned up HTML file: {result['html_filename']}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up HTML file {result['html_filename']}: {e}")
            
            # Extract profile if we have JSON-LD schema
            if best_result.get('has_json_ld_schema', False) and not best_result.get('auth_wall_detected', False):
                # Re-parse the HTML from the best attempt
                with open(best_result['html_filename'], 'r', encoding='utf-8') as f:
                    best_html = f.read()
                
                soup = BeautifulSoup(best_html, 'html.parser')
                profile = self._extract_profile_info(
                    soup, 
                    profile_url, 
                    best_result['memory_usage_mb'], 
                    best_attempt
                )
                
                if profile:
                    best_result['profile'] = profile
                    best_result['profile_extracted'] = True
                    logger.info(f"✅ Successfully extracted profile from best attempt {best_attempt}")
                else:
                    logger.warning(f"Failed to extract profile from best attempt {best_attempt}")
            
            logger.info(f"Best attempt determined: {best_attempt}")
        else:
            logger.warning("No best attempt determined - no JSON-LD schema found")
            # Clean up all HTML files if no successful attempt
            for result in results:
                if result['html_filename']:
                    try:
                        os.remove(result['html_filename'])
                        logger.info(f"Cleaned up HTML file: {result['html_filename']}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up HTML file {result['html_filename']}: {e}")
        
        logger.info(f"Completed scraping with {len(results)} attempts. Best attempt: {best_attempt}")
        return results
    
    def _extract_profile_info(self, soup: BeautifulSoup, profile_url: str, 
                             memory_usage: float, attempt_number: int) -> Optional[LinkedInProfile]:
        """
        Extract profile information from the parsed HTML.
        
        Args:
            soup: BeautifulSoup object of the page
            profile_url: The original profile URL
            memory_usage: Memory usage when scraped
            attempt_number: Which attempt this was
            
        Returns:
            LinkedInProfile object if successful, None otherwise
        """
        try:
            # Extract basic information
            name = self._extract_name(soup)
            headline = self._extract_headline(soup)
            location = self._extract_location(soup)
            about = self._extract_about(soup)
            
            # Extract experience
            experience = self._extract_experience(soup)
            
            # Extract education
            education = self._extract_education(soup)
            
            # Extract skills
            skills = self._extract_skills(soup)
            
            # Create profile object
            profile = LinkedInProfile(
                name=name or "Not found",
                headline=headline or "Not found",
                location=location or "Not found",
                about=about or "Not found",
                experience=experience,
                education=education,
                skills=skills,
                url=profile_url,
                scraped_at=datetime.now(),
                memory_usage=memory_usage,
                attempt_number=attempt_number
            )
            
            return profile
            
        except Exception as e:
            logger.error(f"Error extracting profile info: {e}")
            return None
    
    def _extract_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the profile name."""
        try:
            # Try multiple selectors for name
            selectors = [
                'h1.text-heading-xlarge',
                '.pv-text-details__left-panel h1',
                '.pv-top-card--list-bullet h1',
                'h1[data-section="name"]',
                '.pv-top-card__non-inline-text',
                'h1',
                '.pv-top-card h1'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    name = element.get_text().strip()
                    if name and len(name) > 0 and len(name) < 100:  # Reasonable name length
                        return name
            
            return None
        except Exception as e:
            logger.error(f"Error extracting name: {e}")
            return None
    
    def _extract_headline(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the profile headline."""
        try:
            selectors = [
                '.text-body-medium.break-words',
                '.pv-text-details__left-panel .text-body-medium',
                '.pv-top-card--list-bullet .text-body-medium',
                '[data-section="headline"]',
                '.pv-top-card .text-body-medium',
                '.pv-top-card__headline'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    headline = element.get_text().strip()
                    if headline:
                        return headline
            
            return None
        except Exception as e:
            logger.error(f"Error extracting headline: {e}")
            return None
    
    def _extract_location(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the profile location."""
        try:
            selectors = [
                '.pv-text-details__left-panel .text-body-small',
                '.pv-top-card--list-bullet .text-body-small',
                '[data-section="location"]',
                '.pv-top-card .text-body-small'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    location = element.get_text().strip()
                    if location and ('location' in location.lower() or ',' in location):
                        return location
            
            return None
        except Exception as e:
            logger.error(f"Error extracting location: {e}")
            return None
    
    def _extract_about(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the about section."""
        try:
            selectors = [
                '[data-section="summary"] .pv-shared-text-with-see-more',
                '.pv-about__summary-text',
                '.pv-shared-text-with-see-more',
                '.pv-about__summary',
                '.pv-top-card__summary'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    about = element.get_text().strip()
                    if about:
                        return about
            
            return None
        except Exception as e:
            logger.error(f"Error extracting about: {e}")
            return None
    
    def _extract_experience(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract work experience."""
        experience_list = []
        
        try:
            # Look for experience sections with multiple selectors
            selectors = [
                '[data-section="experience"] .pvs-list__item--line-separated',
                '.experience__company-name',
                '.pv-position-entity',
                '.pvs-list__item--line-separated'
            ]
            
            for selector in selectors:
                experience_sections = soup.select(selector)
                if experience_sections:
                    break
            
            for section in experience_sections:
                try:
                    # Extract company name
                    company_element = section.select_one('.pvs-entity__path-node, .experience__company-name')
                    company = company_element.get_text().strip() if company_element else "Unknown"
                    
                    # Extract job title
                    title_element = section.select_one('.pvs-entity__path-node + span, .experience__title')
                    title = title_element.get_text().strip() if title_element else "Unknown"
                    
                    # Extract duration
                    duration_element = section.select_one('.pvs-entity__caption-wrapper, .experience__duration')
                    duration = duration_element.get_text().strip() if duration_element else "Unknown"
                    
                    if company != "Unknown" or title != "Unknown":
                        experience_list.append({
                            'company': company,
                            'title': title,
                            'duration': duration
                        })
                    
                except Exception as e:
                    logger.error(f"Error extracting individual experience: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting experience: {e}")
        
        return experience_list
    
    def _extract_education(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract education information."""
        education_list = []
        
        try:
            # Look for education sections with multiple selectors
            selectors = [
                '[data-section="education"] .pvs-list__item--line-separated',
                '.education__school-name',
                '.pv-education-entity'
            ]
            
            for selector in selectors:
                education_sections = soup.select(selector)
                if education_sections:
                    break
            
            for section in education_sections:
                try:
                    # Extract school name
                    school_element = section.select_one('.pvs-entity__path-node, .education__school-name')
                    school = school_element.get_text().strip() if school_element else "Unknown"
                    
                    # Extract degree
                    degree_element = section.select_one('.pvs-entity__path-node + span, .education__degree')
                    degree = degree_element.get_text().strip() if degree_element else "Unknown"
                    
                    # Extract duration
                    duration_element = section.select_one('.pvs-entity__caption-wrapper, .education__duration')
                    duration = duration_element.get_text().strip() if duration_element else "Unknown"
                    
                    if school != "Unknown" or degree != "Unknown":
                        education_list.append({
                            'school': school,
                            'degree': degree,
                            'duration': duration
                        })
                    
                except Exception as e:
                    logger.error(f"Error extracting individual education: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting education: {e}")
        
        return education_list
    
    def _extract_skills(self, soup: BeautifulSoup) -> List[str]:
        """Extract skills information."""
        skills_list = []
        
        try:
            # Look for skills sections with multiple selectors
            selectors = [
                '[data-section="skills"] .pvs-list__item--line-separated',
                '.skill-categories-section .pvs-list__item--line-separated',
                '.pvs-list__item--line-separated'
            ]
            
            for selector in selectors:
                skills_elements = soup.select(selector)
                if skills_elements:
                    break
            
            for element in skills_elements:
                try:
                    skill_text = element.get_text().strip()
                    if skill_text and len(skill_text) < 100:  # Reasonable skill name length
                        skills_list.append(skill_text)
                except Exception as e:
                    logger.error(f"Error extracting individual skill: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting skills: {e}")
        
        return skills_list
    
    def save_results_to_json(self, results: List[Dict[str, Any]], filename: str):
        """Save scraping results to JSON file."""
        try:
            # Convert results to JSON-serializable format
            json_results = []
            for result in results:
                json_result = result.copy()
                if result.get('profile'):
                    # Convert profile dataclass to dict
                    profile = result['profile']
                    json_result['profile'] = {
                        'name': profile.name,
                        'headline': profile.headline,
                        'location': profile.location,
                        'about': profile.about,
                        'experience': profile.experience,
                        'education': profile.education,
                        'skills': profile.skills,
                        'url': profile.url,
                        'scraped_at': profile.scraped_at.isoformat(),
                        'memory_usage': profile.memory_usage,
                        'attempt_number': profile.attempt_number
                    }
                json_results.append(json_result)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(json_results, f, indent=2, default=str, ensure_ascii=False)
            logger.info(f"Results saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving results: {e}")
    
    def close(self):
        """Close the WebDriver and clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

def main(profile_url: str):
    """Example usage of the SeleniumMultiAttemptScraper."""
    # Initialize the scraper
    scraper = SeleniumMultiAttemptScraper(max_attempts=10, headless=True)
    
    try:
        # Example LinkedIn profile URL
        # profile_url = "https://www.linkedin.com/in/example-profile"
        
        # Scrape the profile multiple times
        results = scraper.scrape_profile(profile_url)
        
        # Save results to JSON file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_filename = f"linkedin_scraping_results_{timestamp}.json"
        scraper.save_results_to_json(results, results_filename)
        
        # Print summary
        successful_attempts = sum(1 for r in results if r.get('profile_extracted', False))
        print(f"Completed {len(results)} attempts")
        print(f"Successful profile extractions: {successful_attempts}")
        print(f"Results saved to: {results_filename}")
        
    finally:
        # Always close the scraper
        scraper.close()

if __name__ == "__main__":
    main("https://www.linkedin.com/in/justin-j-e-jones")