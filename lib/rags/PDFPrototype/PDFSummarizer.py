import os
import re
from datetime import datetime

# LlamaIndex imports
from llama_index.llms.gemini import Gemini

# PDF Creation imports (ReportLab)
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable, Image, Table, TableStyle
)
# from reportlab.platypus.tableofcontents import TableOfContents # For potential future use
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = "models/gemini-2.0-flash"  # Or your preferred Gemini model
OUTPUT_DIR = "publish_ready_documents_enhanced"

# --- Font and Layout Configuration ---
FONT_BODY = "Times-Roman"
FONT_BODY_BOLD = "Times-Bold"
FONT_BODY_ITALIC = "Times-Italic"
FONT_BODY_BOLD_ITALIC = "Times-BoldItalic"

FONT_HEADING = "Helvetica-Bold"  # Sans-serif for headings for contrast and modernity
FONT_HEADING_LIGHT = "Helvetica"  # For less prominent text like footers

# Margins
PAGE_MARGIN_HORIZONTAL = 0.8 * inch
PAGE_MARGIN_VERTICAL = 0.8 * inch

# Colors
COLOR_TEXT_BODY = colors.HexColor('#111111')
COLOR_TEXT_HEADING_MAJOR = colors.HexColor('#223A5E')  # Deep Blue
COLOR_TEXT_HEADING_MINOR = colors.HexColor('#2E4A7D')  # Slightly Lighter Blue
COLOR_TEXT_HEADING_SUBTLE = colors.HexColor('#485F8A')
COLOR_ACCENT_LINE = colors.HexColor('#AAAAAA')  # Softer Grey for HR and footer line
COLOR_FOOTER_TEXT = colors.HexColor('#666666')


# --- Custom Flowable for Horizontal Rule ---
class HRFlowable(Flowable):
    def __init__(self, width, thickness=0.5, color=COLOR_ACCENT_LINE, spaceBefore=0.1 * inch, spaceAfter=0.1 * inch):
        Flowable.__init__(self)
        self.width = width  # This will be set to availWidth in wrap
        self.thickness = thickness
        self.color = color
        self.spaceBefore = spaceBefore
        self.spaceAfter = spaceAfter
        # The height includes the line itself and the spacing
        self.height = self.thickness + self.spaceBefore + self.spaceAfter

    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        # Draw the line considering the spaceBefore, so it appears after spaceBefore
        # and spaceAfter is below the line.
        # Line is drawn at y=spaceAfter from the bottom of its allocated space.
        self.canv.line(0, self.spaceAfter, self.width, self.spaceAfter)
        self.canv.restoreState()

    def wrap(self, availWidth, availHeight):
        self.width = availWidth  # Take full available width
        return (availWidth, self.height)


# --- PDF Document Class with Headers/Footers ---
class EnhancedPDFTemplate(SimpleDocTemplate):
    def __init__(self, filename, **kwargs):
        self.doc_title = kwargs.pop('doc_title', "Generated Document")
        # self.author_name = kwargs.pop('author_name', "AI Document Generator") # Example
        self.creation_date = datetime.now().strftime("%B %d, %Y")

        super().__init__(filename, **kwargs)
        self.leftMargin = PAGE_MARGIN_HORIZONTAL
        self.rightMargin = PAGE_MARGIN_HORIZONTAL
        self.topMargin = PAGE_MARGIN_VERTICAL
        self.bottomMargin = PAGE_MARGIN_VERTICAL
        self.allowSplitting = 1
        self.splitLongParagraphs = 1

    def _draw_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT_HEADING_LIGHT, 8)  # Using a common light font for footer
        canvas.setFillColor(COLOR_FOOTER_TEXT)

        # Line above footer
        line_y_pos = self.bottomMargin - 0.15 * inch
        canvas.setStrokeColor(COLOR_ACCENT_LINE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, line_y_pos,
                    doc.width + doc.leftMargin, line_y_pos)

        footer_text_y_pos = self.bottomMargin - 0.35 * inch
        footer_text_left = f"{self.doc_title}"
        footer_text_right = f"Page {doc.page}"

        canvas.drawString(doc.leftMargin, footer_text_y_pos, footer_text_left)
        canvas.drawRightString(doc.width + doc.leftMargin, footer_text_y_pos, footer_text_right)
        canvas.restoreState()

    def laterPages(self, canvas, doc):
        self._draw_footer(canvas, doc)

    def firstPage(self, canvas, doc):
        self._draw_footer(canvas, doc)  # Consistent footer for now


