# -*- coding: utf-8 -*-
"""
Created on Wed Jul 10 13:43:35 2024

@author: Riya
"""

from flask import Flask, request, render_template, redirect, url_for, jsonify, session
import secrets
import os
import fitz  # PyMuPDF
import docx2txt
import re
import PyPDF2
import zipfile
from docx2pdf import convert
from datetime import datetime
import pythoncom

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'uploads'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Global variables to store technologies, keywords, and ability words
technologies = []
keywords = []
ability_words = []

# Function to normalize words by removing extra spaces
def normalize_word(word):
    return ' '.join(word.split())

# Function to read text from a PDF file using fitz (PyMuPDF)
def read_pdf(file_path):
    text = ''
    document = fitz.open(file_path)  # Open the PDF document
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        text += page.get_text()
    return text

# Function to read text from a DOCX file using docx2txt
def read_docx(file_path):
    try:
        text = docx2txt.process(file_path)
        return text
    except zipfile.BadZipFile:
        return "Error: The file is not a valid DOCX file."
    except Exception as e:
        return f"Error: An unexpected error occurred while reading the DOCX file. {str(e)}"

# Function to write raw data to a file with UTF-8 encoding
def write_raw_data(filename, text):
    with open(filename, 'a', encoding='utf-8') as file:
        file.write(text)
        file.write("\n" + "="*80 + "\n")  # Separator between resumes

# Function to read technologies from a file
def read_technologies(file_path):
    with open(file_path, 'r') as file:
        technologies = [normalize_word(line.strip()) for line in file.readlines() if line.strip()]
    return technologies

# Function to read keywords from a file
def read_keywords(file_path):
    with open(file_path, 'r') as file:
        keywords = [normalize_word(line.strip()) for line in file.readlines() if line.strip()]
    return keywords

# Function to read ability words from a file
def read_ability_words(file_path):
    with open(file_path, 'r') as file:
        ability_words = [normalize_word(line.strip()) for line in file.readlines() if line.strip()]
    return ability_words

# Function to count occurrences of words in text
def count_words(text, words_list):
    word_count = {}
    for word in words_list:
        normalized_word = normalize_word(word)
        count = len(re.findall(r'\b{}\b'.format(re.escape(normalized_word)), text, flags=re.IGNORECASE))
        word_count[normalized_word] = count
    return word_count

# Function to count pages in a document
def count_pages(file_path, file_ext):
    if file_ext == '.pdf':
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
    elif file_ext == '.docx':
        # Convert the .docx file to a PDF
        pdf_path = file_path.replace('.docx', '.pdf')
        
        # Initialize COM library
        pythoncom.CoInitialize()
        try:
            convert(file_path, pdf_path)
        finally:
            # Uninitialize COM library
            pythoncom.CoUninitialize()
        
        # Open the PDF file and count the pages
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
        
        # Clean up the generated PDF file
        os.remove(pdf_path)
    else:
        num_pages = 1
    return num_pages

# Helper function to parse date
def parse_date(date_str):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

# Function to find dates and durations in a text
def find_dates(text):
    date_patterns = [
        r'\b(?:\d{4}[-/](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[-/]\d{2})\b',  # 2000-jun-03
        r'\b(?:\d{4}[-/]\d{2}[-/]\d{2})\b',  # 2000-06-03
        r'\b(?:\d{2}[-/]\d{2}[-/]\d{4})\b'  # 03-06-2000
    ]
    
    dates = []
    date_lines = []

    for pattern in date_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            dates.append(match.group())
            line_number = text[:match.start()].count('\n') + 1
            date_lines.append(line_number)

    return dates, date_lines

