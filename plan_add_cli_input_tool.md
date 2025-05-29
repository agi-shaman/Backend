# Plan: Add CLI Text Input Tool to Agent

## Goal

Add a new tool to the `Agent` class in [`lib/agent.py`](lib/agent.py) that, when called, prompts the user via the CLI for generic text input and returns the initial input combined with the collected response in a wrapped string format.

## Revised Plan

1.  **Modify [`lib/agent.py`](lib/agent.py):** We will add a new method to the `Agent` class.
2.  **Define the Tool Method:** Create a new private method within the `Agent` class (e.g., `_get_cli_text_input_tool_func`). This method will:
    *   Accept the initial user input (or a relevant part of it) as a parameter when the tool is called by the agent.
    *   Use Python's built-in `input()` function (or a similar mechanism suitable for CLI interaction) to display a generic prompt message to the user (e.g., "Please provide additional information: ") and wait for their text input.
    *   Combine the initial input received as a parameter with the text input collected from the user.
    *   Format the combined information into the string "The user responded ...".
    *   Return this formatted string.
3.  **Register the Tool:** In the `_add_tools` method of the `Agent` class, create a new `FunctionTool` using `FunctionTool.from_defaults`, linking it to the `_get_cli_text_input_tool_func` method. Give the tool a descriptive name (e.g., `get_cli_text_input`) and a clear description explaining its purpose and how it interacts with the user via the CLI.
4.  **Agent Usage:** The agent's LLM, when processing a user's request, can then decide to call this new `get_cli_text_input` tool if it determines that additional information is needed from the user to complete the task.

## Agent Workflow with New Tool

```mermaid
graph TD
    A[User Provides Initial Input] --> B[Agent Processes Input];
    B --> C{Agent Needs More Info?};
    C -- Yes --> D[Agent Calls get_cli_text_input Tool];
    D --> E{Tool Prompts User via CLI};
    E --> F{User Provides Text Input};
    F --> G{Tool Formats Output};
    G --> H[Tool Returns Formatted Output to Agent];
    H --> I[Agent Continues Processing];
    C -- No --> I;
    I --> J[Agent Provides Final Response];