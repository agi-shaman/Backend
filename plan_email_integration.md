# Plan: Integrate Email Tools into Agent

## Objective

Integrate the email sending and drafting capabilities from `rags/PDFPrototype/EmailAgent.py` into the `Agent` class in `lib/agent.py`, excluding logging and GUI components.

## Analysis

Examined the provided content of `rags/PDFPrototype/EmailAgent.py` and `lib/agent.py`. Identified core email functionality in `EmailAgent.py` related to Gmail API interaction and the structure in `lib/agent.py` for adding new tools and methods.

## Proposed Plan

1.  **Analyze Source Code:** Review the provided content of `rags/PDFPrototype/EmailAgent.py` to understand its structure and identify the functions responsible for email operations. Review `lib/agent.py` to see how new tools are added and how the `Agent` class is structured. (Completed based on user provided content)
2.  **Identify and Extract Core Logic:** The key components to extract are the functions that interact with the Gmail API: `get_gmail_service` (for initializing the API client) and `create_gmail_message_body` (for formatting the email payload). The logic within the `/send_email` and `/draft_email` Flask routes will be adapted into new methods within the `Agent` class. Explicitly exclude any code related to Flask, Firebase authentication, logging, or GUI rendering.
3.  **Add Necessary Imports:** Add the required import statements at the top of `lib/agent.py` for modules like `json`, `base64`, `email.message.EmailMessage`, `google.oauth2.credentials.Credentials`, `googleapiclient.discovery.build`, and `googleapiclient.errors.HttpError`.
4.  **Implement Internal Helper Methods:**
    *   Add a private method `_get_gmail_service(self, user_google_access_token: str)` to the `Agent` class. This method will take the user's Google access token as input and return an initialized Gmail API service object. Error handling from the original function will be retained but adapted to fit the agent's context (returning error messages as strings).
    *   Add a private method `_create_gmail_message_body(self, to_email: str, subject: str, message_text: str) -> dict` to the `Agent` class. This method will take the recipient email, subject, and body text, and return the base64url encoded message dictionary required by the Gmail API.
5.  **Implement Internal Email Action Methods:**
    *   Add a private method `_send_email_internal(self, recipient: str, subject: str, body: str, user_google_access_token: str) -> str` to the `Agent` class. This method will orchestrate the sending process: it will call `_get_gmail_service` to get the API client, call `_create_gmail_message_body` to format the message, and then use the Gmail API's `users().messages().send().execute()` method to send the email. It will return a success message including the message ID or an error message if the API call fails.
    *   Add a private method `_draft_email_internal(self, recipient: str, subject: str, body: str, user_google_access_token: str) -> str` to the `Agent` class. Similar to the send method, this will use the helper methods but call the Gmail API's `users().drafts().create().execute()` method to create a draft. It will return a success message including the draft ID or an error message.
6.  **Define Agent Tools:**
    *   Inside the `_add_tools` method, create a `FunctionTool` for sending emails. Its name will be `send_email`. Its description will clearly state its purpose and list the required parameters: `recipient` (string), `subject` (string), `body` (string), and `user_google_access_token` (string). The function wrapped by this tool will be `_send_email_internal`.
    *   Create another `FunctionTool` for drafting emails. Its name will be `draft_email`. Its description will explain its function and list the required parameters: `recipient` (string), `subject` (string), `body` (string), and `user_google_access_token` (string). The function wrapped will be `_draft_email_internal`.
7.  **Agent Prompting and Token Handling:** The agent's main system prompt will need to be updated (conceptually) to inform it about the new `send_email` and `draft_email` tools. The agent must be instructed that these tools require a `user_google_access_token` and that it should ask the user for this token when an email-related task is requested, if it doesn't already have it. The user will need to provide this token as a parameter when instructing the agent to use the email tools.

## Plan Diagram

```mermaid
graph TD
    A[User Task: Integrate Email Tools] --> B{Analyze EmailAgent.py};
    A --> C{Analyze Agent.py};
    B --> D[Identify Core Email Logic];
    C --> E[Understand Agent Structure];
    D --> F[Extract Relevant Code];
    E --> G[Plan Integration Points];
    F & G --> H[Add Imports to Agent.py];
    H --> I[Implement Internal Helper Methods];
    I --> J[Implement Internal Action Methods];
    J --> K[Define FunctionTools in _add_tools];
    K --> L[Update Agent Prompting Strategy];
    L --> M[Present Plan to User];
    M --> N{User Approval?};
    N -- Yes --> O[Offer to Write Plan to File];
    O --> P{Write to File?};
    P -- Yes --> Q[Write Plan.md];
    P -- No --> R[Proceed to Implementation];
    N -- No --> M; %% Loop back for revisions
    Q --> S[Switch to Code Mode];
    R --> S;
    S --> T[Implement Code Changes];