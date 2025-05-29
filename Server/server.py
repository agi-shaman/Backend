from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import asyncio  # For asyncio.create_task if you want fire-and-forget

# Import your agent (assuming agent.py is in the same directory or Python path)
from ..lib import agent   # Make sure your Agent class is importable


# --- Pydantic Models for Request and Response ---
class TaskRequest(BaseModel):
    prompt: str


class AgentResponse(BaseModel):
    status: str
    message: str  # A general message (e.g., "Task submitted")
    agent_output: str | None = None  # The actual output from the agent


# --- FastAPI App Initialization ---
app = FastAPI(
    title="Agent Processing API",
    description="An API to submit tasks to an AI agent.",
    version="1.0.0"
)

# --- Initialize Agent ---
# This agent instance will be shared across requests.
# Ensure your Agent class is thread-safe if it maintains state that's modified by `run`.
# Given `run` is async, state management should be handled carefully.
# If initialization is heavy, consider FastAPI's lifespan events.
print("Initializing agent...")
my_global_agent = agent.Agent(verbose=True)  # Set verbose to True for server-side logging
print("Agent initialized.")


# --- Helper function to run the agent task ---
# This is the function that will actually run in the "new thread"
# (more accurately, as a concurrent asyncio task managed by FastAPI's event loop)
async def run_agent_task_async(task_prompt: str) -> str:
    """
    Executes the agent's run method.
    This is an async function, so FastAPI will handle its execution
    concurrently without blocking the main server thread for other requests.
    """
    print(f"\n--- [Server] Executing task in background: {task_prompt} ---")
    try:
        response = await my_global_agent.run(task_prompt)
        print(f"\n--- [Server] Agent finished. Response: {response} ---")
        return response
    except Exception as e:
        print(f"\n--- [Server] Error during agent execution: {e} ---")
        # Depending on how you want to handle errors, you might re-raise,
        # or return an error message string.
        return f"Error processing task: {str(e)}"


# --- API Endpoint ---
@app.post("/process_task", response_model=AgentResponse)
async def process_task_endpoint(task_request: TaskRequest):
    """
    Receives a task prompt and processes it using the agent.
    The agent's `run` method is awaited, allowing other requests to be handled
    concurrently by FastAPI's event loop.
    """
    print(f"\n--- [Server] Received request with prompt: {task_request.prompt} ---")

    # Directly await the agent task. FastAPI handles concurrency.
    # This means while this specific request is awaiting `my_global_agent.run()`,
    # FastAPI can still accept and start processing other incoming requests.
    try:
        agent_output_str = await run_agent_task_async(task_request.prompt)
        return AgentResponse(
            status="completed",
            message="Agent processing finished.",
            agent_output=agent_output_str
        )
    except Exception as e:
        # This exception handling is a fallback, specific errors should be caught in run_agent_task_async
        print(f"Critical error in endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process task: {str(e)}")


# --- Optional: Fire-and-forget endpoint ---
# If you don't want to wait for the agent's response and just want to kick off the task.
# The client will get an immediate response that the task was submitted.
# The actual processing happens in the background.
@app.post("/process_task_fire_and_forget", response_model=AgentResponse)
async def process_task_fire_and_forget_endpoint(
        task_request: TaskRequest,
        background_tasks: BackgroundTasks
):
    """
    Receives a task prompt and schedules it for background processing.
    Returns immediately to the client.
    """
    print(f"\n--- [Server] Received fire-and-forget request: {task_request.prompt} ---")

    # Using FastAPI's BackgroundTasks to run the agent task.
    # This will run after the response has been sent to the client.
    # Note: run_agent_task_async is async, BackgroundTasks can handle it.
    # If run_agent_task_async was synchronous, BackgroundTasks would run it in a thread pool.
    background_tasks.add_task(run_agent_task_async, task_request.prompt)

    # Alternatively, using asyncio.create_task for true concurrent execution
    # within the event loop without BackgroundTasks (more advanced):
    # asyncio.create_task(run_agent_task_async(task_request.prompt))
    # If you use create_task, be mindful of error handling and resource management
    # for these "unawaited" tasks. BackgroundTasks is often simpler for this.

    return AgentResponse(
        status="submitted",
        message="Task submitted for background processing. Check server logs for completion.",
        agent_output=None  # No output as it's fire-and-forget
    )


# --- Main Block to Run Uvicorn ---
if __name__ == "__main__":
    # Make sure to run this script with: uvicorn server:app --reload
    # Or programmatically:
    print("Starting Uvicorn server on http://127.0.0.1:8000")
    print("Access OpenAPI docs at http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)