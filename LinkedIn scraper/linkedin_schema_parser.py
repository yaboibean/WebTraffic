import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LinkedInProfileSchema:
    """Data class for LinkedIn profile schema information"""
    linkedin_url: str
    name: str
    title: str  # Headline/title text from LinkedIn
    job_titles: List[str]
    location: Optional[str]
    languages: List[str]
    current_company: Optional[str]
    current_position: Optional[str]
    education: List[Dict[str, Any]]
    experience: List[Dict[str, Any]]
    skills: List[str]
    followers_count: Optional[int]
    profile_image_url: Optional[str]
    awards: List[str]
    member_of: List[Dict[str, Any]]
    description: str
    scraped_at: datetime
    raw_schema: Dict[str, Any]

class LinkedInSchemaParser:
    """
    Parser for LinkedIn JSON-LD schema data.
    
    Extracts structured data from LinkedIn profile pages and formats it
    for PostgreSQL database insertion.
    """
    
    def __init__(self):
        """Initialize the schema parser."""
        pass
    
    def extract_schema_from_html(self, html_content: str, profile_url: str) -> Optional[LinkedInProfileSchema]:
        """
        Extract JSON-LD schema from HTML content and supplement with direct HTML scraping.
        
        Args:
            html_content: The HTML content of the LinkedIn profile page
            profile_url: The LinkedIn profile URL
            
        Returns:
            LinkedInProfileSchema object if successful, None otherwise
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # First, try to extract from JSON-LD schema
            schema_data = None
            script_tags = soup.find_all('script', type='application/ld+json')
            
            for script in script_tags:
                script_content = script.get_text().strip()
                if script_content:
                    try:
                        parsed_schema = json.loads(script_content)
                        if self._is_linkedin_profile_schema(parsed_schema):
                            schema_data = parsed_schema
                            break
                    except json.JSONDecodeError:
                        continue
            
            # Extract basic info from schema if available
            if schema_data:
                profile_schema = self._parse_profile_schema(schema_data, profile_url)
            else:
                # Create minimal profile schema if no JSON-LD found
                profile_schema = LinkedInProfileSchema(
                    linkedin_url=profile_url,
                    name="Unknown",
                    title="",
                    job_titles=[],
                    location=None,
                    languages=[],
                    current_company=None,
                    current_position=None,
                    education=[],
                    experience=[],
                    skills=[],
                    followers_count=None,
                    profile_image_url=None,
                    awards=[],
                    member_of=[],
                    description="",
                    scraped_at=datetime.now(),
                    raw_schema={}
                )
            
            # Supplement with direct HTML scraping for complete data
            self._supplement_with_html_scraping(soup, profile_schema)
            
            return profile_schema
            
        except Exception as e:
            logger.error(f"Error extracting schema from HTML: {e}")
            return None
    
    def _is_linkedin_profile_schema(self, schema_data: Dict[str, Any]) -> bool:
        """
        Check if the schema data represents a LinkedIn profile.
        
        Args:
            schema_data: The parsed JSON-LD schema data
            
        Returns:
            True if it's a LinkedIn profile schema, False otherwise
        """
        try:
            # Check for @graph structure (common in LinkedIn schemas)
            if '@graph' in schema_data:
                graph = schema_data['@graph']
                for item in graph:
                    if isinstance(item, dict) and item.get('@type') == 'Person':
                        return True
            
            # Check for direct Person type
            if schema_data.get('@type') == 'Person':
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking schema type: {e}")
            return False
    
    def _parse_profile_schema(self, schema_data: Dict[str, Any], profile_url: str) -> LinkedInProfileSchema:
        """
        Parse the LinkedIn profile schema into structured data.
        
        Args:
            schema_data: The parsed JSON-LD schema data
            profile_url: The LinkedIn profile URL
            
        Returns:
            LinkedInProfileSchema object
        """
        try:
            # Extract person data from @graph or direct schema
            person_data = self._extract_person_data(schema_data)
            
            if not person_data:
                raise ValueError("No person data found in schema")
            
            # Extract basic information
            name = person_data.get('name', 'Unknown')
            title = person_data.get('title', '')
            job_titles = person_data.get('jobTitle', [])
            if isinstance(job_titles, str):
                job_titles = [job_titles]
            
            # Extract location
            location = None
            address = person_data.get('address', {})
            if isinstance(address, dict):
                locality = address.get('addressLocality', '')
                country = address.get('addressCountry', '')
                if locality and country:
                    location = f"{locality}, {country}"
                elif locality:
                    location = locality
                elif country:
                    location = country
            
            # Extract languages
            languages = []
            knows_language = person_data.get('knowsLanguage', [])
            for lang in knows_language:
                if isinstance(lang, dict):
                    languages.append(lang.get('name', ''))
                elif isinstance(lang, str):
                    languages.append(lang)
            
            # Extract current company and position from worksFor
            current_company = None
            current_position = None
            works_for = person_data.get('worksFor', [])
            if works_for and isinstance(works_for, list):
                # Get the most recent position (first in list)
                current_job = works_for[0]
                if isinstance(current_job, dict):
                    current_company = current_job.get('name', '')
                    member = current_job.get('member', {})
                    if isinstance(member, dict):
                        current_position = member.get('description', '')
            
            # If we have job titles from schema, use the first one as current position
            if job_titles and not current_position:
                current_position = job_titles[0]
            
            # Extract education (only actual educational institutions, not work experience)
            education = []
            experience = []
            alumni_of = person_data.get('alumniOf', [])
            
            for item in alumni_of:
                if isinstance(item, dict):
                    item_type = item.get('@type', '')
                    item_name = item.get('name', '')
                    
                    # Check if this is actually an educational institution
                    if item_type == 'EducationalOrganization':
                        # This is actual education
                        edu_info = {
                            'institution': item_name,
                            'url': item.get('url', ''),
                            'location': item.get('location', ''),
                            'start_date': None,
                            'end_date': None,
                            'description': '',
                            'type': 'education'
                        }
                        
                        member = item.get('member', {})
                        if isinstance(member, dict):
                            edu_info['start_date'] = member.get('startDate', '')
                            edu_info['end_date'] = member.get('endDate', '')
                            edu_info['description'] = member.get('description', '')
                        
                        education.append(edu_info)
                    else:
                        # This is work experience that LinkedIn incorrectly put in alumniOf
                        exp_info = {
                            'company': item_name,
                            'url': item.get('url', ''),
                            'location': item.get('location', ''),
                            'start_date': None,
                            'end_date': None,
                            'description': '',
                            'type': 'work_experience'
                        }
                        
                        member = item.get('member', {})
                        if isinstance(member, dict):
                            exp_info['start_date'] = member.get('startDate', '')
                            exp_info['end_date'] = member.get('endDate', '')
                            exp_info['description'] = member.get('description', '')
                        
                        experience.append(exp_info)
            
            # Extract work experience from worksFor (add to existing experience)
            for job in works_for:
                if isinstance(job, dict):
                    job_info = {
                        'company': job.get('name', ''),
                        'url': job.get('url', ''),
                        'location': job.get('location', ''),
                        'start_date': None,
                        'end_date': None,
                        'description': '',
                        'type': 'work_experience'
                    }
                    
                    member = job.get('member', {})
                    if isinstance(member, dict):
                        job_info['start_date'] = member.get('startDate', '')
                        job_info['end_date'] = member.get('endDate', '')
                        job_info['description'] = member.get('description', '')
                    
                    experience.append(job_info)
            
            # Extract skills - LinkedIn skills are unreliable, so we'll skip this
            # The skills extraction from HTML often produces garbage data
            # It's better to leave skills empty than to have incorrect data
            skills = []
            
            # Extract followers count
            followers_count = None
            interaction_stats = person_data.get('interactionStatistic', {})
            if isinstance(interaction_stats, dict) and interaction_stats.get('name') == 'Follows':
                followers_count = interaction_stats.get('userInteractionCount')
            elif isinstance(interaction_stats, list):
                for stat in interaction_stats:
                    if isinstance(stat, dict) and stat.get('name') == 'Follows':
                        followers_count = stat.get('userInteractionCount')
                        break
            
            # Extract profile image
            profile_image_url = None
            image = person_data.get('image', {})
            if isinstance(image, dict):
                profile_image_url = image.get('contentUrl', '')
            
            # Extract awards
            awards = person_data.get('awards', [])
            if isinstance(awards, str):
                awards = [awards]
            
            # Extract memberOf (organizations/clubs)
            member_of = person_data.get('memberOf', [])
            if isinstance(member_of, dict):
                member_of = [member_of]
            
            # Extract description
            description = person_data.get('description', '')
            
            # After collecting all experience, set current position/company from most recent ongoing experience if missing
            if (not current_position or not current_company) and experience:
                # Find the most recent experience with no end_date
                ongoing = [exp for exp in experience if not exp.get('end_date')]
                if ongoing:
                    # Use the first ongoing experience (most recent)
                    most_recent = ongoing[0]
                    if not current_position:
                        current_position = most_recent.get('title', '')
                    if not current_company:
                        current_company = most_recent.get('company', '')
            
            # Final fallback: if we still don't have current position, try to get it from experience
            if not current_position and experience:
                # Find the most recent ongoing experience
                ongoing_experiences = [exp for exp in experience if not exp.get('end_date')]
                if ongoing_experiences:
                    # Look for a title field in the experience
                    most_recent = ongoing_experiences[0]
                    if 'title' in most_recent:
                        current_position = most_recent['title']
                    elif 'position' in most_recent:
                        current_position = most_recent['position']
            
            return LinkedInProfileSchema(
                linkedin_url=profile_url,
                name=name,
                title=title,
                job_titles=job_titles,
                location=location,
                languages=languages,
                current_company=current_company,
                current_position=current_position,
                education=education,
                experience=experience,
                skills=skills,
                followers_count=followers_count,
                profile_image_url=profile_image_url,
                awards=awards,
                member_of=member_of,
                description=description,
                scraped_at=datetime.now(),
                raw_schema=schema_data
            )
            
        except Exception as e:
            logger.error(f"Error parsing profile schema: {e}")
            raise
    
    def _extract_person_data(self, schema_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract person data from the schema structure.
        
        Args:
            schema_data: The parsed JSON-LD schema data
            
        Returns:
            Person data dictionary or None
        """
        try:
            # Check for @graph structure
            if '@graph' in schema_data:
                graph = schema_data['@graph']
                for item in graph:
                    if isinstance(item, dict) and item.get('@type') == 'Person':
                        return item
            
            # Check for direct Person type
            if schema_data.get('@type') == 'Person':
                return schema_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting person data: {e}")
            return None
    
    def _extract_skills_from_description(self, description: str) -> List[str]:
        """
        Extract skills from description text.
        
        Args:
            description: The description text
            
        Returns:
            List of skills
        """
        try:
            # Simple skill extraction - can be enhanced with more sophisticated parsing
            skills = []
            
            # Look for common skill patterns
            skill_patterns = [
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Capitalized words
                r'([A-Z]{2,})',  # Acronyms
            ]
            
            for pattern in skill_patterns:
                matches = re.findall(pattern, description)
                skills.extend(matches)
            
            # Remove duplicates and common words
            common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
            skills = [skill for skill in skills if skill.lower() not in common_words and len(skill) > 2]
            
            return list(set(skills))[:10]  # Limit to 10 skills
            
        except Exception as e:
            logger.error(f"Error extracting skills: {e}")
            return []
    
    def to_postgres_dict(self, profile_schema: LinkedInProfileSchema) -> Dict[str, Any]:
        """
        Convert LinkedInProfileSchema to PostgreSQL-ready dictionary.
        
        Args:
            profile_schema: The LinkedInProfileSchema object
            
        Returns:
            Dictionary ready for PostgreSQL insertion
        """
        try:
            return {
                'linkedin_url': profile_schema.linkedin_url,
                'name': profile_schema.name,
                'title': profile_schema.title,
                'job_titles': json.dumps(profile_schema.job_titles),
                'location': profile_schema.location,
                'languages': json.dumps(profile_schema.languages),
                'current_company': profile_schema.current_company,
                'current_position': profile_schema.current_position,
                'education': json.dumps(profile_schema.education),
                'experience': json.dumps(profile_schema.experience),
                'skills': json.dumps(profile_schema.skills),
                'followers_count': profile_schema.followers_count,
                'profile_image_url': profile_schema.profile_image_url,
                'awards': json.dumps(profile_schema.awards),
                'member_of': json.dumps(profile_schema.member_of),
                'description': profile_schema.description,
                'scraped_at': profile_schema.scraped_at.isoformat(),
                'raw_schema': json.dumps(profile_schema.raw_schema)
            }
            
        except Exception as e:
            logger.error(f"Error converting to PostgreSQL format: {e}")
            raise
    
    def save_to_json(self, profile_schema: LinkedInProfileSchema, filename: str):
        """
        Save LinkedInProfileSchema to JSON file.
        
        Args:
            profile_schema: The LinkedInProfileSchema object
            filename: Output filename
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(asdict(profile_schema), f, indent=2, default=str, ensure_ascii=False)
            logger.info(f"Schema data saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving schema data: {e}")
    
    def _supplement_with_html_scraping(self, soup: BeautifulSoup, profile_schema: LinkedInProfileSchema):
        """
        Supplement profile data by scraping HTML directly for missing information.
        
        Args:
            soup: BeautifulSoup object of the page
            profile_schema: LinkedInProfileSchema to supplement
        """
        try:
            # Extract name if not already set
            if profile_schema.name == "Unknown":
                profile_schema.name = self._extract_name_from_html(soup)
            
            # Extract title/headline if not already set
            if not profile_schema.title:
                profile_schema.title = self._extract_title_from_html(soup)
            
            # Extract headline/job titles if not already set
            if not profile_schema.job_titles:
                profile_schema.job_titles = self._extract_job_titles_from_html(soup)
            
            # Extract location if not already set
            if not profile_schema.location:
                profile_schema.location = self._extract_location_from_html(soup)
            
            # Extract about/description if not already set
            if not profile_schema.description:
                profile_schema.description = self._extract_about_from_html(soup)
            
            # Extract education from HTML (supplement existing data)
            html_education = self._extract_education_from_html(soup)
            if html_education:
                # Merge with existing education data, avoiding duplicates
                existing_institutions = {edu.get('institution', '').lower() for edu in profile_schema.education}
                for edu in html_education:
                    if edu.get('institution', '').lower() not in existing_institutions:
                        profile_schema.education.append(edu)
            
            # Extract experience from HTML (supplement existing data)
            html_experience = self._extract_experience_from_html(soup)
            if html_experience:
                # Merge with existing experience data, avoiding duplicates
                existing_companies = {exp.get('company', '').lower() for exp in profile_schema.experience}
                for exp in html_experience:
                    if exp.get('company', '').lower() not in existing_companies:
                        profile_schema.experience.append(exp)
            
            # Extract volunteering
            volunteering = self._extract_volunteering_from_html(soup)
            if volunteering:
                # Add volunteering as experience entries with type 'volunteering'
                for vol in volunteering:
                    vol['type'] = 'volunteering'
                    profile_schema.experience.append(vol)
            
            # Extract certifications
            certifications = self._extract_certifications_from_html(soup)
            if certifications:
                # Add certifications as education entries with type 'certification'
                for cert in certifications:
                    cert['type'] = 'certification'
                    profile_schema.education.append(cert)
            
            # Extract languages if not already set
            if not profile_schema.languages:
                profile_schema.languages = self._extract_languages_from_html(soup)
            
            # Extract current company/position if not already set
            if not profile_schema.current_company or not profile_schema.current_position:
                current_job = self._extract_current_job_from_html(soup)
                if current_job:
                    if not profile_schema.current_company:
                        profile_schema.current_company = current_job.get('company', '')
                    if not profile_schema.current_position:
                        profile_schema.current_position = current_job.get('position', '')
            
            # Final fallback: if we still don't have current position, try to get it from experience
            if not profile_schema.current_position and profile_schema.experience:
                # Find the most recent ongoing experience
                ongoing_experiences = [exp for exp in profile_schema.experience if not exp.get('end_date')]
                if ongoing_experiences:
                    # Look for a title field in the experience
                    most_recent = ongoing_experiences[0]
                    if 'title' in most_recent:
                        profile_schema.current_position = most_recent['title']
                    elif 'position' in most_recent:
                        profile_schema.current_position = most_recent['position']
            
        except Exception as e:
            logger.error(f"Error supplementing with HTML scraping: {e}")
    
    def _extract_name_from_html(self, soup: BeautifulSoup) -> str:
        """Extract name from HTML."""
        try:
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
                    if name and len(name) > 0 and len(name) < 100:
                        return name
            
            return "Unknown"
        except Exception as e:
            logger.error(f"Error extracting name from HTML: {e}")
            return "Unknown"
    
    def _extract_title_from_html(self, soup: BeautifulSoup) -> str:
        """Extract title from HTML."""
        try:
            selectors = [
                '.top-card-layout__headline',
                '.pv-top-card__headline',
                '.pv-text-details__left-panel .text-body-medium',
                '.pv-top-card--list-bullet .text-body-medium',
                'h2.top-card-layout__headline',
                '.text-heading-medium'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text().strip()
                    if title and len(title) > 0 and len(title) < 500:
                        return title
            
            return ""
        except Exception as e:
            logger.error(f"Error extracting title from HTML: {e}")
            return ""
    
    def _extract_job_titles_from_html(self, soup: BeautifulSoup) -> List[str]:
        """Extract job titles from HTML."""
        try:
            titles = []
            selectors = [
                '.text-body-medium.break-words',
                '.pv-text-details__left-panel .text-body-medium',
                '.pv-top-card--list-bullet .text-body-medium',
                '[data-section="headline"]',
                '.pv-top-card .text-body-medium',
                '.pv-top-card__headline'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    title = element.get_text().strip()
                    if title and title not in titles:
                        titles.append(title)
            
            return titles
        except Exception as e:
            logger.error(f"Error extracting job titles from HTML: {e}")
            return []
    
    def _extract_location_from_html(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract location from HTML."""
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
            logger.error(f"Error extracting location from HTML: {e}")
            return None
    
    def _extract_about_from_html(self, soup: BeautifulSoup) -> str:
        """Extract about section from HTML."""
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
            
            return ""
        except Exception as e:
            logger.error(f"Error extracting about from HTML: {e}")
            return ""
    
    def _extract_education_from_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract education from HTML using data-section attributes."""
        education_list = []
        
        try:
            # Look specifically for education sections using data-section
            education_sections = soup.select('[data-section="educationsDetails"] .education__list-item')
            
            for section in education_sections:
                try:
                    # Extract institution name
                    institution_selectors = [
                        '.pvs-entity__path-node',
                        '.education__school-name',
                        '.pv-entity__school-name',
                        '.pv-entity__summary-info h3',
                        'h3',
                        '.pvs-entity__path-node span'
                    ]
                    
                    institution = ""
                    for selector in institution_selectors:
                        institution_element = section.select_one(selector)
                        if institution_element:
                            institution = institution_element.get_text().strip()
                            if institution and len(institution) > 2:
                                break
                    
                    # Extract degree/major
                    degree_selectors = [
                        '[data-section="educations"]',
                        '.pv-entity__degree-name',
                        '.pv-entity__secondary-title',
                        '.pvs-entity__path-node + span',
                        '.pvs-entity__path-node span'
                    ]
                    
                    degree = ""
                    for selector in degree_selectors:
                        degree_element = section.select_one(selector)
                        if degree_element:
                            degree = degree_element.get_text().strip()
                            if degree and len(degree) > 2:
                                break
                    
                    # Extract duration
                    duration_selectors = [
                        '.pvs-entity__caption-wrapper',
                        '.education__duration',
                        '.pv-entity__dates',
                        '.pv-entity__date-range'
                    ]
                    
                    duration = ""
                    for selector in duration_selectors:
                        duration_element = section.select_one(selector)
                        if duration_element:
                            duration = duration_element.get_text().strip()
                            if duration:
                                break
                    
                    # Extract description
                    description_selectors = [
                        '.pvs-entity__description',
                        '.education__description',
                        '.pv-entity__description',
                        '.pv-entity__extra-details'
                    ]
                    
                    description = ""
                    for selector in description_selectors:
                        description_element = section.select_one(selector)
                        if description_element:
                            description = description_element.get_text().strip()
                            if description:
                                break
                    
                    if institution:
                        education_info = {
                            'institution': institution,
                            'degree': degree,
                            'duration': duration,
                            'description': description,
                            'url': '',
                            'location': '',
                            'start_date': '',
                            'end_date': '',
                            'type': 'education'
                        }
                        education_list.append(education_info)
                    
                except Exception as e:
                    logger.error(f"Error extracting individual education: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting education from HTML: {e}")
        
        return education_list
    
    def _extract_experience_from_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract experience from HTML using data-section attributes."""
        experience_list = []
        
        try:
            # Look specifically for experience sections using data-section
            experience_sections = soup.select('[data-section="experience"] .pvs-list__item--line-separated')
            
            for section in experience_sections:
                try:
                    # Extract company name
                    company_selectors = [
                        '.pvs-entity__path-node',
                        '.experience__company-name',
                        '.pv-entity__company-name',
                        '.pv-entity__summary-info h3',
                        'h3',
                        '.pvs-entity__path-node span'
                    ]
                    
                    company = ""
                    for selector in company_selectors:
                        company_element = section.select_one(selector)
                        if company_element:
                            company = company_element.get_text().strip()
                            if company and len(company) > 2:
                                break
                    
                    # Extract job title
                    title_selectors = [
                        '.pvs-entity__path-node + span',
                        '.pvs-entity__path-node span',
                        '.pv-entity__summary-info h4',
                        '.pv-entity__title',
                        'h4'
                    ]
                    
                    title = ""
                    for selector in title_selectors:
                        title_element = section.select_one(selector)
                        if title_element:
                            title = title_element.get_text().strip()
                            if title and len(title) > 2:
                                break
                    
                    # Extract duration
                    duration_selectors = [
                        '.pvs-entity__caption-wrapper',
                        '.experience__duration',
                        '.pv-entity__dates',
                        '.pv-entity__date-range'
                    ]
                    
                    duration = ""
                    for selector in duration_selectors:
                        duration_element = section.select_one(selector)
                        if duration_element:
                            duration = duration_element.get_text().strip()
                            if duration:
                                break
                    
                    # Extract description
                    description_selectors = [
                        '.pvs-entity__description',
                        '.experience__description',
                        '.pv-entity__description',
                        '.pv-entity__extra-details'
                    ]
                    
                    description = ""
                    for selector in description_selectors:
                        description_element = section.select_one(selector)
                        if description_element:
                            description = description_element.get_text().strip()
                            if description:
                                break
                    
                    if company or title:
                        experience_info = {
                            'company': company,
                            'title': title,
                            'duration': duration,
                            'description': description,
                            'url': '',
                            'location': '',
                            'start_date': '',
                            'end_date': '',
                            'type': 'work_experience'
                        }
                        experience_list.append(experience_info)
                    
                except Exception as e:
                    logger.error(f"Error extracting individual experience: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting experience from HTML: {e}")
        
        return experience_list
    
    def _extract_volunteering_from_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract volunteering from HTML."""
        volunteering_list = []
        
        try:
            # Look for volunteering sections
            volunteering_sections = soup.select('[data-section="volunteering"] .pvs-list__item--line-separated, .volunteering__organization-name')
            
            for section in volunteering_sections:
                try:
                    # Extract organization name
                    org_element = section.select_one('.pvs-entity__path-node, .volunteering__organization-name')
                    organization = org_element.get_text().strip() if org_element else ""
                    
                    # Extract role
                    role_element = section.select_one('.pvs-entity__path-node + span, .volunteering__role')
                    role = role_element.get_text().strip() if role_element else ""
                    
                    # Extract duration
                    duration_element = section.select_one('.pvs-entity__caption-wrapper, .volunteering__duration')
                    duration = duration_element.get_text().strip() if duration_element else ""
                    
                    # Extract description
                    description_element = section.select_one('.pvs-entity__description, .volunteering__description')
                    description = description_element.get_text().strip() if description_element else ""
                    
                    if organization or role:
                        volunteering_info = {
                            'company': organization,
                            'title': role,
                            'duration': duration,
                            'description': description,
                            'url': '',
                            'location': '',
                            'start_date': '',
                            'end_date': '',
                            'type': 'volunteering'
                        }
                        volunteering_list.append(volunteering_info)
                    
                except Exception as e:
                    logger.error(f"Error extracting individual volunteering: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting volunteering from HTML: {e}")
        
        return volunteering_list
    
    def _extract_skills_from_html(self, soup: BeautifulSoup) -> List[str]:
        """Extract skills from HTML."""
        skills_list = []
        
        try:
            # Look for skills sections
            skills_elements = soup.select('[data-section="skills"] .pvs-list__item--line-separated, .skill-categories-section .pvs-list__item--line-separated')
            
            for element in skills_elements:
                try:
                    skill_text = element.get_text().strip()
                    if skill_text and len(skill_text) < 100 and skill_text not in skills_list:
                        skills_list.append(skill_text)
                except Exception as e:
                    logger.error(f"Error extracting individual skill: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting skills from HTML: {e}")
        
        return skills_list
    
    def _extract_certifications_from_html(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract certifications from HTML."""
        certifications_list = []
        
        try:
            # Look for certifications sections
            cert_sections = soup.select('[data-section="certifications"] .pvs-list__item--line-separated, .certification__name')
            
            for section in cert_sections:
                try:
                    # Extract certification name
                    cert_element = section.select_one('.pvs-entity__path-node, .certification__name')
                    cert_name = cert_element.get_text().strip() if cert_element else ""
                    
                    # Extract issuing organization
                    org_element = section.select_one('.pvs-entity__path-node + span, .certification__issuer')
                    issuer = org_element.get_text().strip() if org_element else ""
                    
                    # Extract date
                    date_element = section.select_one('.pvs-entity__caption-wrapper, .certification__date')
                    date = date_element.get_text().strip() if date_element else ""
                    
                    if cert_name:
                        cert_info = {
                            'institution': issuer,
                            'degree': cert_name,
                            'duration': date,
                            'description': '',
                            'url': '',
                            'location': '',
                            'start_date': '',
                            'end_date': '',
                            'type': 'certification'
                        }
                        certifications_list.append(cert_info)
                    
                except Exception as e:
                    logger.error(f"Error extracting individual certification: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting certifications from HTML: {e}")
        
        return certifications_list
    
    def _extract_languages_from_html(self, soup: BeautifulSoup) -> List[str]:
        """Extract languages from HTML."""
        languages_list = []
        
        try:
            # Look for languages sections
            language_elements = soup.select('[data-section="languages"] .pvs-list__item--line-separated, .language__name')
            
            for element in language_elements:
                try:
                    language_text = element.get_text().strip()
                    if language_text and language_text not in languages_list:
                        languages_list.append(language_text)
                except Exception as e:
                    logger.error(f"Error extracting individual language: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting languages from HTML: {e}")
        
        return languages_list
    
    def _extract_current_job_from_html(self, soup: BeautifulSoup) -> Optional[Dict[str, str]]:
        """Extract current job from HTML."""
        try:
            # Look for current position in the top card - multiple strategies
            current_job_selectors = [
                '.pv-top-card__experience-list .pv-top-card__experience-list-item',
                '.pv-top-card__experience-list .pvs-list__item--line-separated',
                '.pv-top-card .text-body-medium',
                '.pv-top-card__headline',
                '.pv-text-details__left-panel .text-body-medium',
                '.pv-top-card--list-bullet .text-body-medium'
            ]
            
            for selector in current_job_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text().strip()
                    if text and len(text) > 3:
                        # Try to parse "Position at Company" format
                        if ' at ' in text:
                            parts = text.split(' at ')
                            if len(parts) >= 2:
                                return {
                                    'position': parts[0].strip(),
                                    'company': parts[1].strip()
                                }
                        # If no "at" found, this might be just the position
                        else:
                            return {
                                'position': text,
                                'company': ''
                            }
            
            # Alternative: look for job title in the headline area
            headline_selectors = [
                '.pv-top-card__headline',
                '.pv-text-details__left-panel .text-body-medium',
                '.pv-top-card--list-bullet .text-body-medium'
            ]
            
            for selector in headline_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text().strip()
                    if text and len(text) > 3:
                        return {
                            'position': text,
                            'company': ''
                        }
            
            return None
        except Exception as e:
            logger.error(f"Error extracting current job from HTML: {e}")
            return None