# --- Style Definition Function ---
def define_pdf_styles():
    styles = getSampleStyleSheet()

    # Base Normal/Body Text Style (Modifying 'Normal' for density)
    styles['Normal'].fontName = FONT_BODY
    styles['Normal'].fontSize = 10
    styles['Normal'].leading = 12  # 1.2x font size for compactness
    styles['Normal'].textColor = COLOR_TEXT_BODY
    styles['Normal'].alignment = TA_JUSTIFY
    styles['Normal'].spaceBefore = 0.05 * inch  # Minimal space
    styles['Normal'].spaceAfter = 0.1 * inch  # Standard paragraph separation
    styles['Normal'].splitLongParagraphs = 1
    # styles['Normal'].hyphenationLang = 'en_US' # Requires ReportLab PLUS

    # Main Document Title
    styles.add(ParagraphStyle(name='DocTitle',
                              fontName=FONT_HEADING,
                              fontSize=22,
                              leading=28,  # Generous leading for title
                              alignment=TA_CENTER,
                              textColor=COLOR_TEXT_HEADING_MAJOR,
                              spaceBefore=0,  # No space before the main title
                              spaceAfter=0.25 * inch))  # Good space after main title

    # Headings
    styles.add(ParagraphStyle(name='H1Style',
                              parent=styles['Normal'],  # Inherit basic properties
                              fontName=FONT_HEADING,
                              fontSize=16,
                              leading=19,  # 1.2x
                              textColor=COLOR_TEXT_HEADING_MAJOR,
                              spaceBefore=0.2 * inch,  # More space before major headings
                              spaceAfter=0.1 * inch,
                              keepWithNext=1))  # Keep heading with the paragraph that follows

    styles.add(ParagraphStyle(name='H2Style',
                              parent=styles['Normal'],
                              fontName=FONT_HEADING,
                              fontSize=13,
                              leading=16,  # 1.2x
                              textColor=COLOR_TEXT_HEADING_MINOR,
                              spaceBefore=0.18 * inch,  # Slightly less than H1
                              spaceAfter=0.09 * inch,
                              keepWithNext=1))

    styles.add(ParagraphStyle(name='H3Style',
                              parent=styles['Normal'],
                              fontName=FONT_HEADING,  # Still bold, but smaller
                              fontSize=11,  # Closer to body text size
                              leading=14,  # 1.2x
                              textColor=COLOR_TEXT_HEADING_SUBTLE,
                              spaceBefore=0.15 * inch,
                              spaceAfter=0.08 * inch,
                              keepWithNext=1))

    # List Item Style
    styles.add(ParagraphStyle(name='ListItemStyle',
                              parent=styles['Normal'],  # Base on Normal for font, size, color
                              leftIndent=0.25 * inch,
                              bulletIndent=0.05 * inch,  # Space for bullet before text starts
                              spaceBefore=0.02 * inch,  # Tight list item spacing
                              spaceAfter=0.02 * inch,
                              bulletFontName=FONT_BODY,  # Consistent bullet font
                              bulletFontSize=10,
                              firstLineIndent=0))  # Standard hanging indent for bullets

    # For paragraphs that are entirely bold (e.g., sub-headings without formal Hx style)
    styles.add(ParagraphStyle(name='BoldBodyText',
                              parent=styles['Normal'],
                              fontName=FONT_BODY_BOLD))

    # Signature Field Style (e.g., "Name: __________")
    styles.add(ParagraphStyle(name='SignatureField',
                              parent=styles['Normal'],
                              fontSize=10,  # Match body text
                              leading=20,  # MORE leading to give space for handwritten signature
                              spaceBefore=0.15 * inch,  # Space above the signature line
                              spaceAfter=0.05 * inch))  # Space after signature line

    return styles