# Function to process the resume text and extract project details
def process_resume(text, technologies):
    lines = text.split("\n")
    project_details = []
    total_duration_days = 0
    unique_technologies = set()
    projects_found = False

    current_project_name = None
    current_technologies = []
    current_dates = []
    collecting_description = False

    for line in lines:
        line = line.strip()

        # Detecting project lines
        if line.lower().startswith('project:'):
            projects_found = True
            collecting_description = False

        project_match = re.match(r'^project:\s*(.*)', line, re.IGNORECASE)
        if project_match:
            if current_project_name:  # Save the previous project
                duration = ""
                if len(current_dates) >= 2:
                    start_date = parse_date(current_dates[0])
                    end_date = parse_date(current_dates[1])
                    if start_date and end_date:
                        duration_days = (end_date - start_date).days
                        total_duration_days += duration_days
                        duration = f"{duration_days} days"

                project_details.append({
                    "project_name": current_project_name,
                    "technologies": ", ".join(current_technologies),
                    "fraction": f"{len(current_technologies)}/{len(technologies)}",
                    "duration": duration
                })

            current_project_name = project_match.group(1).strip()
            current_technologies = []
            current_dates = []
            collecting_description = True

        # Extracting technologies for the current project
        tech_match = re.match(r'^technologies:\s*(.*)', line, re.IGNORECASE)
        if tech_match:
            tech_str = tech_match.group(1).strip().lower()
            current_technologies = [tech.strip() for tech in tech_str.split(",") if tech.strip() in technologies]
            unique_technologies.update(current_technologies)

        # Extracting dates for the current project
        dates, _ = find_dates(line)
        current_dates.extend(dates)

    # Add the last project if not added
    if current_project_name:
        duration = ""
        if len(current_dates) >= 2:
            start_date = parse_date(current_dates[0])
            end_date = parse_date(current_dates[1])
            if start_date and end_date:
                duration_days = (end_date - start_date).days
                total_duration_days += duration_days
                duration = f"{duration_days} days"

        project_details.append({
            "project_name": current_project_name,
            "technologies": ", ".join(current_technologies),
            "fraction": f"{len(current_technologies)}/{len(technologies)}",
            "duration": duration
        })

    return {
        "project_details": project_details,
        "total_duration": f"{total_duration_days} days",
        "unique_technologies": unique_technologies,
        "projects_found": projects_found
    }

# Function to display a summary table for project details
# Function to display a summary table for project details
def display_table(results, total_technologies):
    project_table = []
    total_duration = 0
    total_fraction = 0

    for project in results['project_details']:
        project_duration = project.get('duration', 'N/A')
        
        if project_duration != 'N/A' and project_duration.split() and project_duration.split()[0].isdigit():
            project_duration_days = int(project_duration.split()[0])
            total_duration += project_duration_days
        else:
            project_duration_days = 0

        technologies_used = project.get('technologies', '')
        fraction = len(technologies_used.split(',')) / total_technologies if total_technologies > 0 else 0.0
        total_fraction += fraction

        project_table.append({
            'project_name': project.get('project_name', 'N/A'),
            'technologies': technologies_used,
            'duration': project_duration,
            'fraction': f"{len(technologies_used.split(','))}/{total_technologies}"
        })

    return project_table, f"{total_duration} days", f"{total_fraction}/{len(results['project_details'])}"

# Function to display an elaborate summary of the projects
def display_elaborate_summary(results, lines, technologies):
    elaborate_summary = []
    total_fraction = 0

    for project in results['project_details']:
        project_name = project.get('project_name', 'N/A')
        technologies_used = project.get('technologies', '')
        project_duration = project.get('duration', 'N/A')
        project_lines = []

        for i, line in enumerate(lines):
            if project_name.lower() in line.lower():
                project_lines.append(i + 1)

        fraction = len(technologies_used.split(',')) / len(technologies) if len(technologies) > 0 else 0.0
        total_fraction += fraction

        elaborate_summary.append({
            'project_name': project_name,
            'technologies': technologies_used,
            'duration': project_duration,
            'lines': project_lines,
            'fraction': f"{len(technologies_used.split(','))}/{len(technologies)}"
        })

    return elaborate_summary, f"{total_fraction}/{len(results['project_details'])}"

@app.route('/')
def index():
    return render_template('index_v1.html')

