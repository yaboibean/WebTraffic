# InstaLILY Lead Qualification Tool

A global web application for qualifying website visitors as potential leads using AI-powered analysis.

## Features

- **CSV Upload & Analysis**: Upload visitor data and get AI-powered qualification
- **Real-time Processing**: See results as they're processed with live progress tracking
- **Email Draft Generation**: Automatically generate personalized emails for qualified leads
- **Data Storage**: Store and retrieve past analysis results
- **Global Access**: Deployed on Streamlit Cloud for worldwide access

## Deployment

### Streamlit Cloud (Recommended)

1. Push this repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account and select this repository
4. Set the main file path to `app.py`
5. Add the following secrets in the Streamlit Cloud dashboard:
   ```
   PERPLEXITY_API_KEY = "your-perplexity-api-key"
   OPENAI_API_KEY = "your-openai-api-key"
   ```

### Local Development

1. Install dependencies:
   ```bash
   pip install streamlit pandas requests openai sqlite3
   ```

2. Set environment variables:
   ```bash
   export PERPLEXITY_API_KEY="your-key"
   export OPENAI_API_KEY="your-key"
   ```

3. Run the app:
   ```bash
   streamlit run app.py
   ```

## Usage

1. **Upload CSV**: Visit the web app and upload a CSV file with visitor data
2. **Configure Analysis**: Choose whether to process all rows and generate emails
3. **Start Analysis**: Click "Start Analysis" and watch real-time progress
4. **View Results**: See qualified leads with rationales and email drafts
5. **Download Results**: Export the analysis results as CSV
6. **View History**: Access past analyses and qualified leads

## CSV Format

Your CSV should include columns like:
- FirstName
- LastName
- Title
- CompanyName
- Industry
- Email
- Website
- Country

## API Keys Required

- **Perplexity API**: For AI-powered lead qualification
- **OpenAI API**: For email draft generation (optional)

## Database

Uses SQLite for local data storage. All analysis results and qualified leads are automatically saved and can be accessed through the "View Past Results" page.
