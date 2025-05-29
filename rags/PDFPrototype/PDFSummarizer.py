import os
import re  # For parsing markdown-like syntax
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# LlamaIndex imports
from llama_index.llms.gemini import Gemini

# PDF Creation imports (ReportLab)
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors

# --- Configuration ---
# Ensure your GOOGLE_API_KEY is set in your environment variables
API_KEY = os.getenv("GOOGLE_API_KEY")
# Using a more capable model is recommended for better adherence to complex formatting instructions
MODEL_NAME = "models/gemini-2.0-flash"  # Or "models/gemini-pro" if 1.5 is not available
OUTPUT_DIR = "final_documents"


# --- PDF Helper Function with Markdown-like Parsing ---
def create_structured_pdf(output_filepath: str, generated_content: str):
    """
    Creates a PDF document by parsing markdown-like syntax from the generated_content.
    The first H1 heading (#) is used as the PDF's main title.
    """
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    doc = SimpleDocTemplate(output_filepath)

    styles = getSampleStyleSheet()

    # Define custom styles based on markdown
    styles.add(ParagraphStyle(name='MarkdownH1',
                              parent=styles['h1'],
                              fontSize=24,
                              leading=28,
                              spaceBefore=20,
                              spaceAfter=10,
                              alignment=TA_CENTER,
                              textColor=colors.HexColor('#2C3E50')))  # Dark Blue/Grey
    styles.add(ParagraphStyle(name='MarkdownH2',
                              parent=styles['h2'],
                              fontSize=18,
                              leading=22,
                              spaceBefore=16,
                              spaceAfter=8,
                              textColor=colors.HexColor('#34495E')))  # Slightly Lighter Dark Blue/Grey
    styles.add(ParagraphStyle(name='MarkdownH3',
                              parent=styles['h3'],
                              fontSize=14,
                              leading=18,
                              spaceBefore=12,
                              spaceAfter=6,
                              textColor=colors.HexColor('#7F8C8D')))  # Grey
    styles.add(ParagraphStyle(name='MarkdownBody',
                              parent=styles['Normal'],
                              spaceBefore=6,
                              spaceAfter=6,
                              leading=15,  # Increased leading for readability
                              alignment=TA_LEFT,
                              fontSize=11))
    styles.add(ParagraphStyle(name='MarkdownListItem',
                              parent=styles['Normal'],
                              spaceBefore=3,
                              spaceAfter=3,
                              leading=15,
                              leftIndent=20,
                              bulletIndent=5,  # Adjust for bullet alignment
                              fontSize=11))

    story = []
    lines = generated_content.split('\n')

    pdf_main_title_text = "Untitled Document"  # Fallback
    first_h1_processed = False

    for i, line_raw in enumerate(lines):
        line = line_raw.strip()

        # Pre-process line for inline bold: **text** to <b>text</b>
        # This needs to be done carefully to not interfere with other markdown
        processed_line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)

        current_style = styles['MarkdownBody']
        text_to_add = processed_line
        is_list_item = False

        if line.startswith("# "):
            current_style = styles['MarkdownH1']
            text_to_add = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line[2:].strip())
            if not first_h1_processed:
                pdf_main_title_text = line[2:].strip()  # Store the raw text for title
                story.append(Paragraph(text_to_add, current_style))
                story.append(Spacer(1, 0.2 * inch))  # Extra space after main title
                first_h1_processed = True
                continue  # Skip adding it again below if it was the main title
        elif line.startswith("## "):
            current_style = styles['MarkdownH2']
            text_to_add = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line[3:].strip())
        elif line.startswith("### "):
            current_style = styles['MarkdownH3']
            text_to_add = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line[4:].strip())
        elif line.startswith("* ") or line.startswith("- "):
            current_style = styles['MarkdownListItem']
            # text_to_add is already `processed_line` which has bold conversion
            text_to_add = processed_line[2:].strip()
            is_list_item = True
        elif not line:  # Empty line
            if story and not isinstance(story[-1], Spacer):  # Add spacer if not already one
                story.append(Spacer(1, 0.15 * inch))
            continue  # Skip adding paragraph for empty line

        if text_to_add:  # Ensure there's text to add
            if is_list_item:
                story.append(Paragraph(text_to_add, current_style, bulletText='•'))
            else:
                story.append(Paragraph(text_to_add, current_style))

    if not story:  # Handle case where no content was parsed (e.g., empty LLM response)
        story.append(Paragraph("Content generation failed or produced no parseable output.", styles['MarkdownBody']))

    try:
        doc.build(story)
        print(f"Successfully created PDF: {output_filepath}")
        return pdf_main_title_text  # Return the extracted title
    except Exception as e:
        print(f"Error creating PDF: {e}")
        print("Content that was attempted to be written (first 500 chars):")
        print("-----------------------------------------")
        print(generated_content[:500])
        print("-----------------------------------------")
        return "Error_In_PDF_Creation"


