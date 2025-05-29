# pdf_writer_utility.py

import os
import re
from datetime import datetime

# PDF Creation imports (ReportLab)
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib import colors
# from reportlab.pdfgen import canvas # Not directly used here, but SimpleDocTemplate uses it

# --- Font and Layout Configuration (from example) ---
FONT_BODY = "Times-Roman"
FONT_BODY_BOLD = "Times-Bold"
FONT_BODY_ITALIC = "Times-Italic"
# FONT_BODY_BOLD_ITALIC = "Times-BoldItalic" # Not used in current styles

FONT_HEADING = "Helvetica-Bold"
FONT_HEADING_LIGHT = "Helvetica" # Used for footer

PAGE_MARGIN_HORIZONTAL = 0.8 * inch
PAGE_MARGIN_VERTICAL = 0.8 * inch

COLOR_TEXT_BODY = colors.HexColor('#111111')
COLOR_TEXT_HEADING_MAJOR = colors.HexColor('#223A5E')
COLOR_TEXT_HEADING_MINOR = colors.HexColor('#2E4A7D')
COLOR_TEXT_HEADING_SUBTLE = colors.HexColor('#485F8A')
COLOR_ACCENT_LINE = colors.HexColor('#AAAAAA')
COLOR_FOOTER_TEXT = colors.HexColor('#666666')


class HRFlowable(Flowable):
    def __init__(self, width, thickness=0.5, color=COLOR_ACCENT_LINE, spaceBefore=0.1 * inch, spaceAfter=0.1 * inch):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.color = color
        self.spaceBefore = spaceBefore
        self.spaceAfter = spaceAfter
        self.height = self.thickness + self.spaceBefore + self.spaceAfter

    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.spaceAfter, self.width, self.spaceAfter)
        self.canv.restoreState()

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return (availWidth, self.height)


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
        canvas.setFont(FONT_HEADING_LIGHT, 8)
        canvas.setFillColor(COLOR_FOOTER_TEXT)

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
        self._draw_footer(canvas, doc)


def define_pdf_styles():
    styles = getSampleStyleSheet()

    styles['Normal'].fontName = FONT_BODY
    styles['Normal'].fontSize = 10
    styles['Normal'].leading = 12
    styles['Normal'].textColor = COLOR_TEXT_BODY
    styles['Normal'].alignment = TA_JUSTIFY
    styles['Normal'].spaceBefore = 0.05 * inch
    styles['Normal'].spaceAfter = 0.1 * inch
    styles['Normal'].splitLongParagraphs = 1

    styles.add(ParagraphStyle(name='DocTitle',
                              fontName=FONT_HEADING,
                              fontSize=22,
                              leading=28,
                              alignment=TA_CENTER,
                              textColor=COLOR_TEXT_HEADING_MAJOR,
                              spaceBefore=0,
                              spaceAfter=0.25 * inch))
    styles.add(ParagraphStyle(name='H1Style',
                              parent=styles['Normal'],
                              fontName=FONT_HEADING,
                              fontSize=16,
                              leading=19,
                              textColor=COLOR_TEXT_HEADING_MAJOR,
                              spaceBefore=0.2 * inch,
                              spaceAfter=0.1 * inch,
                              keepWithNext=1))
    styles.add(ParagraphStyle(name='H2Style',
                              parent=styles['Normal'],
                              fontName=FONT_HEADING,
                              fontSize=13,
                              leading=16,
                              textColor=COLOR_TEXT_HEADING_MINOR,
                              spaceBefore=0.18 * inch,
                              spaceAfter=0.09 * inch,
                              keepWithNext=1))
    styles.add(ParagraphStyle(name='H3Style',
                              parent=styles['Normal'],
                              fontName=FONT_HEADING,
                              fontSize=11,
                              leading=14,
                              textColor=COLOR_TEXT_HEADING_SUBTLE,
                              spaceBefore=0.15 * inch,
                              spaceAfter=0.08 * inch,
                              keepWithNext=1))
    styles.add(ParagraphStyle(name='ListItemStyle',
                              parent=styles['Normal'],
                              leftIndent=0.25 * inch,
                              bulletIndent=0.05 * inch,
                              spaceBefore=0.02 * inch,
                              spaceAfter=0.02 * inch,
                              bulletFontName=FONT_BODY,
                              bulletFontSize=10,
                              firstLineIndent=0))
    styles.add(ParagraphStyle(name='BoldBodyText',
                              parent=styles['Normal'],
                              fontName=FONT_BODY_BOLD))
    styles.add(ParagraphStyle(name='SignatureField',
                              parent=styles['Normal'],
                              fontSize=10,
                              leading=20, # More leading for handwritten signature
                              spaceBefore=0.15 * inch,
                              spaceAfter=0.05 * inch))
    return styles