def main():
    """Example usage of the LinkedInSchemaParser."""
    # Example usage
    parser = LinkedInSchemaParser()
    
    # You would typically load this from a scraped HTML file
    # with open('linkedin_attempt_XX_YYYYMMDD_HHMMSS.html', 'r', encoding='utf-8') as f:
    #     html_content = f.read()
    
    # For demonstration, we'll use a placeholder
    html_content = """
    <script type="application/ld+json">
    {"@context":"http://schema.org","@graph":[{"@type":"WebPage","reviewedBy":{"@type":"Person","name":"Jason Xie"},"url":"https://www.linkedin.com/in/jasonagxie"},{"@context":"http://schema.org","@type":"Person","address":{"@type":"PostalAddress","addressCountry":"US","addressLocality":"New York, New York, United States"},"alumniOf":[{"@type":"Organization","name":"Columbia University Irving Medical Center","url":"https://www.linkedin.com/company/columbiamed","location":"New York, United States","member":{"@type":"OrganizationRole","description":"Prof. Yufeng Shen's Lab","startDate":"2024-06","endDate":"2024-08"}}],"name":"Jason Xie","sameAs":"https://www.linkedin.com/in/jasonagxie","url":"https://www.linkedin.com/in/jasonagxie","worksFor":[{"@type":"Organization","name":"InstaLILY AI","url":"https://www.linkedin.com/company/instalily","location":"New York, United States","member":{"@type":"OrganizationRole","startDate":"2025-05"}}],"interactionStatistic":{"@type":"InteractionCounter","interactionType":"https://schema.org/FollowAction","name":"Follows","userInteractionCount":800}}]}
    </script>
    """
    
    profile_url = "https://www.linkedin.com/in/jasonagxie"
    
    # Parse the schema
    profile_schema = parser.extract_schema_from_html(html_content, profile_url)
    
    if profile_schema:
        print("✅ Successfully parsed LinkedIn schema!")
        print(f"Name: {profile_schema.name}")
        print(f"Job Titles: {profile_schema.job_titles}")
        print(f"Location: {profile_schema.location}")
        print(f"Languages: {profile_schema.languages}")
        print(f"Current Company: {profile_schema.current_company}")
        print(f"Followers: {profile_schema.followers_count}")
        
        # Convert to PostgreSQL format
        pg_dict = parser.to_postgres_dict(profile_schema)
        print(f"\nPostgreSQL-ready data:")
        for key, value in pg_dict.items():
            if key != 'raw_schema':  # Skip the large raw schema for display
                print(f"  {key}: {value}")
        
        # Save to JSON file
        parser.save_to_json(profile_schema, 'linkedin_schema_data.json')
    else:
        print("❌ Failed to parse LinkedIn schema")

if __name__ == "__main__":
    main() 