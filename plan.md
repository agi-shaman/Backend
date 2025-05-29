# Plan to Fix `agent_test.py` Errors

## Problem Description

When running the command `source .venv/bin/activate && cd .. && python -m Backend.test.agent_test`, the following errors and warnings occurred:

1.  Initially: `--- [Main_Agent] Error during run: no running event loop ---` and `RuntimeWarning: coroutine 'Context._step_worker' was never awaited`.
2.  After fixing the event loop issue: `--- [Main_Agent] Error during run: Result is not set. ---` and `IndexError: list index out of range` originating from `llama_index.llms.gemini.base.py`. Also, a `RuntimeWarning: coroutine 'Agent.run' was never awaited` in [`test/agent_test.py`](test/agent_test.py).
3.  After fixing the `Agent.run` not awaited and attempting to guide the agent with the full sub-agent name: `pydantic_core._pydantic_core.PydanticSerializationError: Unable to serialize unknown type: <class 'google.ai.generativelanguage_v1beta.types.content.FunctionCall'>`.

## Cause

1.  The initial error was due to calling an asynchronous method (`Agent.run()`) from a synchronous context without an active asyncio event loop.
2.  The `RuntimeWarning` in [`test/agent_test.py`](test/agent_test.py) was because the now-asynchronous `main_agent.run()` was not awaited.
3.  The `IndexError` and "Result is not set" error were likely due to the main agent using short sub-agent names, causing the `CallSubAgent` method to return an error message that the `llama_index` framework couldn't process as a valid tool output, leading to serialization issues.
4.  The `PydanticSerializationError` indicates that the `llama_index` memory component is trying to serialize a raw `FunctionCall` object, which it doesn't know how to handle. This is likely because the result of `self.worker.run()` (an `AgentChatResponse` object) was being stringified directly instead of extracting the final text response from its `.response` attribute before passing it to memory or returning it.

## Proposed Solutions

1.  **Fix Event Loop Issue (Completed):**
    *   Change the definition of the `run_agent` function in [`test/agent_test.py`](test/agent_test.py) to be asynchronous (`async def`).
    *   Call `run_agent()` using `asyncio.run()` in the `if __name__ == "__main__":` block.

2.  **Fix 'Agent.run' not awaited (Completed):**
    *   Add the `await` keyword before the call to `main_agent.run()` in the `run_agent` function in [`test/agent_test.py`](test/agent_test.py).

3.  **Guide Agent with Full Sub-agent Names (Completed):**
    *   Modify the `user_msg` string provided to the main agent in [`test/agent_test.py`](test/agent_test.py) to explicitly instruct the agent to use the full sub-agent names ('Main_Agent/AgentA' and 'Main_Agent/AgentB') when calling them using the `call_specific_sub_agent` tool.

4.  **Fix PydanticSerializationError:**
    *   Modify the `Agent.run` method in [`lib/agent.py`](lib/agent.py) to correctly extract the final text response from the `AgentChatResponse` object returned by `self.worker.run()` by accessing the `.response` attribute.

    **Current `Agent.run` (lines 36-47):**
    ```python
     36 |     async def run(self, user_msg: str) -> str:
     37 |         if (self.verbose):
     38 |             print(f"\n--- [{self.name}] Task received: {user_msg} ---")
     39 |         try:
     40 |             response = str(await self.worker.run(user_msg=user_msg, memory=self.memory))
     41 |
     42 |             if (self.verbose):
     43 |                 print(f"--- [{self.name}] Response: {response} ---")
     44 |             return response
     45 |         except Exception as e:
     46 |             print(f"--- [{self.name}] Error during run: {e} ---")
     47 |             return f"Error in {self.name}: {str(e)}"
    ```

    **Proposed `Agent.run` modification:**
    ```python
     36 |     async def run(self, user_msg: str) -> str:
     37 |         if (self.verbose):
     38 |             print(f"\n--- [{self.name}] Task received: {user_msg} ---")
     39 |         try:
     40 |             agent_response = await self.worker.run(user_msg=user_msg, memory=self.memory)
     41 |             response = str(agent_response.response) # Extract response from AgentChatResponse
     42 |
     43 |             if (self.verbose):
     44 |                 print(f"--- [{self.name}] Response: {response} ---")
     45 |             return response
     46 |         except Exception as e:
     47 |             print(f"--- [{self.name}] Error during run: {e} ---")
     48 |             return f"Error in {self.name}: {str(e)}"
    ```

## Visual Representation of the Plan

```mermaid
graph TD
    A[Run Command] --> B{Event Loop Error?};
    B -- Yes --> C[Modify test/agent_test.py for async];
    C --> D[Run Command];
    D --> E{Agent.run not awaited?};
    E -- Yes --> F[Add await in test/agent_test.py];
    F --> G[Run Command];
    G --> H{IndexError / Result not set?};
    H -- Yes --> I[Modify user_msg in test/agent_test.py];
    I --> J[Run Command];
    J --> K{PydanticSerializationError?};
    K -- Yes --> L[Extract response from AgentChatResponse in lib/agent.py];
    L --> M[Run Command];
    M --> N{Errors Resolved?};
    N -- Yes --> O[Task Complete];
    N -- No --> K;