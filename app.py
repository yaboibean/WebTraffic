import streamlit as st
import pandas as pd
import requests
import time
import os
import tempfile
import sqlite3
from datetime import datetime
import re
import json
import sys
import threading
from contextlib import contextmanager
import io
from io import StringIO

###########################
# Print Capture Utilities #
###########################

class PrintCapture(io.StringIO):
    """Capture all print statements to a buffer."""
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
    def write(self, s):
        with self.lock:
            super().write(s)
    def getvalue(self):
        with self.lock:
            return super().getvalue()

@contextmanager
def capture_prints():
    """Context manager to capture all prints to a buffer."""
    old_stdout = sys.stdout
    buffer = PrintCapture()
    sys.stdout = buffer
    try:
        yield buffer
    finally:
        sys.stdout = old_stdout

# Page config
st.set_page_config(
    page_title="InstaLILY Lead Qualification Tool",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
PERPLEXITY_API_KEY = st.secrets.get("PERPLEXITY_API_KEY", "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")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# Database setup
def init_database():
    """Initialize SQLite database for storing results"""
    conn = sqlite3.connect('qualification_results.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            filename TEXT,
            total_rows INTEGER,
            qualified_count INTEGER,
            qualification_rate REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qualified_visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER,
            first_name TEXT,
            last_name TEXT,
            title TEXT,
            company_name TEXT,
            industry TEXT,
            email TEXT,
            website TEXT,
            qualification_score REAL,
            notes TEXT,
            email_draft TEXT,
            FOREIGN KEY (analysis_id) REFERENCES analyses (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_analysis_results(filename, df):
    """Save analysis results to database"""
    conn = sqlite3.connect('qualification_results.db')
    cursor = conn.cursor()
    
    # Insert analysis record
    qualified_count = df['Qualified'].sum()
    total_rows = len(df)
    qualification_rate = qualified_count / total_rows if total_rows > 0 else 0
    
    cursor.execute('''
        INSERT INTO analyses (timestamp, filename, total_rows, qualified_count, qualification_rate)
        VALUES (?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), filename, total_rows, qualified_count, qualification_rate))
    
    analysis_id = cursor.lastrowid
    
    # Insert qualified visitors
    qualified_df = df[df['Qualified'] == True]
    for _, row in qualified_df.iterrows():
        cursor.execute('''
            INSERT INTO qualified_visitors 
            (analysis_id, first_name, last_name, title, company_name, industry, email, website, qualification_score, notes, email_draft)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis_id,
            row.get('FirstName', ''),
            row.get('LastName', ''),
            row.get('Title', ''),
            row.get('CompanyName', ''),
            row.get('Industry', ''),
            row.get('Email', ''),
            row.get('Website', ''),
            float(row.get('Score', 0)) if row.get('Score', '').replace('.', '').isdigit() else 0,
            row.get('Notes', ''),
            row.get('EmailDraft', '')
        ))
    
    conn.commit()
    conn.close()
    return analysis_id

def get_past_analyses():
    """Retrieve past analyses from database"""
    conn = sqlite3.connect('qualification_results.db')
    
    query = '''
        SELECT a.*, COUNT(qv.id) as qualified_visitors_count
        FROM analyses a
        LEFT JOIN qualified_visitors qv ON a.id = qv.analysis_id
        GROUP BY a.id
        ORDER BY a.timestamp DESC
    '''
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_qualified_visitors(analysis_id):
    """Get qualified visitors for a specific analysis"""
    conn = sqlite3.connect('qualification_results.db')
    
    query = '''
        SELECT * FROM qualified_visitors 
        WHERE analysis_id = ?
        ORDER BY qualification_score DESC
    '''
    
    df = pd.read_sql_query(query, conn, params=(analysis_id,))
    conn.close()
    return df

# Qualification functions (adapted from original script)
def is_valid_data(value):
    """Check if a value is valid (not nan, N/A, or empty)"""
    if pd.isna(value):
        return False
    str_val = str(value).strip().lower()
    return str_val not in ['nan', 'n/a', '', 'none']

def extract_rationale(text):
    """Extract comprehensive rationale from Perplexity response"""
    lines = text.split('\n')
    key_points = []
    
    for line in lines[1:]:  # Skip the Yes/No line
        line = line.strip()
        if line and len(line) > 15 and not line.startswith('Score:') and '---' not in line:
            line = line.lstrip('•-* ').strip()
            if any(keyword in line.lower() for keyword in ['company', 'role', 'industry', 'experience', 'decision', 'revenue', 'size', 'potential', 'fit', 'budget', 'authority', 'need', 'timeline', 'qualified', 'unqualified', 'because', 'however', 'although', 'likely', 'strong', 'weak']):
                key_points.append(line)
            if len(key_points) >= 4:
                break
    
    if key_points:
        rationale = " | ".join(key_points)
        if len(rationale) > 400:
            rationale = rationale[:397] + "..."
        return rationale
    else:
        text_clean = text.replace('\n', ' ').strip()
        if len(text_clean) > 100:
            return text_clean[:397] + "..." if len(text_clean) > 400 else text_clean
        return "Analysis completed - see detailed response above"

def draft_email_with_openai(email_prompt):
    """Draft email using OpenAI API"""
    try:
        if not OPENAI_API_KEY:
            return ""
        
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": email_prompt}],
            max_tokens=200,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        return ""

def qualify_visitor(row, progress_bar, current_idx, total_count):
    """Qualify a single visitor using Perplexity AI"""
    
    # Build visitor details with only valid data
    visitor_details = []
    
    if is_valid_data(row.get('Title')):
        visitor_details.append(f"- Title: {row.get('Title')}")
    if is_valid_data(row.get('FirstName')):
        visitor_details.append(f"- First Name: {row.get('FirstName')}")
    if is_valid_data(row.get('LastName')):
        visitor_details.append(f"- Last Name: {row.get('LastName')}")
    if is_valid_data(row.get('Email')):
        visitor_details.append(f"- Email: {row.get('Email')}")
    if is_valid_data(row.get('CompanyName')):
        visitor_details.append(f"- Company: {row.get('CompanyName')}")
    if is_valid_data(row.get('Industry')):
        visitor_details.append(f"- Industry: {row.get('Industry')}")
    if is_valid_data(row.get('Website')):
        visitor_details.append(f"- Website: {row.get('Website')}")
    if is_valid_data(row.get('Country')):
        visitor_details.append(f"- Country: {row.get('Country')}")
    
    visitor_details_text = "\n".join(visitor_details) if visitor_details else "Limited visitor information available"
    
    company = row.get('CompanyName', 'N/A')
    industry = row.get('Industry', 'N/A')
    website = row.get('Website', 'N/A')
    
    qualification_prompt = f"""
As you research, you will visit the following websites and sources:
- Company website: {website if is_valid_data(website) else 'Not available'}
- Google searches for company news and background
- Professional profile verification
- Industry analysis sources

CURRENT RESEARCH TARGET:
{company}{f' in {industry}' if is_valid_data(industry) else ''}

Evaluate the following website visitor to determine if InstaLILY should reach out to them as a potential client.

Firstly some context: this is a website visitor that has been identified as a potential lead for InstaLILY, a B2B SaaS company that provides AI-driven solutions for various industries. We are trying to figure out if they are a good fit for InstaLILY and if we should reach out to them.

Be aware of the intent of the visitor, and put it into 3 categories: Investor, student/looking for a job, or potential customer. If they are an investor or student, they are not qualified. If they are a potential customer, we will evaluate them based on the following criteria.

Visitor Details from RB2B:
{visitor_details_text}

Just a few of the industries that InstaLILY likes to work with are: Healthcare Distribution, Industrial/Construction/Distribution, Automotive (OEM/Fleet/Parts), Food & Beverage Distribution, and PE Operating roles. These are ideals, not requirements. These are just the top industries we are targeting, but we are more than open to other industries if the visitor meets the other criteria. Don't place too much negative weight on the industry, this means that if the industry does not line up, don't dock too many points, but if it does line up, give a lot of points. All of these are very broad, and can be interpreted in many ways, so use your best judgement to determine if the visitor is a good fit for InstaLILY.

In the case of ambiguous or missing data, search online to fill in the gaps. Use the companies website, and any other sources you can find to get a better understanding of the company and the visitor.

InstaLILY's business model is to provide AI-driven solutions that help businesses in these industries (and others) optimize their operations, improve efficiency, and drive growth. We are looking for visitors who have an interest in leveraging AI technology to enhance their business processes.

Also keep in mind that some of the information given could be wrong, so you need to do your own research to verify it

If you find that for example the industry isn't perfect, but the title is right, you will need to restart the evaluation based on the new information you found.

Remember, the person and company do not have to currently be working with AI.

While you are evaluating the visitor/company, do a very very deep search for any news on both the company and the visitor. Look for any recent news, press releases, or social media activity that might indicate their current business focus, challenges, or interests. This will help you better understand their potential fit with InstaLILY. Feel free to use any sources you can find, including Google, news articles, etc. and any other sources you can find. If you cannot find any information, do not qualify them. Reddit is also a great source for finding information about the company and the visitor, so be sure to check there as well.

When you are researching you must search the following: 
- [company name] + [industry] + "news" to find any recent news about the company
- what does [company name] do? to find the company's website and any other information you can find.
- [first name] + [last name] + [company name] to find the visitor's professional profile.
- [company name] + [industry] to find the company's website and any other information you can find.

A visitor is considered QUALIFIED if:
1. They are in or adjacent to ICP industries (if other categories are met, even non-ICP may qualify).
2. They hold a somewhat senior/strategic title. Lower-level roles are OK only if the other categories are met 
3. They show strong buying intent (multiple sessions, career page visits). This is the least important of the three.

Conduct very very deep analysis to judge company/role fit. Take your time to evaluate the company using all available sources, and do not rush this process. 

If a company does something remotely similar to what InstaLILY does, they are a competitor, and they are not qualified, and this immediately disqualifies them. And also keep in mind that they might not be targeting the same industries as InstaLILY, but if they have a similar mission of modernizing other companies (B2B), they are a competitor.

Return only:
- Yes or No
- Many short bullet points with information based on industry, title, seniority, and any override logic
- A short summary of the visitor's profile
- A short summary of the company
- A score 1–10 of how qualified they are: formatted like "Score: 5"
- A small section on their past experiences (based on your research)

The visitor doesn't need to currently be making an effort to adopt AI, but rather have a business that could benefit from AI.

While you are completing this, something that you should be thinking as you evaluate each company, is 'would this company benefit from InstaLILY's services', because they don't already have to be adopting AI services right now, in fact, the more outdated the better! Keep in mind, InstaLILY helps companies modernize their operations, and improve their efficiency.

Another thing you NEED to watch out for is whether the visitor is a competitor, trying to scope out InstaLILY. In order to know if they are a competitor, you need to conduct a very very deep search about the company online and use as many sources you can find. This also requires you to do some research, but it is very important. If they are a competitor, they are not qualified, and you should say so in your response. This means you also have to have a deep understanding of InstaLILY's business model, and products. With this said though, they still can be doing some stuff with AI already.

Be sure that you understand both InstaLILY's business model and ICPs, as well as the visitor's profile. If you are not sure, do not qualify them. Make sure that they would be a good fit for InstaLILY, and that they are not a competitor. If you are not sure, do not qualify them.

Keep in mind, the more people we can qualify, the better, but if they are not a good fit, we should not waste time on them. Be very thorough in your analysis.

You should aim to qualify between 25 and 35% of the visitors.

Do not include citations!

Make sure you start with either a "Yes" or a "No" indicating whether or not the person and company is qualified. If they are qualified, say "Yes" as the first words, and if they are not, say "No"

Finally, If you select someone, you should be 100% confident that they could work well with InstaLILY and align well with what we do. The more people that we can qualify the better.

Don't use any bold text or italic.

Take as much time as you need to evaluate the visitor and company, and be very thorough in your analysis. Find every single known piece of information about them that you can, whether it is from their website, social media, linkedin, news articles, or any other sources. The more information you can find, the better your analysis will be.

Remember, the industry is a very important factor, but it is very loose.The industry is very broad, and can be interpreted in many ways, so use your best judgement to determine if the visitor is a good fit for InstaLILY.

Also keep in mind that for a little company, they might not be able to afford InstaLILY. This means that larger companies are more likely to be qualified, but smaller companies can also be qualified if they meet the other criteria.

Even if a company is big and might have access to AI, they might still be a good fit for InstaLILY. The name of the game is that we wont know unless we talk to them, so the more we can qualify, the better. But with that said, we dont want to waste time on people that are not a good fit, so be very thorough in your analysis.

Try and be extra lenient with big companies, as they are more likely to be qualified.
"""
    
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": qualification_prompt}]
    }
    
    try:
        # Update progress
        progress_bar.progress((current_idx + 1) / total_count)
        
        response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            reply = response.json()['choices'][0]['message']['content'].strip()
            is_qualified = reply.lower().startswith("yes")
            
            # Extract score
            score_match = re.search(r'score\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)', reply, re.IGNORECASE)
            score = score_match.group(1) if score_match else ""
            
            # Draft email if qualified
            email_draft = ""
            if is_qualified and OPENAI_API_KEY:
                name = row.get('FirstName', '') if is_valid_data(row.get('FirstName')) else None
                title = row.get('Title', '') if is_valid_data(row.get('Title')) else None
                company = row.get('CompanyName', '') if is_valid_data(row.get('CompanyName')) else None
                industry = row.get('Industry', '') if is_valid_data(row.get('Industry')) else None
                website = row.get('Website', '') if is_valid_data(row.get('Website')) else None
                email_addr = row.get('Email', '') if is_valid_data(row.get('Email')) else None

                visitor_info_lines = []
                if name: visitor_info_lines.append(f"- Name: {name}")
                if title: visitor_info_lines.append(f"- Title: {title}")
                if company: visitor_info_lines.append(f"- Company: {company}")
                if industry: visitor_info_lines.append(f"- Industry: {industry}")
                if website: visitor_info_lines.append(f"- Website: {website}")
                if email_addr: visitor_info_lines.append(f"- Email: {email_addr}")
                visitor_info = "\n".join(visitor_info_lines)

                email_prompt = f"""
Write a short, very formal and professional, personalized email from Sumo (co-founder of InstaLILY) to the following website visitor, based on their role and company. 
No buzzwords. Mention curiosity about what brought them to the site, and a soft offer to help. 
Mention how InstaLILY helps companies eliminate manual work and improve operations with AI.
Talk a little bit about why we could help them (specific to their company and what they do--this will require research on both InstaLILY and the company we are emailing.
The name of the game is to get them to respond, so keep it very very professional and short!! Do Not include citations!
2 sentences max!
Also be sure to keep in mind their role at the company and how that might change the email (a board member would get a different email than a director of operations, for example).
Don't make it sound like a sales email.
It is most important that the email is not salesy at all, but the first line is ultra personalized to catch their attention.

Here is the information about the visitor:
{visitor_info}

Don't use any bold text or italic.

Remember the name of the game is ultra professional, ultra polished, and ultra personalized, and very very short. Make sure you match a professional tone and make sure you are ultra professional, ultra polished, and ultra personalized.
Very formal!
"""
                email_draft = draft_email_with_openai(email_prompt)
            
            return {
                'qualified': is_qualified,
                'notes': reply,
                'score': score,
                'email_draft': email_draft,
                'rationale': extract_rationale(reply)
            }
        else:
            return {
                'qualified': False,
                'notes': f"API error: {response.status_code}",
                'score': "",
                'email_draft': "",
                'rationale': "API Error"
            }
    except Exception as e:
        return {
            'qualified': False,
            'notes': f"Exception: {str(e)}",
            'score': "",
            'email_draft': "",
            'rationale': "Processing Error"
        }

# Initialize database
init_database()

# Sidebar navigation

# Print log toggle
show_print_log = st.sidebar.checkbox("Show Print Log (Terminal Output)", value=False)
st.sidebar.title("🚀 InstaLILY Lead Qualification")
page = st.sidebar.selectbox("Choose Action", ["Upload CSV & Analyze", "View Past Results"])

print_log_buffer = st.session_state.get('print_log_buffer', None)
if print_log_buffer is None:
    print_log_buffer = PrintCapture()
    st.session_state['print_log_buffer'] = print_log_buffer

if page == "Upload CSV & Analyze":
    st.title("📊 Lead Qualification Analysis")
    st.markdown("Upload a CSV file with visitor data to qualify leads using AI-powered analysis.")
    
    # File upload
    uploaded_file = st.file_uploader(
        "Choose a CSV file", 
        type=['csv'],
        help="Upload a CSV file containing visitor data with columns like FirstName, LastName, Title, CompanyName, Industry, etc."
    )
    
    if uploaded_file is not None:
        # Capture all prints in this block
        with capture_prints() as print_buffer:
            try:
                # Read CSV
                df = pd.read_csv(uploaded_file)
                print(f"Loaded {len(df)} rows from {uploaded_file.name}")
                st.success(f"✅ Loaded {len(df)} rows from {uploaded_file.name}")
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
                print(f"Error processing file: {str(e)}")
        # Save print log to session state
        st.session_state['print_log_buffer'].write(print_buffer.getvalue())

        # Always show preview, row selection, and config
        if 'df' in locals():
            st.subheader("📋 Data Preview")
            st.dataframe(df.head(10))

            st.subheader("🎯 Select Rows to Process")
            col1, col2 = st.columns(2)
            with col1:
                process_all = st.checkbox("Process all rows", value=True)
            if not process_all:
                with col2:
                    selected_rows = st.multiselect(
                        "Select specific rows (by index)",
                        options=list(range(len(df))),
                        default=list(range(min(10, len(df))))
                    )
                    df = df.iloc[selected_rows].reset_index(drop=True)

            st.subheader("⚙️ Configuration")
            col1, col2 = st.columns(2)
            with col1:
                include_emails = st.checkbox("Generate email drafts for qualified leads", value=True)
            with col2:
                batch_size = st.selectbox("Batch size (for large datasets)", [1, 5, 10, 25, 50], index=2)

            estimated_time = len(df) * 10.1  # seconds (initial guess)
            est_minutes = int(estimated_time // 60)
            est_seconds = int(estimated_time % 60)
            time_estimate_placeholder = st.empty()
            time_estimate_placeholder.info(f"⏱️ Estimated processing time: {est_minutes}m {est_seconds}s for {len(df)} rows")

            # Process button
            if st.button("🚀 Start Analysis", type="primary"):
                if len(df) == 0:
                    st.error("No data to process!")
                else:
                    # Processing
                    st.subheader("🔄 Processing...")
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results_container = st.empty()
                    # Use the same placeholder for dynamic time estimate
                    qual_flags = []
                    notes_list = []
                    scores_list = []
                    email_drafts = []
                    rationales = []
                    start_time = time.time()
                    row_times = []
                    for idx, row in enumerate(df.itertuples(index=False)):
                        row_start = time.time()
                        # Convert row to dict for compatibility
                        if hasattr(row, '_asdict'):
                            row_dict = row._asdict()
                        else:
                            row_dict = dict(zip(df.columns, row))
                        status_text.text(f"Processing {idx + 1}/{len(df)}: {row_dict.get('FirstName', 'N/A')} {row_dict.get('LastName', 'N/A')} at {row_dict.get('CompanyName', 'N/A')}")
                        result = qualify_visitor(row_dict, progress_bar, idx, len(df))
                        qual_flags.append(result['qualified'])
                        notes_list.append(result['notes'])
                        scores_list.append(result['score'])
                        email_drafts.append(result['email_draft'] if include_emails else "")
                        rationales.append(result['rationale'])
                        # Track time for this row
                        row_time = time.time() - row_start
                        row_times.append(row_time)
                        avg_time = sum(row_times) / len(row_times)
                        rows_left = len(df) - (idx + 1)
                        est_time_left = avg_time * rows_left
                        est_minutes = int(est_time_left // 60)
                        est_seconds = int(est_time_left % 60)
                        # Replace static estimate with dynamic one
                        time_estimate_placeholder.info(f"⏱️ Estimated time remaining: {est_minutes}m {est_seconds}s (avg {int(round(avg_time))}s/row, {rows_left} left)")
                        # Show live results
                        qualified_count = sum(qual_flags)
                        with results_container.container():
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Processed", f"{idx + 1}/{len(df)}")
                            col2.metric("Qualified", qualified_count)
                            col3.metric("Rate", f"{qualified_count/(idx+1)*100:.1f}%")
                            if result['qualified']:
                                st.success(f"✅ {row_dict.get('FirstName', '')} {row_dict.get('LastName', '')} - QUALIFIED")
                                st.write(f"💭 {result['rationale']}")
                            else:
                                st.warning(f"❌ {row_dict.get('FirstName', '')} {row_dict.get('LastName', '')} - Not Qualified")
                    # Add results to dataframe
                    df['Qualified'] = qual_flags
                    df['Notes'] = notes_list
                    df['Score'] = scores_list
                    if include_emails:
                        df['EmailDraft'] = email_drafts
                    df['Rationale'] = rationales
                    # Calculate final stats
                    qualified_count = df['Qualified'].sum()
                    total_time = time.time() - start_time
                    # Save to database
                    analysis_id = save_analysis_results(uploaded_file.name, df)
                    # Display final results
                    st.subheader("🎉 Analysis Complete!")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Total Processed", len(df))
                    col2.metric("Qualified", qualified_count)
                    col3.metric("Qualification Rate", f"{qualified_count/len(df)*100:.1f}%")
                    col4.metric("Processing Time", f"{total_time/60:.1f}m")
                    # Display qualified leads
                    if qualified_count > 0:
                        st.subheader("✅ Qualified Leads")
                        qualified_df = df[df['Qualified'] == True]
                        for _, row in qualified_df.iterrows():
                            with st.expander(f"🎯 {row.get('FirstName', '')} {row.get('LastName', '')} - {row.get('CompanyName', '')}"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write("**Contact Info:**")
                                    st.write(f"Name: {row.get('FirstName', '')} {row.get('LastName', '')}")
                                    st.write(f"Title: {row.get('Title', 'N/A')}")
                                    st.write(f"Company: {row.get('CompanyName', 'N/A')}")
                                    st.write(f"Industry: {row.get('Industry', 'N/A')}")
                                    st.write(f"Email: {row.get('Email', 'N/A')}")
                                    st.write(f"Score: {row.get('Score', 'N/A')}/10")
                                with col2:
                                    if include_emails and row.get('EmailDraft'):
                                        st.write("**Draft Email:**")
                                        st.text_area("", value=row.get('EmailDraft', ''), height=100, key=f"email_{row.name}")
                                st.write("**Qualification Rationale:**")
                                st.write(row.get('Rationale', 'No rationale available'))
                    # Download results
                    csv_buffer = StringIO()
                    df.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Results CSV",
                        data=csv_buffer.getvalue(),
                        file_name=f"qualified_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )

elif page == "View Past Results":
    st.title("📈 Past Analysis Results")
    # Get past analyses
    analyses_df = get_past_analyses()
    if len(analyses_df) == 0:
        st.info("No past analyses found. Upload a CSV to get started!")
    else:
        st.subheader("📊 Analysis History")
        # Display analyses table
        display_df = analyses_df.copy()
        display_df['timestamp'] = pd.to_datetime(display_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['qualification_rate'] = (display_df['qualification_rate'] * 100).round(1).astype(str) + '%'
        # Show only the count of qualified leads in the 'Qualified' column
        if 'qualified_visitors_count' in display_df.columns:
            display_df['Qualified'] = pd.to_numeric(display_df['qualified_visitors_count'], errors='coerce').fillna(0).astype(int)
        else:
            display_df['Qualified'] = 0
        st.dataframe(
            display_df[['timestamp', 'filename', 'total_rows', 'Qualified', 'qualification_rate']].rename(columns={
                'timestamp': 'Date/Time',
                'filename': 'File Name',
                'total_rows': 'Total Rows',
                'Qualified': 'Qualified',
                'qualification_rate': 'Rate'
            }),
            use_container_width=True
        )
        
        # Select analysis to view details
        st.subheader("🔍 View Detailed Results")
        selected_analysis = st.selectbox(
            "Select an analysis to view qualified leads:",
            options=analyses_df['id'].tolist(),
            format_func=lambda x: f"{analyses_df[analyses_df['id']==x]['filename'].iloc[0]} - {analyses_df[analyses_df['id']==x]['timestamp'].iloc[0]}"
        )
        
        if selected_analysis:
            with capture_prints() as print_buffer:
                qualified_visitors = get_qualified_visitors(selected_analysis)
                if len(qualified_visitors) == 0:
                    st.info("No qualified visitors found for this analysis.")
                else:
                    st.write(f"**{len(qualified_visitors)} Qualified Leads:**")
            st.session_state['print_log_buffer'].write(print_buffer.getvalue())
            
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Qualified Leads", len(qualified_visitors))
            col2.metric("Avg Score", f"{qualified_visitors['qualification_score'].mean():.1f}/10")
            col3.metric("Industries", qualified_visitors['industry'].nunique())
            
            # Display qualified visitors
            for _, visitor in qualified_visitors.iterrows():
                with st.expander(f"🎯 {visitor['first_name']} {visitor['last_name']} - {visitor['company_name']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Contact Information:**")
                        st.write(f"**Name:** {visitor['first_name']} {visitor['last_name']}")
                        st.write(f"**Title:** {visitor['title']}")
                        st.write(f"**Company:** {visitor['company_name']}")
                        st.write(f"**Industry:** {visitor['industry']}")
                        st.write(f"**Email:** {visitor['email']}")
                        st.write(f"**Website:** {visitor['website']}")
                        st.write(f"**Score:** {visitor['qualification_score']}/10")
                    
                    with col2:
                        if visitor['email_draft']:
                            st.write("**Email Draft:**")
                            st.text_area("", value=visitor['email_draft'], height=150, key=f"past_email_{visitor['id']}")
                    
                    if visitor['notes']:
                        st.write("**Full Analysis:**")
                        st.text_area("", value=visitor['notes'], height=200, key=f"notes_{visitor['id']}")
            
            # Export qualified leads
            csv_buffer = StringIO()
            qualified_visitors.to_csv(csv_buffer, index=False)
            
            st.download_button(
                label="📥 Download Qualified Leads CSV",
                data=csv_buffer.getvalue(),
                file_name=f"qualified_leads_{selected_analysis}.csv",
                mime="text/csv"
            )

# Footer
# Show print log if enabled
if show_print_log:
    st.markdown("---")
    st.markdown("### Terminal Output (Print Log)")
    st.text_area("", value=st.session_state['print_log_buffer'].getvalue(), height=300)
st.markdown("---")
st.markdown("Potential Lead Qualification | InstaLILY 2025")
