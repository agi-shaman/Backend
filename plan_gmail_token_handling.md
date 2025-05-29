# Plan: Enhance Agent's Email Tool Descriptions

## Objective

Modify the agent's behavior in `lib/agent.py` so that when the Gmail service tools (`send_email` or `draft_email`) require a Google access token, the agent automatically uses the `get_text_input` tool to ask the user for it.

## Analysis

Based on the provided code (`lib/agent.py`), the email tools already signal the need for a token by returning the specific string "REQUIRED_INPUT: Google Access Token needed for email action.". The `get_text_input` tool is also available. The current setup relies on the agent's underlying LLM to interpret this signal and decide to use the `get_text_input` tool.

To ensure the agent's LLM reliably performs this action, we can make the instruction more explicit within the descriptions of the email tools themselves. This guides the LLM on the expected next step when the "REQUIRED_INPUT" signal is received.

## Proposed Plan

1.  **Goal:** Modify the descriptions of the `send_email` and `draft_email` tools in [`lib/agent.py`](lib/agent.py) to explicitly instruct the agent's LLM to use the `get_text_input` tool when a Google Access Token is required.
2.  **File to Modify:** [`lib/agent.py`](lib/agent.py)
3.  **Proposed Changes:**
    *   Locate the description string for the `send_email` tool (currently around lines 301-308).
    *   Append the following instruction to the end of the existing description:
        ```
        If the tool returns 'REQUIRED_INPUT: Google Access Token needed for email action.', you MUST then use the 'get_text_input' tool with the prompt 'Please provide your Google access token:' to obtain the token from the user before attempting the email action again.
        ```
    *   Locate the description string for the `draft_email` tool (currently around lines 322-329).
    *   Append the same instruction to the end of this description.

This modification clarifies the expected workflow for the agent's LLM when it encounters the specific return value indicating a missing token.

## Intended Workflow

Here's a simplified flow diagram illustrating the intended behavior:

```mermaid
graph TD
    A[Agent calls send_email/draft_email tool] --> B{Tool checks for token};
    B -- Token provided --> C[Tool performs email action];
    C --> D[Tool returns success/error];
    D --> E[Agent LLM processes result];
    B -- Token missing --> F[Tool returns "REQUIRED_INPUT: Google Access Token needed for email action."];
    F --> G[Agent LLM receives "REQUIRED_INPUT..." output];
    G --> H[Agent LLM calls get_text_input tool];
    H --> I[get_text_input prompts user];
    I --> J[User provides token];
    J --> K[get_text_input returns token];
    K --> L[Agent LLM receives token];
    L --> A;
```

This plan focuses on guiding the agent's LLM through prompt engineering within the tool descriptions, leveraging the existing mechanism where the tools signal the need for input.