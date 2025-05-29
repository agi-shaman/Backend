# Plan: Integrate FileDecoder into Agent

## Objective

Integrate the file decoding capabilities from `lib/FileDecoder.py` into `lib/agent.py` to replace the PDF-specific reading logic and enable the agent to load and index various file types.

## Plan

1.  **Import `get_file_content`:** Add an import statement in `lib/agent.py` to import the `get_file_content` function from `lib.FileDecoder`.
2.  **Modify and Rename Loading Function:** Rename the existing `load_and_index_pdf` function in `lib/agent.py` to a more general name like `load_and_index_item`. This function will be modified to:
    *   Accept a generic `file_path_str` and `item_id`.
    *   Call `get_file_content(file_path_str)` to extract text from the file.
    *   Check the returned `error_msg`. If an error occurred during extraction, the function will return the error message.
    *   If content is successfully extracted, it will create a LlamaIndex `Document` object using this extracted text.
    *   The existing logic for creating nodes, building the vector index, persisting the index, and creating the query engine will be reused, operating on the `Document` object created from the extracted text.
3.  **Update Tool Definition:** Find the `FunctionTool` definition for `load_pdf_document` in `lib/agent.py` and update it.
    *   The tool name will be changed to reflect its new capability, perhaps `load_file_document`.
    *   The `fn` parameter will be updated to point to the renamed `load_and_index_item` function.
    *   The `description` will be updated to accurately list all the file types now supported by the `get_file_content` function (PDF, DOCX, XLSX, PPTX, TXT, HTML, and others treated as plain text) and explain that it extracts text content for indexing. The parameter names in the description will also be updated from `pdf_file_path` to `file_path` and `pdf_id` to `item_id`.
4.  **Verify Other Functions:** Quickly review `query_indexed_item` and `list_loaded_items` to ensure they are already generic enough to work with any indexed item, regardless of its original file type.

## Flow Diagram

```mermaid
graph TD
    A[User Request: Load file X.docx with ID 'report'] --> B[Agent calls load_file_document tool];
    B --> C[load_and_index_item(file_path='X.docx', item_id='report') called];
    C --> D[Call get_file_content('X.docx')];
    D --> E{FileDecoder extracts text?};
    E -- Yes --> F[Receive text content];
    F --> G[Create LlamaIndex Document from text];
    G --> H[Process Document into Nodes];
    H --> I[Build VectorStoreIndex];
    I --> J[Persist Index];
    J --> K[Create Query Engine];
    K --> L[Store Query Engine as 'report'];
    L --> M[Return Success Message];
    E -- No --> N[Receive Error Message];
    N --> O[Return Error Message];