@app.route('/compare', methods=['POST'])
def compare():
    global technologies, keywords, ability_words  # Use global variables
    
    resume_directory = request.form['resume_directory']
    job_desc_directory = request.form['job_desc_directory']

    if not resume_directory or not job_desc_directory:
        return redirect(url_for('index'))

    # Store directories in session
    session['resume_directory'] = resume_directory
    session['job_desc_directory'] = job_desc_directory

    technologies_path = os.path.join(job_desc_directory, 'Technologies.txt')
    keywords_path = os.path.join(job_desc_directory, 'keywords.txt')
    ability_words_path = os.path.join(job_desc_directory, 'ability_words.txt')

    missing_files = []
    if not os.path.exists(technologies_path):
        missing_files.append('Technologies.txt')
    if not os.path.exists(keywords_path):
        missing_files.append('keywords.txt')
    if not os.path.exists(ability_words_path):
        missing_files.append('ability_words.txt')

    if missing_files:
        return f"Files not found: {', '.join(missing_files)}", 400

    technologies = read_technologies(technologies_path)
    keywords = read_keywords(keywords_path)
    ability_words = read_ability_words(ability_words_path)
    comparison_data = []

    for resume_filename in os.listdir(resume_directory):
        resume_path = os.path.join(resume_directory, resume_filename)
        if not os.path.isfile(resume_path):
            continue

        file_ext = os.path.splitext(resume_filename)[1].lower()
        if file_ext == '.pdf':
            text = read_pdf(resume_path)
        elif file_ext == '.docx':
            text = read_docx(resume_path)
        else:
            continue  # Skip unsupported file formats
            
        # Write raw data to a file
        write_raw_data('resume_raw_data.txt', text)
        
        tech_counts = count_words(text, technologies)
        keyword_counts = count_words(text, keywords)
        ability_word_counts = count_words(text, ability_words)

        matched_tech_count = sum(1 for count in tech_counts.values() if count > 0)
        total_technologies = len(technologies)
        tech_matched_fraction = matched_tech_count / total_technologies if total_technologies > 0 else 0.0
        tech_similarity_percentage = round(tech_matched_fraction * 100, 2)

        matched_keyword_count = sum(1 for count in keyword_counts.values() if count > 0)
        total_keywords = len(keywords)
        keyword_matched_fraction = matched_keyword_count / total_keywords if total_keywords > 0 else 0.0
        keyword_similarity_percentage = round(keyword_matched_fraction * 100, 2)

        matched_ability_word_count = sum(1 for count in ability_word_counts.values() if count > 0)
        total_ability_words = len(ability_words)
        ability_word_matched_fraction = matched_ability_word_count / total_ability_words if total_ability_words > 0 else 0.0
        ability_word_similarity_percentage = round(ability_word_matched_fraction * 100, 2)

        total_terms = total_technologies + total_keywords + total_ability_words
        total_matched_count = matched_tech_count + matched_keyword_count + matched_ability_word_count
        total_matched_fraction = total_matched_count / total_terms if total_terms > 0 else 0.0
        total_similarity_percentage = round(total_matched_fraction * 100, 2)

        comparison_data.append({
            'filename': resume_filename,
            'tech_counts': tech_counts,
            'keyword_counts': keyword_counts,
            'ability_word_counts': ability_word_counts,
            'tech_similarity_percentage': tech_similarity_percentage,
            'keyword_similarity_percentage': keyword_similarity_percentage,
            'ability_word_similarity_percentage': ability_word_similarity_percentage,
            'total_similarity_percentage': total_similarity_percentage
        })

    # Store the comparison data in session
    session['comparison_data'] = comparison_data

    # Sort the comparison_data by total_similarity_percentage in descending order
    comparison_data.sort(key=lambda x: x['total_similarity_percentage'], reverse=True)

    return render_template('compare_v1.html', comparison_data=comparison_data, technologies=technologies, keywords=keywords, ability_words=ability_words)


@app.route('/result')
def result():
    filename = request.args.get('filename')
    file_ext = os.path.splitext(filename)[1].lower()
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if file_ext == '.pdf':
        text = read_pdf(file_path)
    elif file_ext == '.docx':
        text = read_docx(file_path)
    else:
        return jsonify({'error': 'Unsupported file format'})

    # Retrieve directories from session
    resume_directory = session.get('resume_directory')
    job_desc_directory = session.get('job_desc_directory')

    technologies_path = os.path.join(job_desc_directory, 'Technologies.txt')
    keywords_path = os.path.join(job_desc_directory, 'keywords.txt')
    ability_words_path = os.path.join(job_desc_directory, 'ability_words.txt')

    technologies = read_technologies(technologies_path)
    keywords = read_keywords(keywords_path)
    ability_words = read_ability_words(ability_words_path)

    technology_count = count_words(text, technologies)
    keyword_count = count_words(text, keywords)
    ability_word_count = count_words(text, ability_words)

    num_pages = count_pages(file_path, file_ext)
    results = process_resume(text, technologies)

    project_table, total_duration, total_fraction = display_table(results, len(technologies))
    elaborate_summary, total_fraction_summary = display_elaborate_summary(results, text.split("\n"), technologies)

    # Retrieve comparison data from session
    comparison_data = session.get('comparison_data')
    resume_comparison_data = next((item for item in comparison_data if item['filename'] == filename), None)

    return render_template('result_v1.html', 
                           filename=filename, 
                           technology_count=technology_count,
                           keyword_count=keyword_count,
                           ability_word_count=ability_word_count,
                           num_pages=num_pages,
                           project_table=project_table,
                           total_duration=total_duration,
                           total_fraction=total_fraction,
                           elaborate_summary=elaborate_summary,
                           total_fraction_summary=total_fraction_summary,
                           resume_comparison_data=resume_comparison_data)

if __name__ == '__main__':
    app.run(debug=True)