# --- Enhanced PDF Creation Function ---
def create_enhanced_pdf(output_filepath: str, generated_content: str, document_title_from_llm: str):
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    doc = EnhancedPDFTemplate(output_filepath, doc_title=document_title_from_llm)
    styles = define_pdf_styles()

    story = []

    # Add the main document title at the very beginning
    if document_title_from_llm and document_title_from_llm.strip() != "Untitled Document":
        # Clean any markdown from the title string itself for display
        clean_display_title = re.sub(r'[\*_#]', '', document_title_from_llm).strip()
        title_paragraph = Paragraph(clean_display_title, styles['DocTitle'])
        story.append(title_paragraph)
        # story.append(Spacer(1, 0.1 * inch)) # Optional small spacer after title

    lines = generated_content.split('\n')
    available_width_for_flowables = doc.width  # doc.width is page_width - left_margin - right_margin

    in_signature_section = False  # Flag to identify if we are in a signature section

    bold_regex = re.compile(r'\*\*(.*?)\*\*')
    # More specific italic regex to avoid conflict with list items starting with *
    italic_regex1 = re.compile(r'(?<!\*)\*(?!\s|\*)([^*]+?)(?<!\s|\*)\*(?!\*)')  # *italic* (not **)
    italic_regex2 = re.compile(r'_(.+?)_')  # _italic_

    for i, line_raw in enumerate(lines):
        line_trimmed = line_raw.strip()

        # Markdown to ReportLab inline tags
        # Apply bold first, then italics to avoid issues with nested like **_text_**
        processed_line = bold_regex.sub(r'<b>\1</b>', line_trimmed)
        processed_line = italic_regex1.sub(r'<i>\1</i>', processed_line)
        processed_line = italic_regex2.sub(r'<i>\1</i>', processed_line)  # Apply second italic pattern

        current_style_key = 'Normal'  # Default to Normal style key
        text_to_add = processed_line

        # Skip empty lines unless they are intentional (e.g. multiple blank lines for large space)
        if not line_trimmed:
            # story.append(Spacer(1, 0.1 * inch)) # Add small spacer for single empty lines if desired
            continue

        # --- Structure Detection ---
        if line_trimmed.startswith("# "):
            # This is the H1 from content. We've already added DocTitle.
            # So, the first # from Gemini will be H1Style.
            heading_text = bold_regex.sub(r'\1', line_trimmed[2:].strip())  # Remove markdown from heading text itself
            heading_text = italic_regex1.sub(r'\1', heading_text)
            heading_text = italic_regex2.sub(r'\1', heading_text)
            story.append(Paragraph(heading_text, styles['H1Style']))
            in_signature_section = False  # New section, not signatures unless specified

        elif line_trimmed.startswith("## "):
            heading_text = bold_regex.sub(r'\1', line_trimmed[3:].strip())
            heading_text = italic_regex1.sub(r'\1', heading_text)
            heading_text = italic_regex2.sub(r'\1', heading_text)
            story.append(Paragraph(heading_text, styles['H2Style']))
            # Check if this heading indicates a signature section
            if "signature" in heading_text.lower() or "approval" in heading_text.lower():
                in_signature_section = True
            else:
                in_signature_section = False

        elif line_trimmed.startswith("### "):
            heading_text = bold_regex.sub(r'\1', line_trimmed[4:].strip())
            heading_text = italic_regex1.sub(r'\1', heading_text)
            heading_text = italic_regex2.sub(r'\1', heading_text)
            story.append(Paragraph(heading_text, styles['H3Style']))
            in_signature_section = False  # New subsection, typically not signatures

        elif (line_trimmed.startswith("* ") or line_trimmed.startswith("- ")) and not line_trimmed.startswith(
                ("---", "***")):
            # Handle list item text, preserving its inline formatting
            list_item_text = processed_line[2:].strip()  # Get text after "* " or "- "
            story.append(Paragraph(list_item_text, styles['ListItemStyle'], bulletText='•'))

        elif line_trimmed in ["---", "***"]:  # Horizontal Rule
            story.append(HRFlowable(width=available_width_for_flowables))

        elif in_signature_section and (":" in processed_line and "___" in processed_line):
            # This is likely a signature line like "<b>Name:</b> __________"
            # The AI should provide the bolding for the label part.
            story.append(Paragraph(processed_line, styles['SignatureField']))

        elif text_to_add:  # Regular paragraph
            # Check if the entire paragraph is bold (e.g. "<b>Only bold text</b>")
            # This implies it might be an un-numbered sub-heading or emphasized block.
            is_fully_bold = text_to_add.startswith("<b>") and text_to_add.endswith("</b>") and \
                            text_to_add.count("<b>") == 1 and text_to_add.count("</b>") == 1

            if is_fully_bold:
                para = Paragraph(text_to_add, styles['BoldBodyText'])
            else:
                para = Paragraph(text_to_add, styles['Normal'])  # Use the modified 'Normal' style
            story.append(para)

    if not story:  # If after all processing, story is empty (e.g. only title was there)
        story.append(
            Paragraph("Content generation failed or produced no parseable output after the title.", styles['Normal']))

    try:
        doc.build(story)
        print(f"Successfully created PDF: {output_filepath}")
    except Exception as e:
        print(f"ERROR creating PDF: {output_filepath} - {e}")
        import traceback
        traceback.print_exc()


