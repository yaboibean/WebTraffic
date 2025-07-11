# Complete updated code with integrated email drafting after qualification

import pandas as pd
import requests
import time
import os
import sys
import re
import tempfile
import subprocess
from utils import process_linkedin_url
from from_json import print_json
import openai

# Constants
PERPLEXITY_API_KEY = "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"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


# === Select CSVs to Process ===
folder_path = os.path.join(os.path.dirname(__file__), "Data")
csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]

if not csv_files:
    print("❌ No CSV files found in folder.")
    exit()

print("\n📄 Found the following CSV files:")
for i, fname in enumerate(csv_files):
    print(f"{i + 1}. {fname}")

def restart_program():
    print("🔄 Restarting program...\n")
    python = sys.executable
    os.execl(python, python, *sys.argv)

try:
    selection = input("Enter the numbers of the CSV files to process (comma-separated, e.g., 1,3 or 0 for all): ").strip()
    if selection == ".":
        restart_program()
    if not selection:
        print("⚠️ No selection made. Exiting.")
        exit()
    if selection == "0":
        selected_files = csv_files
    else:
        indices = [int(x.strip()) - 1 for x in selection.split(",")]
        selected_files = [csv_files[i] for i in indices if 0 <= i < len(csv_files)]
    if not selected_files:
        print("⚠️ No valid files selected. Exiting.")
        exit()
except Exception as e:
    print(f"⚠️ Invalid input: {e}. Exiting.")
    exit()

# Load and concatenate selected CSV files
dfs = []
for fname in selected_files:
    try:
        print(f"\n📥 Loading {fname}...")
        df_part = pd.read_csv(os.path.join(folder_path, fname))
        dfs.append(df_part)
    except Exception as e:
        print(f"❌ Error loading {fname}: {e}")

if not dfs:
    print("❌ No valid CSVs loaded. Exiting.")
    exit()

df = pd.concat(dfs, ignore_index=True)
print(f"\n✅ Loaded {len(df)} total rows from {len(dfs)} file(s).")

# Ask user which rows to process
print(f"\nThere are {len(df)} rows in total.")
row_selection = input("Enter the row numbers to process (comma-separated, e.g., 1,3,5 or 0 for all): ").strip()
if row_selection == ".":
    restart_program()
if not row_selection:
    print("⚠️ No selection made. Exiting.")
    exit()
if  row_selection == "0":
    selected_indices = df.index.tolist()
    original_csv_line_numbers = list(range(1, len(df) + 1))  # All line numbers 1 to N
else:
    try:
        original_csv_line_numbers = [int(x.strip()) for x in row_selection.split(",") if x.strip().isdigit()]
        selected_indices = [x - 2 for x in original_csv_line_numbers if 1 <= x <= len(df)]
        selected_indices = [i for i in selected_indices if 0 <= i < len(df)]
        if not selected_indices:
            print("⚠️ No valid rows selected. Exiting.")
            exit()
    except Exception as e:
        print(f"⚠️ Invalid input: {e}. Exiting.")
        exit()

df = df.iloc[selected_indices].reset_index(drop=True)
print(f"✅ Selected {len(df)} row(s) for processing.")

# Scrape LinkedIn profiles for all selected rows
linkedin_urls = [
    process_linkedin_url(row.get('LinkedInUrl', 'N/A'))
    for _, row in df.iterrows()
    if row.get('LinkedInUrl', 'N/A') and str(row.get('LinkedInUrl', 'N/A')).strip().lower() != 'nan'
]

# Add preview functionality
print(f"\n🔍 PREVIEW: Found {len(linkedin_urls)} LinkedIn profiles to scrape:")
for i, url in enumerate(linkedin_urls[:10]):  # Show first 10
    print(f"  {i+1}. {url}")
if len(linkedin_urls) > 10:
    print(f"  ... and {len(linkedin_urls) - 10} more")

preview_choice = input("\n📋 Would you like to preview companies and websites that will be researched? (y/n): ").strip().lower()
if preview_choice == 'y':
    print("\n🌐 PREVIEW: Companies and websites to be researched:")
    for idx, row in df.iterrows():
        company = row.get('CompanyName', 'N/A')
        website = row.get('Website', 'N/A')
        industry = row.get('Industry', 'N/A')
        print(f"  {idx+1}. {company} ({industry})")
        if website and website != 'N/A':
            print(f"     Website: {website}")
        print(f"     Research queries planned:")
        print(f"       - '{company} + {industry} + news'")
        print(f"       - 'what does {company} do?'")
        print()

# Add live preview options
live_preview = input("\n👀 Enable live browser preview? (y/n): ").strip().lower()
headless_mode = "False" if live_preview == 'y' else "True"

proceed = input("🚀 Proceed with LinkedIn scraping? (y/n): ").strip().lower()
if proceed != 'y':
    print("❌ Scraping cancelled by user.")
    exit()

# Write URLs to a temporary file
with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp:
    for url in linkedin_urls:
        tmp.write(url + '\n')
    tmp_path = tmp.name

# Add preview flag to scraper call with live preview option
print(f"\n🔍 Starting LinkedIn scraping {'with live browser preview' if live_preview == 'y' else 'in headless mode'}...")
subprocess.run([
    "python3",
    "scrape_and_parse_linkedin.py",
    "--csv",
    tmp_path,
    "10",  # max_attempts
    headless_mode, # headless based on user choice
    "--preview" if live_preview == 'y' else "--no-preview"
])

# Step 1: Validity Logic
def is_valid(row):
    linkedin_url = row["LinkedInUrl"]
    has_context = bool(linkedin_url) and (row["FirstName"] or row["Title"]) and row["CompanyName"] and row["Industry"]
    return has_context

print("🔍 Validity check started...")
try:
    df["Valid"] = df.apply(is_valid, axis=1)
    print("✅ Valid entries flagged.")
except Exception as e:
    print(f"❌ Error applying validity logic: {e}")
    raise

# Step 2: Qualification and Email Generation
print("🚀 Starting ICP Qualification with Email Drafting...")

