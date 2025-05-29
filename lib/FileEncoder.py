import pathlib
import os
from docx import Document as DocxDocument
import json
from bs4 import BeautifulSoup # Used for basic HTML structure if needed, though direct string write is simpler
import csv # For potential future CSV writing, include now

def write_text_to_txt(file_path: str, content: str) -> str:
    """Writes plain text content to a .txt file."""
    try:
        path = pathlib.Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return f"Successfully wrote text content to '{path}'."
    except Exception as e:
        return f"Error writing text to '{file_path}': {e}"

def write_text_to_docx(file_path: str, content: str) -> str:
    """Writes text content to a basic .docx file."""
    try:
        path = pathlib.Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        document = DocxDocument()
        # Add content line by line as paragraphs
        for line in content.splitlines():
            document.add_paragraph(line)
        document.save(path)
        return f"Successfully wrote DOCX content to '{path}'."
    except Exception as e:
        return f"Error writing DOCX to '{file_path}': {e}"

def write_text_to_html(file_path: str, content: str) -> str:
    """Writes text content to a basic .html file."""
    try:
        path = pathlib.Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Simple HTML structure
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<title>Document</title>
</head>
<body>
<pre>{content}</pre>
</body>
</html>"""
        path.write_text(html_content, encoding='utf-8')
        return f"Successfully wrote HTML content to '{path}'."
    except Exception as e:
        return f"Error writing HTML to '{file_path}': {e}"

def write_text_to_json(file_path: str, content: str) -> str:
    """Attempts to parse content as JSON and writes it to a .json file."""
    try:
        path = pathlib.Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Attempt to parse content as JSON
        json_data = json.loads(content)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=4)
        return f"Successfully wrote JSON content to '{path}'."
    except json.JSONDecodeError:
        return f"Error writing JSON to '{file_path}': Content is not valid JSON."
    except Exception as e:
        return f"Error writing JSON to '{file_path}': {e}"

def write_file_content(file_path_str: str, content: str) -> str:
    """
    Writes content to a file, determining the format based on the file extension.
    Returns a success message or an error message.
    """
    file_path = pathlib.Path(file_path_str)
    ext = file_path.suffix.lower()

    if ext == ".txt":
        return write_text_to_txt(file_path_str, content)
    elif ext == ".docx":
        return write_text_to_docx(file_path_str, content)
    elif ext in [".html", ".htm"]:
        return write_text_to_html(file_path_str, content)
    elif ext == ".json":
        return write_text_to_json(file_path_str, content)
    # Add more formats here as needed
    else:
        return f"Error: Unsupported file extension for writing: '{ext}'. Supported formats: .txt, .docx, .html, .json."