# --- Main Script Logic ---
def main():
    if not API_KEY:
        print("CRITICAL ERROR: GOOGLE_API_KEY environment variable not set.")
        print("Please set it before running the script. You can get a key from https://aistudio.google.com/app/apikey")
        return

    print(f"Initializing Gemini LLM ({MODEL_NAME})...")
    try:
        llm = Gemini(api_key=API_KEY, model_name=MODEL_NAME)
    except Exception as e:
        print(f"Error initializing Gemini LLM: {e}")
        return

    print_disclaimers()

    user_document_request = input("Describe the document you want to create (be specific for best results):\n> ")

    # --- Modified System Prompt for Gemini ---
    system_prompt_for_gemini = f"""
You are an expert AI document author, specializing in creating dense, well-structured, and professionally formatted documents suitable for formal use. Your output MUST be pure markdown, adhering strictly to the following guidelines.

DOCUMENT STRUCTURE & FORMATTING (MANDATORY MARKDOWN):
1.  **Main Title (Implicit from first H1):** Your response MUST begin directly with the main title of the document, formatted as `# Document Title`. This title should be descriptive and formal. Do NOT output any text before this H1 title.
2.  **Sections (H2):** Use `## Section Title` for all primary sections. Ensure logical flow.
3.  **Subsections (H3):** Use `### Subsection Title` for sub-topics within sections.
4.  **Emphasis:**
    *   Use `**bold text**` for strong emphasis on key terms, definitions, or critical points.
    *   Use `*italic text*` or `_italic text_` for mild emphasis (e.g., foreign words, titles of works, or subtle highlights).
5.  **Lists:**
    *   Use `* List item` or `- List item` for unordered bulleted lists. Ensure consistent formatting. Indent sub-lists if necessary (e.g. two spaces before the asterisk).
6.  **Paragraphs:** Write concise, information-dense paragraphs with clear topic sentences. Aim for maximum clarity and efficiency with minimal word count. Avoid redundancy and unnecessary adjectives or adverbs. Every sentence must contribute significant value.
7.  **Horizontal Rules:** If a strong visual separation is absolutely essential between major distinct content blocks (not typically between H2/H3 sections, but perhaps to delineate a completely different part of the document like an appendix from the main body, or before a signature block if it's not under a ## Signatures heading), use `---` on its own line. Use VERY sparingly.
8.  **Signature Section (Conditional - AI Decision):**
    *   **Decision:** Based on the user's document request, YOU (the AI) must decide if a signature section is contextually appropriate and necessary (e.g., for agreements, formal proposals, letters requiring sign-off, meeting minutes for approval, etc.).
    *   **Implementation:** If a signature section is deemed necessary, include a final section explicitly titled: `## Signatures` or `## Approval Section`.
    *   Under this specific heading, provide clear placeholders for signatures. For each signatory, use the format:
        `**Printed Name:** _________________________` (The underscores should be plentiful to create a visible line)
        `**Signature:** _________________________`
        `**Date:** _________________________`
        (If there are multiple signatories, repeat this block for each. You can optionally add a `---` separator between blocks for multiple signatories if it enhances clarity.)
    *   If a signature section is NOT appropriate for the document type, DO NOT include it.

CONTENT REQUIREMENTS:
1.  **Direct Output:** Start your response DIRECTLY with the H1 markdown title. NO conversational filler, introductions like "Okay, here is the document...", or self-referential statements ("As an AI...").
2.  **Density and Efficiency:** The document must be as compact and information-dense as possible while remaining perfectly readable and comprehensive. Your goal is to convey all necessary information in the fewest possible words and pages. Prioritize impactful information over lengthy explanations.
3.  **Professional Tone:** Maintain a highly formal, objective, and polished tone throughout the entire document.
4.  **Completeness:** Ensure the document is self-contained and thoroughly covers the requested topic from introduction to conclusion, as appropriate for the document type.

USER'S DOCUMENT REQUEST: "{user_document_request}"

Remember: Begin your response *immediately* with the H1 markdown title.
"""

    print("\nGenerating sophisticated document structure with Gemini...")
    print(f"Using model: {MODEL_NAME}. This may take a moment. Please wait.")

    generated_content = ""
    document_title_from_llm = "Untitled Document"
    try:
        response = llm.complete(system_prompt_for_gemini)
        generated_content = response.text.strip()

        if not generated_content:
            print("Gemini returned empty content. Please try a more specific prompt or check API status.")
            return

        # Extract H1 title for PDF metadata and filename
        first_line = generated_content.split('\n', 1)[0]
        title_match = re.match(r"#\s*(.*)", first_line)
        if title_match:
            document_title_from_llm = title_match.group(1).strip()
        else:  # Fallback if no H1 or very short content
            document_title_from_llm = user_document_request[:60].title() + "_Document"
            if not document_title_from_llm.strip() or document_title_from_llm == "_Document":
                document_title_from_llm = "Generated_Document_From_Request"


    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n--- Gemini's Raw Output (Preview First 1000 Chars) ---")
    print(generated_content[:1000] + ("..." if len(generated_content) > 1000 else ""))
    print("--- End of Preview ---")

    # Create filename from the extracted (and cleaned) document title
    filename_base = "Generated_Document"
    if document_title_from_llm and document_title_from_llm.strip() != "Untitled Document":
        # Clean title for filename (remove markdown, non-alphanum, replace spaces)
        sanitized_title = re.sub(r'[\*_#]', '', document_title_from_llm)  # Remove markdown chars
        sanitized_title = re.sub(r'[^\w\s-]', '', sanitized_title)  # Keep word chars, spaces, hyphens
        sanitized_title = re.sub(r'[-\s]+', '_', sanitized_title).strip('_')  # Replace space/hyphen with underscore
        filename_base = sanitized_title[:70]  # Keep filename manageable
        if not filename_base: filename_base = "Document"  # Fallback

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"{filename_base}_{timestamp}.pdf"
    pdf_filepath = os.path.join(OUTPUT_DIR, pdf_filename)

    print(f"\nFormatting and building PDF: {pdf_filepath}")
    print(f"Using document title: '{document_title_from_llm}'")
    create_enhanced_pdf(pdf_filepath, generated_content, document_title_from_llm)


def print_disclaimers():
    print("-" * 70)
    print("PDF Document Generator - Enhanced Professional Output (Beta)")
    print("-" * 70)
    print("\nIMPORTANT DISCLAIMERS:")
    print("1. AI-Generated Content: The content of the PDF is generated by an AI (Gemini).")
    print("   IT IS YOUR RESPONSIBILITY TO REVIEW, EDIT, AND VERIFY ALL INFORMATION")
    print("   for accuracy, completeness, and suitability before any use.")
    print("2. NO PROFESSIONAL ADVICE: This tool DOES NOT provide legal, financial, medical,")
    print("   or any other form of professional advice. Documents are for informational and")
    print("   drafting purposes ONLY.")
    print("3. CONSULT EXPERTS: For any document with legal, financial, or critical implications,")
    print("   ALWAYS consult with a qualified professional.")
    print("4. 'Sophisticated Formatting' refers to layout and style, not guaranteed content perfection.")
    print("-" * 70)


if __name__ == "__main__":
    main()