# Add preview for qualification process
print(f"\n📊 QUALIFICATION PREVIEW:")
print(f"Will process {len(df)} visitors using Perplexity AI")
print(f"Each visitor will be researched online for:")
print(f"  - Company background and recent news")
print(f"  - Individual's role and LinkedIn profile")
print(f"  - Industry analysis and AI readiness")
print(f"  - Competitive analysis")

qual_preview = input("\n🤔 Show detailed research plan for first visitor? (y/n): ").strip().lower()
if qual_preview == 'y' and len(df) > 0:
    row = df.iloc[0]
    company = row.get('CompanyName', 'N/A')
    name = f"{row.get('FirstName', 'N/A')} {row.get('LastName', 'N/A')}"
    industry = row.get('Industry', 'N/A')
    website = row.get('Website', 'N/A')
    
    print(f"\n🔍 RESEARCH PREVIEW for {name} at {company}:")
    print(f"📊 Planned research queries:")
    print(f"  1. '{company} + {industry} + news' - Recent company news")
    print(f"  2. 'what does {company} do?' - Company description")
    print(f"  3. '{name} + {company}' - Individual verification")
    print(f"  4. '{company} + {industry}' - Market positioning")
    if website and website != 'N/A':
        print(f"  5. Website analysis: {website}")
    print(f"📋 Will evaluate against InstaLILY's ICP criteria")
    print(f"✉️ If qualified, will draft personalized email")

final_proceed = input("\n🚀 Proceed with full qualification process? (y/n): ").strip().lower()
if final_proceed != 'y':
    print("❌ Qualification cancelled by user.")
    exit()

qual_flags = []
notes_gpt = []
email_drafts = []

print(f"DEBUG: DataFrame shape before Perplexity loop: {df.shape}")
print(df.head())