# --- Main Script Logic ---
def main():
    if not API_KEY:
        print("ERROR: GOOGLE_API_KEY environment variable not set.")
        print("Please set it before running the script. Get one from https://aistudio.google.com/app/apikey")
        return

    print(f"Initializing Gemini LLM ({MODEL_NAME}) via LlamaIndex...")
    try:
        llm = Gemini(api_key=API_KEY, model_name=MODEL_NAME)
    except Exception as e:
        print(f"Error initializing Gemini LLM: {e}")
        print("Ensure 'google-generativeai' and 'llama-index-llms-gemini' are installed and API key is valid.")
        return

    print("-" * 50)
    user_document_request = input(
        "Enter the type of document you want to create (e.g., 'a business plan for a coffee shop', 'a technical guide for setting up a home server'): \n> ")

    # Construct the detailed prompt for Gemini
    # This prompt is CRITICAL for getting the desired output format and tone
    system_prompt_for_gemini = f"""
You are a professional document architect AI. Your sole purpose is to generate a complete, well-structured, and fully formatted document based on the user's request. The document must be ready for immediate professional use.

MANDATORY FORMATTING AND CONTENT RULES:
1.  **Document Title (H1):** The VERY FIRST line of your output MUST be the main title of the document, formatted as an H1 heading (e.g., `# My Document Title`). This title should be concise and accurately reflect the document's content.
2.  **Section Headings (H2):** Use H2 headings for all major sections (e.g., `## Introduction`, `## Key Features`).
3.  **Subsection Headings (H3):** Use H3 headings for subsections if necessary (e.g., `### Subsection Detail`).
4.  **Bold Text:** Use double asterisks for **bold emphasis** on key terms or phrases (e.g., `**Important:** This is critical.`).
5.  **Lists:** Use bullet points for unordered lists, starting each item with `* ` (asterisk followed by a space) or `- ` (hyphen followed by a space).
6.  **Paragraphs:** Ensure clear separation between paragraphs (a single blank line in the markdown source).
7.  **Content Only:** Your output MUST consist ONLY of the document content itself, starting with the H1 title.

ABSOLUTELY DO NOT INCLUDE ANY OF THE FOLLOWING:
- Conversational introductions or closings (e.g., "Okay, here is...", "I hope this helps...", "Certainly,...").
- Disclaimers or warnings about the content (e.g., "I am an AI model...", "This is not legal advice...", "Please consult a professional...").
- Explanations of the formatting you are using.
- Self-references or apologies.
- Any text whatsoever before the H1 document title.
- Any text whatsoever after the final piece of document content.

The output should be pure, structured markdown, perfectly adhering to these rules, ready for direct conversion to a polished PDF.

USER'S DOCUMENT REQUEST: "{user_document_request}"
"""

    print("\nGenerating structured document with Gemini... This may take a few moments.")

    try:
        # For LlamaIndex, the `complete` method is used for direct LLM calls.
        response = llm.complete(system_prompt_for_gemini)
        generated_content = response.text.strip()  # Strip leading/trailing whitespace

        if not generated_content:
            print("Gemini returned empty content. Please try a different prompt or check the model/API key.")
            return

    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return

    print("\n--- Gemini's Raw Generated Content (Preview) ---")
    print(generated_content[:800] + ("..." if len(generated_content) > 800 else ""))
    print("--- End of Preview ---")

    # Extract the H1 title from the generated content for the filename
    filename_base = "Generated_Document"  # Default
    match = re.match(r"#\s*(.*)", generated_content)  # Match first line if it's H1
    if match:
        title_text = match.group(1).strip()
        if title_text:  # Ensure title is not empty
            # Sanitize for filename: remove non-alphanumeric, replace spaces with underscores
            filename_base = re.sub(r'[^\w\s-]', '', title_text)
            filename_base = re.sub(r'[-\s]+', '_', filename_base).strip('_')
            filename_base = filename_base[:60]  # Limit length to avoid overly long filenames
            if not filename_base:  # If title was all special chars and became empty
                filename_base = "Document"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"{filename_base}_{timestamp}.pdf"
    pdf_filepath = os.path.join(OUTPUT_DIR, pdf_filename)

    print(f"\nAttempting to create PDF: {pdf_filepath}")

    # The create_structured_pdf function will use the generated_content to build the PDF.
    # It also tries to extract the H1 for the PDF's internal title.
    pdf_title = create_structured_pdf(pdf_filepath, generated_content)

    if pdf_title and pdf_title not in ["Untitled Document", "Error_In_PDF_Creation"]:
        print(f"PDF generated. Document title appears to be: '{pdf_title}'")
    elif pdf_title == "Error_In_PDF_Creation":
        print("PDF creation failed. Please check the error messages and the raw generated content.")
    else:
        print("PDF generated, but a specific title could not be robustly extracted from the content for confirmation.")


if __name__ == "__main__":
    main()