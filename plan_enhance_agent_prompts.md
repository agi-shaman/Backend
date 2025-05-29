# Plan: Enhance Agent System Prompt for PDF Verification and Subagent Delegation

**Objective:** Modify the `autonomous_system_prompt` in `test/agent_test.py` to instruct the agent on how to perform the requested tasks:
1. Enable the agent to process PDFs to check if they satisfy requirements (by verifying the output of the writing model).
2. Enable the agent to generate subagents for complex requests (defined as requests that can be broken down into sub-tasks).

**Proposed Changes to the System Prompt:**

1.  **Add a section on Task Analysis and Delegation:** This section will guide the agent to evaluate incoming user requests and decide whether to handle them directly or delegate parts to subagents.
2.  **Modify the "AUTONOMOUS PDF MODIFICATION" section:**
    *   Add a step after creating the new PDF to load and query the generated document.
    *   Instruct the agent to analyze the query results to verify the content and formatting.
    *   Update the final reporting step to include the outcome of the verification.

**Detailed Steps for Agent (as described in the new prompt):**

The agent will follow this general flow for each user request:

```mermaid
graph TD
    A[User Request] --> B{Analyze Request Complexity};
    B -- Can be broken into sub-tasks --> C[Identify Sub-tasks];
    C --> D{Suitable Sub-agent Exists?};
    D -- No --> E[Create New Sub-agent (with specific prompt)];
    D -- Yes --> F[Call Sub-agent with Sub-task];
    E --> F;
    F --> G[Get Sub-agent Result];
    G --> H{More Sub-tasks?};
    H -- Yes --> C;
    H -- No --> I[Synthesize Sub-agent Results];
    B -- Simple / PDF Modification --> J[Start PDF Modification Process];
    J --> K[Load Original PDF];
    K --> L[Extract Text];
    L --> M[Identify Placeholders];
    M --> N[Generate/Substitute Info];
    N --> O[Construct New Description];
    O --> P[Create New PDF];
    P --> Q[Load Generated PDF for Verification];
    Q --> R[Query Generated PDF (Verify Content/Format)];
    R --> S[Analyze Verification Result];
    S --> I[Synthesize Results];
    I --> T[Report Final Outcome to User];
```

**Specific Prompt Modifications:**

*   **New Section: Task Analysis and Delegation**
    *   Instruct the agent to first analyze if the user request can be broken down into distinct sub-tasks.
    *   If yes, instruct it to use `list_sub_agents` to check for existing relevant subagents.
    *   If no suitable subagent exists, instruct it to use `create_new_sub_agent` with a tailored system prompt for the specific sub-task.
    *   Instruct it to use `call_specific_sub_agent` to delegate the sub-task.
    *   Instruct it to synthesize the results from subagents before formulating the final response.
*   **Modified Section: TASK: AUTONOMOUS PDF MODIFICATION**
    *   Keep steps 1-7 largely the same, but emphasize noting the path of the newly created PDF in step 7.
    *   Insert a new Step 8: **Verify Generated PDF**. This step will detail using `load_pdf_document` on the new file, assigning a verification ID, using `query_pdf_document` with a specific query to check content and formatting against the original intent, and analyzing the result.
    *   Update the final Step (which becomes Step 9) **Report Outcome** to include a mention of the verification process and its outcome.

This plan leverages the agent's existing tools for PDF processing and subagent management by adding explicit instructions within the system prompt.