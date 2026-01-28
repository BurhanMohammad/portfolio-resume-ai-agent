#!/usr/bin/env python3
"""
amop_staff_agent_resume_updater.py

Senior Staff Engineer Resume Sync Agent

Behavior:
- Uses litellm
- Reads FULL PDF + FULL HTML
- Semantically matches entities (Experience, Skills, Projects, etc.)
- Updates existing entries if same entity
- Adds missing entries
- NEVER deletes HTML-only content
- Preserves structure, layout, classes, IDs
- FULL file replacement with backup
"""

import os
import time
import json
import shutil
import hashlib
from typing import Dict, List

# ===========================
# CONFIG
# ===========================
MODEL_WAIT_SECONDS = 15
BACKUP_SUFFIX = ".bak_aiagent"
CACHE_FILENAME = ".resume_ai_cache.json"

DEFAULT_ROOT = r"C:\Users\Admin\Downloads\burhanmohammad.github.io-main\burhanmohammad.github.io-main"
PDF_RELATIVE_PATH = r"assets\resume\Mohammad_Burhan_Resume.pdf"

# Using a more powerful model for better HTML understanding
MODEL_ID = "openrouter/meta-llama/llama-3.3-70b-instruct:free"

# ===========================
# LLM (litellm)
# ===========================
from litellm import completion
from litellm.exceptions import APIError
from dotenv import load_dotenv
load_dotenv(override=True)

def get_api_key() -> str:
    api_key = # api key 
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment or .env")
    return api_key

def generate_response(messages: List[Dict], retries: int = 3) -> str:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = completion(
                model=MODEL_ID,
                messages=messages,
                max_tokens=12000,  # Increased for full HTML
                api_key=get_api_key(),
                timeout=120,  # Increased timeout
            )
            return resp.choices[0].message.content
        except APIError as e:
            last_error = e
            print(f"⚠️ LLM error (attempt {attempt}), retrying...")
            time.sleep(3 * attempt)
        except Exception as e:
            last_error = e
            break
    raise RuntimeError(f"LLM failed: {last_error}")

