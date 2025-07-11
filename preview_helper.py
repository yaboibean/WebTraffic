import requests
from urllib.parse import urlparse
import time

def preview_website_accessibility(urls, max_check=5):
    """Preview which websites are accessible before research"""
    print(f"\n🌐 WEBSITE ACCESSIBILITY PREVIEW (checking first {max_check}):")
    
    accessible = []
    for i, url in enumerate(urls[:max_check]):
        if not url or url == 'N/A':
            continue
            
        try:
            # Clean URL
            if not url.startswith('http'):
                url = 'https://' + url
            
            print(f"  Checking {url}...", end=" ")
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code < 400:
                print("✅ Accessible")
                accessible.append(url)
            else:
                print(f"⚠️ Status {response.status_code}")
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}...")
        
        time.sleep(0.5)  # Rate limiting
    
    print(f"\n📊 Summary: {len(accessible)}/{min(len(urls), max_check)} websites accessible")
    return accessible

def preview_research_strategy(row):
    """Show what research will be conducted for a specific row"""
    company = row.get('CompanyName', 'N/A')
    industry = row.get('Industry', 'N/A')
    name = f"{row.get('FirstName', 'N/A')} {row.get('LastName', 'N/A')}"
    
    research_plan = {
        'company_news': f'"{company}" + "{industry}" + "news" + "2024"',
        'company_description': f'"what does {company} do"',
        'person_verification': f'"{name}" + "{company}" + "LinkedIn"',
        'industry_analysis': f'"{company}" + "{industry}" + "AI" + "technology"',
        'competitive_analysis': f'"{company}" + "competitors" + "{industry}"'
    }
    
    return research_plan

def show_qualification_criteria():
    """Display the qualification criteria that will be used"""
    print("\n📋 QUALIFICATION CRITERIA PREVIEW:")
    print("✅ QUALIFIED if visitor meets:")
    print("  1. Industry fit (Healthcare Distribution, Industrial/Construction, Automotive, Food & Beverage, PE)")
    print("  2. Senior/strategic title (Director+, VP+, C-level, Manager with buying power)")
    print("  3. Company could benefit from AI automation")
    print("  4. Not a competitor to InstaLILY")
    print("  5. Not an investor, student, or job seeker")
    
    print("\n❌ DISQUALIFIED if:")
    print("  - Company does similar AI/automation services (competitor)")
    print("  - Junior role with no buying influence")
    print("  - Personal/consultant without substantial company")
    print("  - Educational institution (unless enterprise operations)")
    
    print(f"\n🎯 Target qualification rate: 25-35% of visitors")

def preview_email_strategy():
    """Show email drafting approach"""
    print("\n✉️ EMAIL DRAFTING PREVIEW:")
    print("📝 For qualified visitors, emails will:")
    print("  - Be extremely short (2 sentences max)")
    print("  - Ultra-professional and formal tone")
    print("  - Personalized to their role and company")
    print("  - Mention curiosity about their website visit")
    print("  - Soft offer to help with AI/automation")
    print("  - Signed by Sumo (co-founder)")
    print("  - No sales language or buzzwords")