def create_styled_pdf_from_markdown(output_filepath: str, markdown_content: str, document_title: str, verbose: bool = False):
    """
    Creates a styled PDF document from markdown content.
    Args:
        output_filepath: The full path where the PDF will be saved.
        markdown_content: The markdown string generated by the LLM.
        document_title: The main title of the document, used for PDF metadata and DocTitle style.
        verbose: If True, prints status messages.
    Returns:
        Tuple (bool, str): (success_status, message)
    """
    output_dir = os.path.dirname(output_filepath)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        if verbose: print(f"Created output directory: {output_dir}")

    doc = EnhancedPDFTemplate(output_filepath, doc_title=document_title)
    styles = define_pdf_styles()
    story = []

    # Add the main document title (centered, large)
    if document_title and document_title.strip().lower() != "untitled document":
        clean_display_title = re.sub(r'[\*_#]', '', document_title).strip() # Remove markdown from title for display
        title_paragraph = Paragraph(clean_display_title, styles['DocTitle'])
        story.append(title_paragraph)
        # story.append(Spacer(1, 0.1 * inch)) # Optional small spacer

    lines = markdown_content.split('\n')
    available_width_for_flowables = doc.width
    in_signature_section = False
    bold_regex = re.compile(r'\*\*(.*?)\*\*')
    italic_regex1 = re.compile(r'(?<!\*)\*(?!\s|\*)([^*]+?)(?<!\s|\*)\*(?!\*)') # *italic*
    italic_regex2 = re.compile(r'_(.+?)_') # _italic_

    for line_raw in lines:
        line_trimmed = line_raw.strip()

        # Apply bold first, then italics for inline formatting
        processed_line = bold_regex.sub(r'<b>\1</b>', line_trimmed)
        processed_line = italic_regex1.sub(r'<i>\1</i>', processed_line)
        processed_line = italic_regex2.sub(r'<i>\1</i>', processed_line) # Apply second italic pattern

        text_to_add = processed_line

        if not line_trimmed: # Skip empty lines
            # story.append(Spacer(1, 0.05 * inch)) # Optionally add small space for blank lines
            continue

        # --- Structure Detection (Markdown to ReportLab Styles) ---
        if line_trimmed.startswith("# "): # Markdown H1 (becomes styled H1Style in body)
            # Note: The overall document_title is already added as DocTitle.
            # This # line will be the first major heading in the document body.
            heading_text = bold_regex.sub(r'\1', line_trimmed[2:].strip()) # Remove markdown from heading text
            heading_text = italic_regex1.sub(r'\1', heading_text)
            heading_text = italic_regex2.sub(r'\1', heading_text)
            story.append(Paragraph(heading_text, styles['H1Style']))
            in_signature_section = False
        elif line_trimmed.startswith("## "): # Markdown H2
            heading_text = bold_regex.sub(r'\1', line_trimmed[3:].strip())
            heading_text = italic_regex1.sub(r'\1', heading_text)
            heading_text = italic_regex2.sub(r'\1', heading_text)
            story.append(Paragraph(heading_text, styles['H2Style']))
            # Check if this heading indicates a signature section
            if "signature" in heading_text.lower() or "approval" in heading_text.lower():
                in_signature_section = True
            else:
                in_signature_section = False
        elif line_trimmed.startswith("### "): # Markdown H3
            heading_text = bold_regex.sub(r'\1', line_trimmed[4:].strip())
            heading_text = italic_regex1.sub(r'\1', heading_text)
            heading_text = italic_regex2.sub(r'\1', heading_text)
            story.append(Paragraph(heading_text, styles['H3Style']))
            in_signature_section = False
        elif (line_trimmed.startswith("* ") or line_trimmed.startswith("- ")) and not line_trimmed.startswith(("---", "***")): # List item
            list_item_text = processed_line[2:].strip() # Text after "* " or "- ", with inline formatting
            story.append(Paragraph(list_item_text, styles['ListItemStyle'], bulletText='•'))
        elif line_trimmed in ["---", "***"]:  # Horizontal Rule
            story.append(HRFlowable(width=available_width_for_flowables))
        elif in_signature_section and (":" in processed_line and "___" in processed_line): # Signature line
            story.append(Paragraph(processed_line, styles['SignatureField'])) # Assumes AI bolds label
        elif text_to_add:  # Regular paragraph
            is_fully_bold = text_to_add.startswith("<b>") and text_to_add.endswith("</b>") and \
                            text_to_add.count("<b>") == 1 and text_to_add.count("</b>") == 1
            if is_fully_bold: # Paragraph is entirely bold (e.g. sub-heading)
                para = Paragraph(text_to_add, styles['BoldBodyText'])
            else:
                para = Paragraph(text_to_add, styles['Normal'])
            story.append(para)

    # Handle cases where no content was effectively generated for the story
    is_story_empty_except_title = True
    if len(story) > 0:
        if len(story) == 1 and isinstance(story[0], Paragraph) and story[0].style.name == 'DocTitle':
            pass # Only title was added
        else:
            for item in story: # Check if there's more than just the DocTitle
                if not (isinstance(item, Paragraph) and item.style.name == 'DocTitle'):
                    is_story_empty_except_title = False
                    break
    
    if len(story) == 0: # Absolutely no content, not even a title from input
         story.append(Paragraph("Content generation failed or produced no parseable output.", styles['Normal']))
    elif is_story_empty_except_title: # Only DocTitle was added, no body content from markdown
        story.append(Paragraph("No main content generated after the title.", styles['Normal']))

    try:
        doc.build(story)
        print(f"PDF successfully created at: {os.path.abspath(output_filepath)}")
        msg = f"Successfully created PDF: {output_filepath}"
        if verbose: print(msg)
        return True, msg, os.path.abspath(output_filepath)
    except Exception as e:
        err_msg = f"ERROR creating PDF '{output_filepath}': {e}"
        if verbose:
            print(err_msg)
            import traceback
            traceback.print_exc()
        return False, err_msg, output_filepath
