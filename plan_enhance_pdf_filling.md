# Plan to Enhance PDF Agent's Filling Capability

This document outlines the plan to modify the `Main_Agent`'s prompt to enable it to fill in all missing data in a PDF, not just explicitly marked placeholders.

## Current Situation

The current `autonomous_system_prompt` in [`test/agent_test.py`](test/agent_test.py) instructs the agent to identify and substitute only explicit placeholder patterns like underscores (`___`) and brackets (`[]`), or keywords followed by underscores.

## Objective

Modify the agent's prompt to instruct it to identify and fill *any* sections or fields that appear incomplete or require information based on the document's context, including explicit placeholders and contextually empty fields.

## Plan Steps

1.  **Analyze Current Prompt:** Analyze the `autonomous_system_prompt` in [`test/agent_test.py`](test/agent_test.py) to understand its current instructions regarding placeholder identification and substitution. (Completed)
2.  **Propose Prompt Modification:** Modify the text within the `autonomous_system_prompt` to instruct the agent to identify *any* sections or fields that appear incomplete or require information (including explicit placeholders and contextually empty fields like "Contact Information" or "Printed Name:"). The agent will then be instructed to generate plausible, generic data for these identified areas based on the document's context and substitute the original text with this generated information, clearly marking the substitutions. (Completed - Proposed changes below)
3.  **Outline Implementation Steps:** The implementation will involve editing the [`test/agent_test.py`](test/agent_test.py) file to replace the existing `autonomous_system_prompt` string with the modified version.
4.  **Seek User Approval:** Present this plan and the specific proposed changes to the prompt text for user review and approval. (Completed - User approved)
5.  **Offer to Write Plan to File:** Offer to write the plan to a markdown file. (Completed - User accepted)
6.  **Request Mode Switch:** Request to switch to Code mode to implement the changes by editing the [`test/agent_test.py`](test/agent_test.py) file.

## Plan Visualization

```mermaid
graph TD
    A[User Request: Fix Prompt to Fill All Data] --> B{Analyze Current Prompt};
    B --> C[Read lib/agent.py];
    B --> D[Read test/agent_test.py];
    C --> E{Identify Prompt Location and Content};
    D --> E;
    E --> F[Propose Prompt Modification];
    F --> G[Outline Implementation Steps];
    G --> H[Present Plan to User];
    H --> I{User Approves Plan?};
    I -- Yes --> J[Offer to Write Plan to File];
    J --> K{User Accepts?};
    K -- Yes --> L[Write Plan to Markdown File];
    K -- No --> M[Proceed to Implementation];
    I -- No --> H; %% Loop back for adjustments
    L --> N[Request Mode Switch to Code];
    M --> N;
    N --> O[Implement Changes in Code Mode];
```

## Proposed Changes to the `autonomous_system_prompt` in [`test/agent_test.py`](test/agent_test.py)

Replace the current instructions for steps 4 and 5 (lines 32-41 in the file content I read) with the following:

```text
        "4.  **Identify Missing Information:** Analyze the extracted text content to identify any sections, fields, or placeholders that appear incomplete or require information. This includes explicit placeholders (like sequences of 3 or more underscores `___`, bracketed terms `[]` or `{{}}`) as well as sections that are clearly meant to contain specific details but are currently empty or generic (e.g., 'Contact Information', 'Printed Name:', 'Signature:', 'Date:').\n"
        "5.  **Generate and Substitute Generic Information:** For each identified section or field requiring information, generate plausible, generic data based on the document's context (e.g., trip details, contact info, approval fields). Replace the original text in these identified areas with the generated generic information. Clearly mark the substituted content, for example: `[AI AUTONOMOUSLY FILLED: Generated Contact Details]`, `[AI AUTONOMOUSLY FILLED: John Doe]`, `[AI AUTONOMOUSLY FILLED: Signed]`, `[AI AUTONOMOUSLY FILLED: 2025-08-20]`.\n"