# === Main Perplexity/Qualification Loop ===
for idx, row in df.iterrows():
    print(f"\n🔄 Processing row {idx + 2} of {len(df)}...")
    print(f"🔍 Checking: {row.get('FirstName', 'N/A')} {row.get('LastName', 'N/A')} at {row.get('CompanyName', 'N/A')}")

    # Add real-time research tracking
    company = row.get('CompanyName', 'N/A')
    industry = row.get('Industry', 'N/A')
    website = row.get('Website', 'N/A')
    
    print(f"🌐 RESEARCH PHASE: About to research {company}")
    if website and website != 'N/A':
        print(f"   📍 Will visit: {website}")
    print(f"   🔍 Search queries:")
    print(f"      - '{company} + {industry} + news'")
    print(f"      - 'what does {company} do?'")
    print(f"   ⏱️  This may take 30-60 seconds...")

    linkedin_json_filename = f"parsed_linkedin_profile_{idx}.json"
    if os.path.exists(linkedin_json_filename):
        if os.path.exists(linkedin_json_filename):
            try:
                linkedin_data = print_json(linkedin_json_filename)
            except Exception as e:
                print(f"⚠️ Could not load LinkedIn data for row {idx}: {e}")
                linkedin_data = "No LinkedIn data available, just use the information above."
        else:
            print(f"⚠️ LinkedIn data file not found for row {idx}: {linkedin_json_filename}")
            linkedin_data = "No LinkedIn data available."

        print("Qualification prompt:")
        # Add real-time research indicator to prompt
        qualification_prompt = f"""

As you research, you will visit the following websites and sources:
- Company website: {website if website != 'N/A' else 'Not available'}
- Google searches for company news and background
- LinkedIn profile verification
- Industry analysis sources

CURRENT RESEARCH TARGET:
{company} in {industry}

        Evaluate the following website visitor to determine if instalily should reach out to them as a potantial client.

        Firstly some context: this is a website visitor that has been identified as a potential lead for InstaLILY, a B2B SaaS company that provides AI-driven solutions for various industries. We are trying to figure out if they are a good fit for InstaLILY and if we should reach out to them.

        Be aware of the intent of the visitor, and put it into 3 categories: Investor, student/looking for a job, or potential customer. If they are an investor or student, they are not qualified. If they are a potential customer, we will evaluate them based on the following criteria.

        Visitor Details from RB2B:
        - Title: {row.get('Title', 'N/A')}
        - First Name: {row.get('FirstName', 'N/A')}
        - Last Name: {row.get('LastName', 'N/A')}
        - LinkedIn URL: {process_linkedin_url(row.get('LinkedInUrl', 'N/A'))}
        - Email: {row.get('Email', 'N/A')}
        - Company: {row.get('CompanyName', 'N/A')}
        - Industry: {row.get('Industry', 'N/A')}
        - Website: {row.get('Website', 'N/A')}
        - Country: {row.get('Country', 'N/A')}
    

    Now, I am going to give you some data from their linkedin. Keep in mind, some of the stuff that these people are doing might not be relevant, but if any of it at all is realevant, you should use it to evaluate the visitor. If you find that the data is not relevant, you can ignore it, but if you find that it is relevant, you should use it to evaluate the visitor. If you find that the data is not relevant, but the visitor has a good title, you should still consider them qualified.
    Again, keep in mind that the visitor might be involved in multiple roles, at multiple companies, in multiple industries, so you should evaluate them based on the the most realavant information you can find, and if you find that the visitor is involved in multiple roles, you should evaluate them based on the most relevant role. If you find that the visitor is involved in multiple companies, you should evaluate them based on the most relevant company. If you find that the visitor is involved in multiple industries, you should evaluate them based on the most relevant industry.
     {linkedin_data}
    


    Some of the industries that InstaLiLY likes to work with are: Healthcare Distribution, Industrial/Construction/Distribution, Automotive (OEM/Fleet/Parts), Food & Beverage Distribution, and PE Operating roles. These are ideals, not requirements. These are just the top industries we are targeting, but we are more than open to other industries if the visitor meets the other criteria. Dont place too much negative weight on the industry, and place a lot of positive weight on the title and seniority (meaning if they have a good title, that is good, but if they dont that is not necessarily bad). this means that if the industry does not line up, don't doc too many points, but if it does line up, give a lot of points. All of these are very broad, and can be interpreted in many ways, so use your best judgement to determine if the visitor is a good fit for InstaLILY.


    
    In the case of ambiguous or missing data, search online to fill in the gaps. Use the companies website, and any other sources you can find to get a better understanding of the company and the visitor.
    InstaLILY's business model is to provide AI-driven solutions that help businesses in these industries optimize their operations, improve efficiency, and drive growth. We are looking for visitors who have an interest in leveraging AI technology to enhance their business processes.

    Also keep in mind that some of the information given could be wrong, so you need to do your own research to verify it, but if you find that for example the industry is wrong, but the title is right, you will need to restart the evaluation based on the new information you found.
    
    Remember, the person and company do not have to currently be working with AI.

    While you are evaluating the visitor/company, do a deep search for any news on both the company and the visitor. Look for any recent news, press releases, or social media activity that might indicate their current business focus, challenges, or interests. This will help you better understand their potential fit with InstaLILY. Feel free to use any sources you can find, including, Google, news articles, etc. and any other sources you can find. If you cannot find any information, do not qualify them. Reddit is also a great source for finding information about the company and the visitor, so be sure to check there as well.

    When you are researching you must search the following: 

        [company name] + [industry] + "news" to find any recent news about the company
        what does [company name] do? to find the company's website and any other information you can find.
        [first name] + [last name] + [company name] to find the visitor's LinkedIn profile.
        [company name] + [industry] to find the company's website and any other information you can find.

    A visitor is considered QUALIFIED if:
    1. They are in or adjacent to ICP industries (if other categories are met, even non-ICP may qualify).
    2. They hold a somewhat senior/strategic title. Lower-level roles are OK only if the other catigories are met 
    3. They show strong buying intent (multiple sessions, career page visits). This is the least important of the three.

    Conduct deep analysis to judge company/role fit. Take your time to evaluate the company using all available sources, and do not rush this process. 

    If a company does something remotely similar to what InstaLILY does, they are a competitor, and they are not qualified, and this immediately disqualifies them. And also keep in mind that they might not be targeting the same industries as instalily, but if they have a similar mission of modernizing other companies (B2B), they are a competitor.

    

    Return only:
    - Yes or No
    - Many short bullet points with information based on industry, title, seniority, and any override logic
    - A short summary of the visitor's profile
    - A short summary of the company
    - A score 1–10 of how qualified they are: formatted like (10 is implied) "Score: 5"
    - A small section on their past experiences (strictly taken from linkedin)

    The visitor doesnt need to currently be making an effort to adopt AI, but rather have a business that could benifit from AI.

    While you are completeing this, something that you should be thingking as you evaluate each company, is 'would this company benifit from Instalily's services', becuase they dont already have to be adopting AI services right now, in fact, the more outdated the better! Keep in mind, instalily helps companies modernize their operations, and improve their efficiency.

    When there are a lack of details for name, title or company, refer to the LinkedIn URL provided in the CSV. If the LinkedIn URL is not available, you can search for the visitor's name and company online to find their LinkedIn profile or other relevant information.
    
    Another thing you NEED to watch out for is whether the visitor is a competitor, trying to scope out InstaLILY. In order to know if they are a competitor, you need to conduct a deep search about the company online and use as many sources you can find. This also requires you to do some research, but it is very important. If they are a competitor, they are not qualified, and you should say so in your response. This means you also have to have a deep understanding of InstaLILY's business model, and products. With this said tho, they still can be doing some stuff with AI already.

    Be sure that you understand both InstaLILY's business model and ICPs, as well as the visitor's profile. If you are not sure, do not qualify them. Make sure that they would be a good fit for InstaLILY, and that they are not a competitor. If you are not sure, do not qualify them.

    Keep in mind, the more people we can qualify, the better, but if they are not a good fit, we should not waste time on them. Be very thorough in your analysis.

    You should aim to qualify between 25 and 35% of the visitors.

    Do not include citations!

The following were all qualified visitors, so you can use them as examples of what a qualified visitor looks like. Study them very carefully and make sure you understand what makes each of them qualified. When in doubt, you can refer back to these examples to help you make your decision. Try and identify a pattern amongst the following

LinkedInUrl	FirstName	LastName	Title	CompanyName	AllTimePageViews	WorkEmail	Website	Industry	Qualified?
https://www.linkedin.com/in/aolar	Amanda	Hazer	Next-Quarter Coach for Women Athletes	amanda hazer consulting llc	4	olara2587@gmail.com	https://knft.com		Qualified
https://www.linkedin.com/in/amitmenghani	Amit	Menghani	Director of Software Engineering	capital one	2	amitsopinion@gmail.com	http://www.capitalone.com	Finance and Banking	Qualified
https://www.linkedin.com/in/ben-jablow-20854	Ben	Jablow	CEO	Romify	1	ben@rupt.com	https://www.rupt.com		Qualified
https://www.linkedin.com/in/bretthughes6	Brett	Hughes	Chief Operating Officer	studionow	1	brett@empactfulcapital.com	https://studionow.com	Media and Publishing	Qualified
https://www.linkedin.com/in/caley-kovler	Caley	Kovler	Director, Consumer Insights	starz	1	caley.kovler@starz.com	http://www.starz.com/	Creative Arts and Entertainment	Qualified
https://www.linkedin.com/in/chad-goldman-57905a31/	Chad	Goldman	Manager, Direct Container Division at Jofran, Inc.		3	chadgoldman@comcast.net			Qualified
https://www.linkedin.com/in/colliersearle	Collier	Searle	Board Member	ORTEC	13		https://ortec.com		Qualified
https://www.linkedin.com/in/davidyoh2	David	Yoh		toast	1	david.yoh@toasttab.com	http://pos.toasttab.com	Information Technology	Qualified
https://www.linkedin.com/in/davidspiegelman	David	Spiegelman	Founder	manta creative	8	david@mantacreative.com	https://www.mantacreative.com	Marketing & Advertising	Qualified
https://www.linkedin.com/in/don-macagba	Don King	Macagba	Site Manager	arx networks	9	dmacagba@arxnetworks.com	http://www.arxnetworks.com	Information Technology	Qualified
https://www.linkedin.com/in/hsuelaine	Elaine	Hsu	Head Of Operations	planet fwd	52	elaine@planetfwd.com	http://planetfwd.com	Information Technology	Qualified
https://www.linkedin.com/in/emilio-mel-smith-b2636749	Emilio Mel	Smith	Assistant Superintendent, Commercial Tennant Improvement Construction	novo construction, inc.	3	mstrag83@hotmail.com	http://www.novoconstruction.com/	Construction	Qualified
https://www.linkedin.com/in/emmanuelebwe	Emmanuel	Ebwe			2	etikwe@hotmail.com	https://takomatherapy.com		Qualified
https://www.linkedin.com/in/erin-fischell-6562303a	Erin	Fischell	Founder	acbotics research llc	6	efischell@jpanalytics.com	https://hartelrealty.com		Qualified
https://www.linkedin.com/in/jason-lionetti-058777121	Jason	Lionetti	Operational Specialist	cb2	1	jasonlionetti702@gmail.com	http://www.cb2.com	Retail	Qualified
https://www.linkedin.com/in/jasontell	Jason	Tell	Chief User Experience Officer	Modern Climate	4	jtell@modernclimate.com	https://modernclimate.com/	Marketing & Advertising	Qualified
https://www.linkedin.com/in/jeff-stuart-b8899611	Jeff	Stuart	Managing Director	berkadia	1	jeff.stuart@berkadia.com	http://www.berkadia.com	Finance and Banking	Qualified
https://www.linkedin.com/in/jennifer-whitaker-41394bb7	Jennifer	Whitaker	Director of Engineering and Maintenance	rivanna water and sewer authority	1	jwhitaker@rivanna.org	http://rivanna.org	Professional and Business Services	Qualified
https://www.linkedin.com/in/jim-mackinnon-aa35032a	Jim	MacKinnon	Director International Sales	yaskawa america, inc. -  drives & motion division	1	jim_mackinnon@yaskawa.com	https://www.yaskawa.com	Manufacturing	Qualified
https://www.linkedin.com/in/joby-peter-08833a4	Joby	Peter	Engineering Manager	amd	1	joby.peter@amd.com	http://www.amd.com	Manufacturing	Qualified
https://www.linkedin.com/in/john-desena	John	DeSena	Co-Chief Operating Officer, Shared Services	b. riley financial	2	jdesena@brileyfin.com	https://brileyfin.com/	Finance and Banking	Qualified
https://www.linkedin.com/in/jon-glascoe-60512551	jon	glascoe	Co-Founder	cypress films	2	jonglascoe@rocketmail.com	https://goo.gle		Qualified
https://www.linkedin.com/in/karina-iturralde	Karina	Iturralde	Public Relations Assistant Account Executive	inkhouse	1	karina@inkhouse.com	http://www.inkhouse.com	Marketing & Advertising	Qualified
https://www.linkedin.com/in/kasey-homa	Kasey	Homa	Global Product Strategy & Development	capital group	1	kasey.homa@capgroup.com	https://www.capitalgroup.com/us/landing-pages/linkedin-terms-of-use.html	Finance and Banking	Qualified
https://www.linkedin.com/in/keri-lartz	Keri	Lartz	Director Of Operations	the rave agency	2	keri@theraveagency.com	https://theraveagency.com	Marketing & Advertising	Qualified
https://www.linkedin.com/in/lissette-gonzalez-83253b54	lissette	Gonzalez	Principle administrator	city of new york, department of homeless services	3	kevlissette@hotmail.com	https://bcfs.net		Qualified
https://www.linkedin.com/in/marissazehnder	Marissa	Zehnder	National Account Executive	justworks	5	marissa@justworks.com	https://www.justworks.com/lp/what-is-justworks/?utm_source=linkedin&utm_medium=organicsocial	Professional and Business Services	Qualified
https://www.linkedin.com/in/michael-dorfman	Michael	Dorfman		pro padel league	4	mdorfman15@gmail.com	https://propadelleague.com	Tourism and Hospitality	Qualified
https://www.linkedin.com/in/muthukumar-easwaran-8081863	Muthukumar	Easwaran	Senior Vice President -  Digital/Data, Product and Technology Platforms	neighborly®	1	muthukumar.easwaran@neighborlybrands.com	https://www.neighborlybrands.com/	Professional and Business Services	Qualified
https://www.linkedin.com/in/nhansch	Neal	Hansch		Silicon Foundry	1	neal@sifoundry.com	http://www.sifoundry.com		Qualified
https://www.linkedin.com/in/nil-timor	Nil	Timor		jwp connatix	2	nil@jwplayer.com	https://jwpconnatix.com	Information Technology	Qualified
https://www.linkedin.com/in/paul-donahue-a3048166	Paul	Donahue	Vice President	salem capital management	1	paul@salemcap.com	http://www.salemcap.com	Finance and Banking	Qualified
https://www.linkedin.com/in/peter-higgins-516a3133	Peter	Higgins	Chief Operating Officer	salt lake city department of airports	3	petehiggs_slc@hotmail.com	https://slcgov.com		Qualified
https://www.linkedin.com/in/phillippoinsatte	Phillip	Poinsatte	President / Owner	global recruiters of boston south (grn)	6	p325ic@aol.com	http://www.globalrecruitersbostonsouth.com	Professional and Business Services	Qualified
https://www.linkedin.com/in/raghava-sreenivasan-183b9b295	Raghava	Sreenivasan	Vice President - Site Reliability Engineer/DevOps Lead	JPMorgan Chase & Co.	2		https://marquisspas.com	Financial Services	Qualified
https://www.linkedin.com/in/rahulkaitheri	Rahul	Kaitheri		lowe's companies, inc.	1	rahul.kaitheri@lowes.com	https://talent.lowes.com	Retail	Qualified
https://www.linkedin.com/in/robert-mahoney-17ba223	Robert	Mahoney	Founder	Has founded a variety of interesting companies.	24	bobbymahoney@gmail.com	https://linktr.ee/csufofficial	Education	Qualified
https://www.linkedin.com/in/ronald-volans	Ron	Volans	Head of North America Janssen Deliver	Johnson & Johnson	1		https://pwc.com		Qualified
https://www.linkedin.com/in/ron-delyons-3127711b8	Ron	DeLyons	Chief Executive Officer	creekwood energy partners	1				Qualified
https://www.linkedin.com/in/ryanstone-nyc	Ryan	Stone		teva pharmaceuticals	5	bigsquirm4@cs.com	http://www.tevapharm.com	Health and Pharmaceuticals	Qualified
https://www.linkedin.com/in/sjyork	Sarah	York	Director, Stores & Corporate Marketing Strategy	Macy's	1	sjyork@suffolk.edu	http://www.macysjobs.com?rx_source=linkedincompanypage	Retail	Qualified
https://www.linkedin.com/in/saroj-adhikari-1aa99020	Saroj	Adhikari	Leader, Data Engineering Team	success academy charter schools	1	saroj.adhikari@successacademies.org	http://jobs.successacademies.org	Education	Qualified
https://www.linkedin.com/in/shannon-moman-a1261216	Shannon	Moman	Director of Sales Support	r & s northeast	4	smoman@rsnortheast.com	http://www.rsnortheast.com	Health and Pharmaceuticals	Qualified
https://www.linkedin.com/in/laiyzhang	Teri	Zhang	Associate Media Director	zenith	5	teri.zhang@zenithmedia.com	http://www.zenithmedia.com	Marketing & Advertising	Qualified
https://www.linkedin.com/in/theresa-cullinan-caulfield-27886955	Theresa	Cullinan Caulfield	Senior Director Human Resources	prager & company	2	theresa.caulfield@prager.com	http://www.prager.com	Finance and Banking	Qualified
https://www.linkedin.com/in/thomas-minetti-414a449	Thomas	Minetti	Home Improvement Contractor	home improvement contractor	2	tminetti@primeres.com	https://capitalremodeling.com	Construction	Qualified
https://www.linkedin.com/in/thomas-knight-1a563915	Thomas	Knight	Owner	toyon associates, inc	1	tom.knight@toyonassociates.com	https://sigsauer.com		Qualified
https://www.linkedin.com/in/xiaoying-su-580ab0224	Xiaoying	Su	Director	Echoes Films	22	xsu2@sva.edu		Media Production	Qualified
https://www.linkedin.com/company/inovahealth				Inova Health	2		https://inova.org	Health and Pharmaceuticals	Qualified
https://www.linkedin.com/company/atkinson-andelson-loya-ruud-&-romo				Atkinson, Andelson, Loya, Ruud & Romo	3		https://aalrr.com	Professional and Business Services	Qualified
https://www.linkedin.com/company/bearings-specialty-co--inc-				Bearings Specialty, Co. Inc.	1		https://bearings-specialty.com	Manufacturing	Qualified
https://www.linkedin.com/company/potrero-medical				Potrero Medical	2		https://potreromed.com	Manufacturing	Qualified
https://www.linkedin.com/company/cornell-cooperative-extension-of-genesee-county				Cornell Cooperative Extension of Genesee County	6		https://cornell.edu	Non-Profit and Social Services	Qualified



The following is an example of a disqualified visitor. Use these as examples of what a disqualified visitor looks like. When in doubt, you can refer back to these examples to help you make your decision. Try and recognize patternes amongst the following:

LinkedInUrl	FirstName	LastName	Title	CompanyName	AllTimePageViews	WorkEmail	Website	Industry
https://www.linkedin.com/in/tina-laforgia-014b2233	Tina	LaForgia	Senior Accountant	guidemark health	28	tlaforgia@guidemarkhealth.com	https://guidemarkhealth.com	Marketing & Advertising
http://www.linkedin.com/in/alison-burton-95095840	Alison	Burton	Floater Executive Assistant	KKR	13	alison.burton@kkr.com	http://www.kkr.com	Financial Services
https://www.linkedin.com/in/james-bush-68a73779	James	Bush			12			
https://www.linkedin.com/company/care-plus-nj				Care Plus NJ	27		https://careplusnj.org	Non-Profit and Social Services
https://www.linkedin.com/in/ivan-samayoa-32213b31	Ivan	Samayoa		UpCrunch	4	ivane.samayoa@gmail.com	http://www.upcrunch.com	
https://www.linkedin.com/in/alexazhao	Zhen	Zhao	Marketing Professional		2	alexzhao49@gmail.com	https://shanda.com	Internet
https://www.linkedin.com/in/christinakaney	Christina	Kaney	Growth Manager	definity first	6	ckaney3@gmail.com	http://www.definityfirst.com	Information Technology
https://www.linkedin.com/in/geoff-hippenstiel-1b01382a	Geoff	Hippenstiel			8	ghippen@hotmail.com	https://mountsinai.org	
https://www.linkedin.com/in/qiaoxin-lin-profile	Vicky	L.	Summer Analyst	ubs	22	qiaoxinlin00@gmail.com	http://www.ubs.com/about	Finance and Banking
https://www.linkedin.com/in/rajeevkrai	Rajeev	Rai	Chief Information Technology Officer	groundworks	50	rajeev.rai@srsdistribution.com	https://www.groundworks.com/	Construction
https://www.linkedin.com/in/danayou	Dana	You	AI/ML Engineer	instalily ai	76		https://www.instalily.ai/	Information Technology
https://www.linkedin.com/company/mount-vernon-seventh-day-adventist-church				MOUNT VERNON SEVENTH-DAY ADVENTIST CHURCH	4		https://mtvernonsda.org	Non-Profit and Social Services
https://www.linkedin.com/in/fern-coleman-57374747	Fern	Coleman	Senior Insight Consultant	Bryter	86	fern.coleman@bryter-uk.com	https://bryter-global.com	
https://www.linkedin.com/company/silverline-realty-group				Silverline Realty Group	79		https://slrgrp.com	Real Estate
https://www.linkedin.com/in/brady-barksdale	Brady	Barksdale		lumeus.ai	19	jbbarksdale@gmail.com	http://lumeus.ai	Information Technology
https://www.linkedin.com/in/ronan-nayak	Ronan	Nayak			4		https://3ds.com	
https://www.linkedin.com/in/lisa-lapusata-48072573	Lisa	LaPusata	Director	bright horizons	8	bev@brighthorizons.com	http://www.brighthorizons.com	Education
https://www.linkedin.com/company/jpmorganassetmanagement				J.P. Morgan Asset Management	7		https://jpmorgan.com	Finance and Banking
https://www.linkedin.com/company/argand-partners				Argand Partners	2		https://argandequity.com	Finance and Banking
https://www.linkedin.com/company/mpiphp				Motion Picture Industry Pension & Health Plans	2		https://mpiphp.org	Creative Arts and Entertainment
https://www.linkedin.com/company/mongodbinc				MongoDB	3		https://mongodb.com	Information Technology
https://www.linkedin.com/company/international-paper				International Paper	1		https://internationalpaper.com	Manufacturing
https://www.linkedin.com/company/yale-school-of-music				Yale School of Music	2		https://yale.edu	Education
https://www.linkedin.com/company/larkin-refractory-solutions				Larkin Refractory Solutions	4		https://larkinrefractory.com	Manufacturing
https://www.linkedin.com/in/hailsw	Hailey	Wilcox	Venture Capital Investor	battery ventures	1	hwilcox@battery.com	http://www.battery.com	Finance and Banking
https://www.linkedin.com/in/julian-gonzalez-46198b3	Julian	Gonzalez	Instructor	st. patrick - st. vincent high school	1	j.gonzalez@spsv.org	https://target.com
https://www.linkedin.com/company/asia-pacific-public-electronic-procurement-network				Asia Pacific Public Electronic Procurement Network	1		https://adb.org	Government and Public Administration
https://www.linkedin.com/company/hilton-tashkent-city-hotel				Hilton Tashkent City Hotel	5		https://hilton.com	Tourism and Hospitality
https://www.linkedin.com/company/accenture-united-states-benefit				ACCENTURE UNITED STATES BENEFIT	1		https://accenture.com	Information Technology
https://www.linkedin.com/company/evergreen-valley-college				Evergreen Valley College	2		https://evc.edu	Education
https://www.linkedin.com/company/washington-university-department-of-surgery-human-resources				Washington University School of Medicine-Department of Surgery-Human Resources	2		https://wustl.edu	Health and Pharmaceuticals
https://www.linkedin.com/company/abbaspourrad-lab				Abbaspourrad Lab	2		https://cornell.edu	Professional and Business Services
https://www.linkedin.com/company/my-eye-dr.-optometry-greenbelt-llc					1	junzhuzhang20@163.com	https://myeyedr.com	
https://www.linkedin.com/in/jessiecaruso	Jessie	Caruso (she/her)	Chief Mom Officer	the caruso clan	4	jcaruso@perkinscoie.com		
https://www.linkedin.com/company/jewish-council-for-the-aging				Jewish Council for the Aging (JCA)	2		https://accessjca.org	Non-Profit and Social Services
https://www.linkedin.com/company/pilates-power				Pilates Power	1		https://powerpilates.com	Professional and Business Services
https://www.linkedin.com/in/tommy-ho-cpa-233bb21a	Tommy	Ho	Senior Accountant	Veracode	3	tommyhocm@hotmail.com	https://veracode.com	Accounting
https://www.linkedin.com/company/copper-state-bolt-nut-company				Copper State Bolt & Nut Company	1		https://copperstate.com	Manufacturing
https://www.linkedin.com/company/georgetown-university-writing-center				Georgetown University Writing Center	1		https://georgetown.edu	Creative Arts and Entertainment
https://www.linkedin.com/in/rothman-robin-rothman-66bb6026	Rothman, Robin	Rothman	Senior Global Real Estate Advisor, Associate Broker	sotheby's international realty	6	robin.rothman@sothebyshomes.com	http://www.sothebysrealty.com	Real Estate

Make sure you start with either a "Yes" or a "No" indicating weather or not the person and company is qualified. If they are qualified, say "Yes" as the first words, and if they are not, say "No"

Finally, If you select someone, you should be 100% confident that they could work well with instalily and align well with what we do. The more people that we can qualify the better.

Dont use any bold text or italic.
"""
    print("Qualification prompt:")
    print(qualification_prompt)
    print("📬 Sending qualification request to Perplexity AI...")
    print("🤔 Perplexity is now actively researching online...")
    print(f"   🔍 Searching: '{company} + {industry} + news'")
    
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    # Progress bar utility
    def print_progress_bar(iteration, total, prefix='', suffix='', length=40):
        percent = f"{100 * (iteration / float(total)):.1f}"
        filled_length = int(length * iteration // total)
        bar = '█' * filled_length + '-' * (length - filled_length)
        print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='\r')
        if iteration == total:
            print()
    payload = {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": qualification_prompt}]
    }
    try:
        response = requests.post(PERPLEXITY_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            print("🔍 Qualification in progress...")
            reply = response.json()['choices'][0]['message']['content'].strip()
            is_qualified = reply.lower().startswith("yes")
            qual_flags.append(is_qualified)
            notes_gpt.append(reply)
            print("📧 Received results from Perplexity")
            print(reply)
            print(f"✅ Qualification result for {row.get('FirstName', '')} {row.get('LastName', '')}: {'Qualified ✅' if is_qualified else 'Not Qualified ❌'}")
            if is_qualified:
                print(f"📧 Drafting email for {row.get('FirstName', '')}...")
                email_prompt = f"""

Write a short, very formal and professional, personalized email from Sumo (co-founder of InstaLILY) to the following website visitor, based on their role and company. 
No buzzwords. Mention curiosity about what brought them to the site, and a soft offer to help. 
Mention how InstaLILY helps companies eliminate manual work and improve operations with AI.
Talk a little bit about why we could help them (specific to their company and what they do--this will require research on both instalily and the company we are emailing.
The name of the game is to get them to respond, so keep it very very profesional and short!! Do Not include citations!
2 sentences max!
Also be sure to keep in mind their role at the company and how that might change the email (a board member would get a different email than a director of operations, for example).
Dont make it sound like a sales email.
It is most important that the email is not salesy at all, but the first line is ultra personalized to catch their attention.

Remember, this is a business email, so write with respect and the upmost respectfullness, and formalness.

Here is the information about the visitor:
- Name: {row.get('FirstName', '')}
- Title: {row.get('Title', '')}
- Company: {row.get('CompanyName', '')}
- Industry: {row.get('Industry', '')}
- LinkedIn URL: {process_linkedin_url(row.get('LinkedInUrl', ''))}
- Website: {row.get('Website', '')}
- Email: {row.get('Email', '')}

Dont use any bold text or italic.

Here are some examples of messages that you can use as a reference and try to match the tone and writing style exactly:

Justin,

Thank you for your incredibly kind words! I'm so glad we've embarked on this journey together.  You and Carl have already been an immense part of our growth and we are energized to partner hand-in-hand !

If there's anything more we can ever do in our partnership or otherwise, please don't hesitate to reach out to me directly.  I've added my mobile line so you have it for your records.

Best,
Sumo

Richard,
Thanks for your insights during the GCP Accelerator. Im one of the presenters, I’d love to connect later today!

Best,
Sumo

Sumit,
It was great connecting today via Alex and the PartsSource team. I look forward to building our partnership!

Best,
Sumo

Frederike, it was great meeting you and having you over, we will be doing more of these events and I look forward to seeing you again!

Best,
Sumo

Joana, thanks for being super supportive of InstaLILY and our period of rapid growth during the Accelerator program.

Best,
Sumo
Co-founder

Ben,
It was great to connect with you, Peter and the team today via Rekha at Platinum. I look forward to building our partnership!

Best,
Sumo

Peter,
It was great to connect with you, Ben and the team today via Rekha at Platinum. I look forward to building our partnership!

Best,
Sumo

Hi Jessica,

I've heard the news and I'm sorry to hear how it unfolded.  I'd be delighted to provide a recommendation - it was a real pleasure to work together with you!  Please give me a couple of days and I'll have it posted.

Separately, if there's anything else I can help with i.e. anyone on my LinkedIn you'd like an introduction with (especially at Apple and Google given common interests) please feel free to let me know.

I'm sure we will cross paths again and I look forward to our in person meeting.  Please call/message my cell if you're ever in NYC.

Best,
Sumo

Hi Jessica,

Hope you're keeping well! Given our strong partnership, I was wondering if you could write a brief LinkedIn recommendation? I've highlighted some wins between our teams (specifically covering PayPal/Venmo/Braintree). I am more than happy to reciprocate the request.

Thank you in advance!

Best,
Sumo

Jason,
Great to meet you as well.  Feel free to drop me a note and we'll find time.  I know Sharon and Lance are keen to move on this as well.

Best,
Sumo

Dmitry,
It was great connecting today, so glad Darren connected our teams! I look forward to building our partnership.

Best,
Sumo



Peter,
It was great spending time with you yesterday in NYC! Amit and I are excited to build our partnership and look forward to continuing our conversation.

Best,
Sumo

Mike,
It was great to spend time with you and Stephan at SHIFT, I'm so glad for the connect via Cory!

My team and I were ideating following our discussion and would love to show you both a demo for DSG, let me know the best way for us to find time together.

Separately, here's information on AI Trailblazers Thu June 6 in NYC, let me know if you can make it and I'll sign you up. It promises to be an awesome event:
https://www.aitrailblazers.io/ai-trailblazers-summer-summit.

Best,
Sumo

Hi Tom,
Sasha & Rachel from my team met Allie at SHIFT - Dan Schuberth also suggested we connect given our success in helping SRS Distribution drive sales using our AI agent platform (they use us across their entire team).

I’d love to connect and find time.

Best,
Sumo
Co-founder & COO

Kier,
It was great to meet you yesterday. We're excited to partner together on the AI agents service automation with you, Janet and Alex!

Best,
Sumo

Tris,
Really appreciated your time on today's call, we're scaling up our footprint using Gemini and GCP, I'd love to continue our conversations as we bring AI to industrial suppliers and distributors!

Best,
Sumo

Manish,
Thank you again for taking the time to meet today—it was great to connect through Vyom. I really appreciated the thoughtful conversation and your openness throughout. I look forward to building our partnership.
I’ll follow up shortly with the deck from our session, an additional supply chain–specific use case, and next steps for getting the Enterprise AI Accelerator—the working session we discussed—on the calendar.
Also appreciated the transparency around your cyber event and security posture. We’ll be sure to include additional materials on our SOC 2, HIPAA compliance, and deployment models as part of the follow-up.
Really looking forward to the next steps, Manish. Please don’t hesitate to drop me a note if anything comes up in the meantime.
Best,
Sumo
Co-founder, InstaLILY

​​Dear Manish,
Thank you so much for taking the time to meet Iris, Vyom, and me. It truly was a pleasure to learn more about Henry Schein and their supply chain operations, as well as discussing the areas where InstaLILY can help cut costs and optimize supply chain operations.
We enjoyed the conversation a lot, and hearing your perspective on how the supply chain team is approaching AI, efficiency, and innovation gave us a lot to think about. It is clear that there is a strong alignment between the challenges your team is focused on and the ways we can support when navigating these challenges.
As mentioned during the meeting, I’ll be sending over the presentation deck along with the demo recordings we walked through. Building on today's meeting, we are excited to schedule a working session with you and the rest of the team to showcase some of our work, ahead of the 72-hour accelerator discussed in the call.
Thanks again for the time and openness. We’re looking forward to working together, and building something great.
Warm Regards,
Sumo
COO, InstaLILY

Remember the name of the game is ultra professional, ultra polished, and ultra personalized, and very very short. Make sure you match the tone and writing style of the examples above, and make sure you are ultra professional, ultra polished, and ultra personalized.
Very formal!

"""
                # --- Use OpenAI API for email drafting instead of Perplexity ---

                OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # Set your OpenAI API key as an environment variable

                def draft_email_with_openai(email_prompt):
                    try:
                        openai.api_key = OPENAI_API_KEY
                        response = openai.ChatCompletion.create(
                            model="gpt-4",
                            messages=[{"role": "user", "content": email_prompt}],
                            max_tokens=200,
                            temperature=0.5,
                        )
                        return response.choices[0].message['content'].strip()
                    except Exception as e:
                        print(f"❌ OpenAI API error: {e}")
                        return ""

                if OPENAI_API_KEY:
                    email_text = draft_email_with_openai(email_prompt)
                    email_drafts.append(email_text)
                else:
                    print("⚠️ OPENAI_API_KEY not set, skipping OpenAI email drafting.")
                    email_drafts.append("")
                email_payload = {
                    "model": "sonar-pro",
                    "messages": [{"role": "user", "content": email_prompt}]
                }
                email_response = requests.post(PERPLEXITY_API_URL, headers=headers, json=email_payload)
                if email_response.status_code == 200:
                    email_text = email_response.json()['choices'][0]['message']['content'].strip()
                    email_drafts.append(email_text)
                else:
                    email_drafts.append("")
            else:
                email_drafts.append("")
        else:
            qual_flags.append(False)
            notes_gpt.append("API error")
            print(f"❌ API error: {response.status_code} - {response.text}")
            email_drafts.append("")
    except Exception as e:
        qual_flags.append(False)
        notes_gpt.append("Exception occurred")
        email_drafts.append("")
        print(f"❌ Error processing row {idx}: {e}")

# Set columns and save
print("Email drafting complete. Setting columns...")
print("📊 Finalizing Data")
df["Qualified"] = qual_flags
df["Notes                                                      "] = notes_gpt
df["EmailDraft                                         "] = email_drafts

# Add line breaks for better readability in spreadsheet applications
df["Notes                                                      "] = df["Notes                                                      "].apply(
    lambda x: x.replace('. ', '.\n') if isinstance(x, str) else x
)
df["EmailDraft                                         "] = df["EmailDraft                                         "].apply(
    lambda x: x.replace('. ', '.\n') if isinstance(x, str) else x
)

def extract_score(text):
    # Look for a number 1-10 (integer or float) after the word 'score'
    match = re.search(r'score\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: look for a number at the end of the string
    match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*$', text)
    if match:
        return match.group(1)
    return ""

df["Score"] = [extract_score(note) for note in notes_gpt]

print("📦 All rows processed. Finalizing and saving output...")
try:
    # Create 'processed' subfolder if it doesn't exist
    processed_folder = os.path.join(os.path.dirname(__file__), "Processed")
    os.makedirs(processed_folder, exist_ok=True)

    # Determine output filename based on selected files
    if len(selected_files) == 1:
        base_name = os.path.splitext(selected_files[0])[0]
        output_file = os.path.join(processed_folder, f"{base_name}_analyzed.csv")
    else:
        # If multiple files, save a separate analyzed file for each input
        for fname, df_part in zip(selected_files, dfs):
            base_name = os.path.splitext(fname)[0]
            output_file = os.path.join(processed_folder, f"{base_name}_analyzed.csv")
            orig_output_file = output_file
            count = 1
            while os.path.exists(output_file):
                output_file = os.path.join(processed_folder, f"{os.path.splitext(base_name)[0]}_{count}.csv")
                count += 1
            df_part = df[df['SourceFile'] == fname] if 'SourceFile' in df.columns else df
            df_part.to_csv(output_file, index=False)
            print(f"💾 Output saved to {output_file}")
        output_file = os.path.join(processed_folder, "AnalyzedVisitors.csv")  # For the rest of the logic, use a generic name
    # If file exists, add a numeric suffix to avoid overwrite
    orig_output_file = output_file
    count = 1
    while os.path.exists(output_file):
        output_file = os.path.join(processed_folder, f"{os.path.splitext(os.path.basename(orig_output_file))[0]}_{count}.csv")
        count += 1
    df.to_csv(output_file, index=False)
    print(f"💾 Output saved to {output_file}")
    print(f"🎯 Percent Qualified: {100 * df['Qualified'].sum() / len(df):.2f}%")
    print(f"{df['Qualified'].sum()} of {len(df)} total visitors.")
    
    # Map qualified DataFrame indices back to original CSV line numbers
    qualified_df_indices = df.index[df["Qualified"]].tolist()
    qualified_csv_line_numbers = [original_csv_line_numbers[i] for i in qualified_df_indices]
    
    print(f"Qualified visitor line numbers (CSV lines): {tuple(qualified_csv_line_numbers)}")
    # Prompt user for correct answers and compare with model's output
    try:
        correct_input = input("Enter the correct line numbers for qualified visitors (x,y,z): ").strip()
        if correct_input:
            correct_set = set(int(x.strip()) for x in correct_input.split(",") if x.strip().isdigit())
            model_set = set(qualified_csv_line_numbers)
            intersection = correct_set & model_set
            # Use F1 score for a more balanced metric
            if model_set or correct_set:
                precision = len(intersection) / len(model_set) if model_set else 0
                recall = len(intersection) / len(correct_set) if correct_set else 0
                if precision + recall > 0:
                    f1 = 2 * precision * recall / (precision + recall)
                else:
                    f1 = 0.0
            else:
                f1 = 1.0
            print(f"✅ F1 score: {f1:.2f} (Precision: {precision:.2f}, Recall: {recall:.2f})")
            print(f"Model: {sorted(model_set)}")
            print(f"Correct: {sorted(correct_set)}")
            print(f"🎯 Matches: {sorted(intersection)}")
            print(f"❌ Model missed: {sorted(correct_set - model_set)}")
            print(f"⚠️ Model over-qualified: {sorted(model_set - correct_set)}")
            print(f"📊 Summary: {len(intersection)} out of {len(model_set)} correct, out of a total of, {len(correct_set)}")
            print("💾 AnalyzedVisitors.csv Updated!")
            if abs(f1 - 1.0) < 1e-6: # Check for perfect F1 score
                print("🎉 Perfect F1 score achieved!")
            f1_info = (
                f"F1: {f1:.2f}; "
                f"Precision: {precision:.2f}; "
                f"Recall: {recall:.2f}; "
                f"Model: {sorted(model_set)}; "
                f"Correct: {sorted(correct_set)}; "
                f"Intersection: {sorted(intersection)}; "
                f"{len(intersection)} of {len(model_set)} correct, {len(df)} total"
            )
            df["F1_Score_Info"] = f1_info
            df.to_csv(os.path.join(processed_folder, "AnalyzedVisitors.csv"), index=False)
        else:
            print("No correct answers entered. Skipping similarity score.")
    except Exception as e:
        print(f"❌ Error comparing answers: {e}")
except Exception as e:
    print(f"❌ Error saving CSV: {e}")
    print(f"🎯 Percent Qualified: {100 * df['Qualified'].sum() / len(df):.2f}%")