# ===========================
# DETERMINISTIC CACHE
# ===========================
def _load_cache() -> Dict[str, str]:
    if os.path.exists(CACHE_FILENAME):
        try:
            with open(CACHE_FILENAME, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_cache(cache: Dict[str, str]):
    with open(CACHE_FILENAME, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def cached_generate(messages: List[Dict]) -> str:
    key_src = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    cache = _load_cache()
    if key in cache:
        return cache[key]
    resp = generate_response(messages)
    cache[key] = resp
    _save_cache(cache)
    return resp

# ===========================
# FILE UTILITIES
# ===========================
def backup_file(path: str) -> str:
    backup = path + BACKUP_SUFFIX
    shutil.copy2(path, backup)
    return backup

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def write_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ===========================
# PDF EXTRACTION
# ===========================
def extract_pdf_text(pdf_path: str) -> str:
    import PyPDF2
    text = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text.append(page.extract_text() or "")
    return "\n".join(text).strip()

# ===========================
# PROMPTS (STAFF-GRADE, GLOBAL)
# ===========================
def system_prompt() -> str:
    return """You are a Senior Staff Software Engineer tasked with synchronizing an HTML resume page with a PDF resume.

CRITICAL RULES:
1. Preserve EXACT HTML structure, CSS classes, IDs, and formatting
2. Update text content ONLY - never modify HTML tags, attributes, or layout
3. Match sections semantically (Experience, Skills, Projects, Education, etc.)
4. For entities in both HTML and PDF: update HTML content to match PDF
5. For entities only in PDF: add them to appropriate sections
6. For entities only in HTML: keep them unchanged (DO NOT DELETE)
7. Maintain chronological order where applicable
8. Keep all original HTML comments and conditional code
9. Return the FULL, complete HTML file - not just changes

PRIORITY SECTIONS TO SYNC:
1. Summary/Introduction (resume-intro section)
2. Work Experiences (work-section)
3. Technical Skills (skills-section > Technical)
4. Projects (project-section)
5. Certifications (education-section for awards)
6. Languages
7. Education
8. Interests
9. Professional Skills (skills-section > Professional)

HTML STRUCTURE PRESERVATION:
- Keep all <div>, <section>, <ul>, <li> with same classes/IDs
- Maintain same number of columns and layout
- Preserve all social links, navigation, headers, footers
- Keep all script and style tags exactly as-is
- Maintain dark mode toggle and configuration panel"""

def build_resume_update_messages(
    html_path: str,
    html_content: str,
    pdf_text: str
) -> List[Dict]:
    return [
        {"role": "system", "content": system_prompt()},
        {
            "role": "user",
            "content": f"""TASK: Synchronize the HTML resume content with the PDF resume content.

PDF RESUME (SOURCE OF TRUTH):
{pdf_text}
CURRENT HTML FILE ({html_path}):
{html_content}


SPECIFIC UPDATES REQUIRED (based on manual analysis):

1. SUMMARY/RESUME-INTRO:
   - Update to match PDF summary exactly
   - Should mention "5 years of experience" and backend-first systems

2. WORK EXPERIENCES (Chronological order):
   a) Alogonox Technologies (August 2024 - Present)
      - Update title to "Software Engineer"
      - Add all bullet points from PDF
      
   b) Seewise.ai (September 2023 - April 2024)  
      - Update title to "Software Development Engineer"
      - Add all bullet points from PDF
      
   c) Codent Software Solutions (2021 - 2023)
      - Keep but update end date to 2023
      - Update bullets from original HTML
      
   d) Headrun (February 2020 - July 2020)
      - Update location to "Vijayawada, INDIA"
      - Use bullet points from PDF

3. TECHNICAL SKILLS:
   - Reorganize to match PDF: Languages, Backend and APIs, Frontend, Databases, Cloud & DevOps, Testing & Quality, Architecture, Security & Auth
   - Include all skills from PDF: Python, JavaScript, SQL, Django, FastAPI, PostgreSQL, AWS, React.js, etc.
   - Keep HTML structure but update list items

4. PROJECTS SECTION:
   - Replace with PDF projects: AI Resume Parser, Real-time Video Call Platforms, Django/React Apps
   - Add "Technical Expertise" subsection as in PDF
   - Remove old detailed project lists, keep only what's in PDF

5. CERTIFICATIONS:
   - Update order to match PDF: Full Stack, Career Essentials, Programming in Python
   - Fix spelling of "Coursera"

6. LANGUAGES:
   - Update order: Telugu, Hindi, English, Tamil, Urdu
   - Update proficiency levels to match PDF

7. EDUCATION:
   - Add "PRIST University" as institution

8. INTERESTS:
   - Update to: Tech Operations, Conducting Workshops, Basketball, Fitness, Travelling

9. TAGLINE:
   - Update to: "Software Engineer (Backend - Python, Django, FastAPI, PostgreSQL, AWS)"

10. PORTFOLIO URL:
    - Update to: "burhanmohammad.github.io"

IMPORTANT: Preserve ALL HTML structure, classes, IDs, and formatting. Only update text content.
Return the COMPLETE updated HTML file."""
        }
    ]

# ===========================
# UPDATE FLOW
# ===========================
def update_resume_flow(root: str, html_rel_path: str):
    html_path = os.path.join(root, html_rel_path)
    pdf_path = os.path.join(root, PDF_RELATIVE_PATH)

    if not os.path.exists(html_path):
        print(f"❌ HTML file not found: {html_path}")
        return
    if not os.path.exists(pdf_path):
        print(f"❌ PDF resume not found: {pdf_path}")
        return

    print(f"📄 Reading HTML: {html_path}")
    html_content = read_file(html_path)

    print(f"📄 Reading PDF: {pdf_path}")
    pdf_text = extract_pdf_text(pdf_path)
    
    print(f"📊 PDF text length: {len(pdf_text)} characters")
    print(f"📊 HTML content length: {len(html_content)} characters")

    print("⏳ Sending FULL HTML + FULL PDF to LLM...")
    messages = build_resume_update_messages(html_path, html_content, pdf_text)

    time.sleep(MODEL_WAIT_SECONDS)
    print("🔄 Generating updated HTML...")
    updated_html = cached_generate(messages).strip()

    # Validate output
    if "<!DOCTYPE html>" not in updated_html[:100].lower() and "<html" not in updated_html[:200].lower():
        print("❌ Output doesn't start with HTML doctype. Checking for partial HTML...")
        # Try to find where HTML might start
        html_start = updated_html.lower().find("<html")
        if html_start > 0:
            print(f"⚠️ Found HTML starting at position {html_start}, trimming...")
            updated_html = updated_html[html_start:]
        else:
            print("❌ Output does not contain valid HTML. Aborting.")
            print("First 500 chars of output:")
            print(updated_html[:500])
            return

    print("\n=== PREVIEW (first 1000 chars) ===")
    print(updated_html[:1000])

    # Basic validation
    if len(updated_html) < 5000:
        print(f"⚠️ Warning: Updated HTML seems very short ({len(updated_html)} chars)")
    
    # Check for key sections
    if "Mohammad Burhan" not in updated_html:
        print("⚠️ Warning: Name not found in output")
    
    if "Software Engineer" not in updated_html:
        print("⚠️ Warning: Key title not found in output")

    # Backup and apply
    backup_needed = True
    if os.path.exists(html_path + BACKUP_SUFFIX):
        backup_needed = input(f"Backup exists. Create new backup? (y/N): ").strip().lower() == 'y'
    
    if input("\nApply FULL HTML update? (y/N): ").strip().lower() == "y":
        if backup_needed:
            backup = backup_file(html_path)
            print(f"🗂 Backup created: {backup}")
        
        write_file(html_path, updated_html)
        print("✅ Resume synchronized successfully.")
        
        # Show diff summary
        original_lines = html_content.count('\n')
        updated_lines = updated_html.count('\n')
        print(f"📈 Lines changed: {original_lines} → {updated_lines}")
        
        # Quick content check
        if "Alogonox" in updated_html and "Seewise.ai" in updated_html:
            print("✓ New companies added successfully")
        if "PRIST University" in updated_html:
            print("✓ Education updated successfully")
            
    else:
        print("❌ Update cancelled.")

# ===========================
# CLI
# ===========================
def interactive_agent(root: str):
    print(f"\n🔍 Project root: {root}")
    print("Commands:")
    print("  update <htmlfile>  - Update specific HTML file")
    print("  update resume      - Update resume.html (common path)")
    print("  ls                 - List HTML files in root")
    print("  exit               - Exit program")

    while True:
        cmd = input("\n> ").strip()
        if not cmd:
            continue
        if cmd == "exit":
            break
        elif cmd == "ls":
            # List HTML files
            for file in os.listdir(root):
                if file.endswith('.html'):
                    print(f"  {file}")
        elif cmd == "update resume":
            # Common resume paths
            common_paths = [
                "resume.html",
                "index.html",
                os.path.join("templates", "resume.html"),
                os.path.join("pages", "resume.html")
            ]
            found = False
            for path in common_paths:
                full_path = os.path.join(root, path)
                if os.path.exists(full_path):
                    update_resume_flow(root, path)
                    found = True
                    break
            if not found:
                print("❌ Could not find resume.html. Try 'update <fullpath>'")
        elif cmd.startswith("update "):
            parts = cmd.split(maxsplit=1)
            if len(parts) == 2:
                update_resume_flow(root, parts[1])
            else:
                print("Usage: update <htmlfile>")
        else:
            print("Unknown command.")

# ===========================
# ENTRYPOINT
# ===========================
if __name__ == "__main__":
    print("=" * 60)
    print("Senior Staff Resume Sync Agent (litellm)")
    print("=" * 60)
    
    root = input(f"Project root [{DEFAULT_ROOT}]: ").strip() or DEFAULT_ROOT
    if not os.path.exists(root):
        print(f"❌ Path does not exist: {root}")
        exit(1)
    
    interactive_agent(root)
