# Plan: Implement Interactive Document Creation

**Objective:** Modify the agent's document creation process to allow the main agent to identify required user input fields based on the document description, prompt the user for this information using the `get_text_input` tool, and then pass the collected data to the writing LLM for final document generation without placeholders. Update the test file accordingly.

**Current Situation:**
The current process involves the writing LLM generating markdown which may contain placeholder patterns like "ask user for [Field Name]". The agent then needs to identify and replace these. The user wants to eliminate this placeholder step and have the main agent gather information upfront.

**Revised Approach:**
The main agent will analyze the document description, infer necessary user input fields, collect the data using `get_text_input`, and then instruct the writing LLM to generate the final document with the data already included.

**Detailed Plan:**

1.  **Analyze `lib/agent.py`:** Read the `_create_document_from_description_internal` function in [`lib/agent.py`](lib/agent.py) to understand its current structure.
2.  **Modify `_create_document_from_description_internal`:**
    *   The function will receive the initial `document_description`.
    *   The main agent's LLM (the one executing this function) will analyze the `document_description` to identify specific pieces of information that are typically required for such a document but are not present in the description (e.g., for an "Approval Request" document, it might infer the need for a signatory's name, signature, and date). This inference step is based on the main agent's general knowledge and the context of the request.
    *   For each piece of information the main agent's LLM determines is needed, it will use the `get_text_input` tool with an appropriate prompt (like the ones previously agreed upon: "Please provide the Printed Name of Signatory:", "Please provide the Signature:", "Please provide the Date of Signature:").
    *   Collect and store all user inputs.
    *   Construct a *final* prompt for the writing LLM. This prompt will include the original `document_description` and the collected user data, explicitly instructing the writing LLM to generate the document with this data included and *without* adding any placeholders or requests for user input. I will need to create a new system prompt or modify the existing one dynamically for this single call to the writing LLM.
    *   Call the writing LLM *once* with this final, data-rich prompt.
    *   Process the markdown received from this single LLM call. This markdown should contain the user's actual input and no placeholders.
    *   Update the logic for filename generation and PDF creation to use the content from this single LLM call.
3.  **Update `test/agent_test.py`:**
    *   Modify the test case to mock the `get_text_input` tool to provide simulated user input for the prompts that the main agent is expected to generate based on the document description.
    *   Mock the *single* writing LLM call. The mock should be configured to receive the final prompt (containing the original description and mocked user data) and return markdown with the mocked user input inserted.
    *   Update assertions to check that the final generated document contains the mocked user input.
4.  **Implement Changes:** Use `apply_diff` to modify [`lib/agent.py`](lib/agent.py) and [`test/agent_test.py`](test/agent_test.py).
5.  **Test:** Run the updated [`test/agent_test.py`](test/agent_test.py).
6.  **Attempt Completion:** Report the outcome.

**Process Flow Diagram:**

```mermaid
graph TD
    A[Start Document Creation<br>with Description] --> B{Main Agent LLM Analyzes<br>Description to Infer Required Fields};
    B -- Infers Field Needed --> C{Map Field Name to<br>User Prompt};
    C --> D[Call get_text_input Tool<br>with Prompt];
    D --> E[Receive User Input];
    E --> F{Store Field Name<br>and User Input};
    F --> B;
    B -- No More Fields Inferred --> G{Construct Final Prompt<br>with Description + User Data};
    G --> H{Call Writing LLM<br>with Final Prompt};
    H --> I[Receive Final Markdown<br>(Contains User Data)];
    I --> J[Use Final Markdown<br>to Create PDF];
    J --> K[Save PDF File];
    K --> L[Return Success Message<br>with File Path];
    L --> M[End Document Creation];
    D -- Tool Call Failed --> N[Handle Error];
    N --> M;
    H -- LLM Call Failed --> O[Handle Error];
    O --> M;