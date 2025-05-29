# server.py

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field  # Keep Pydantic models top-level
import uvicorn
import asyncio
import csv
import os
from datetime import datetime, timezone, timedelta
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Callable, Awaitable  # For type hints


# --- Pydantic Models (remain top-level) ---
class TaskRequest(BaseModel):
    prompt: str


class ScheduleTaskRequest(BaseModel):
    prompt: str
    scheduled_time: datetime = Field(..., description="Scheduled execution time in ISO 8601 format.")


class AgentResponse(BaseModel):
    status: str
    message: str
    agent_output: str | None = None
    task_id: str | None = None


# --- Agent Import ---
# Attempt to import the real Agent, provide a dummy if it fails.
try:
    # Assuming your Agent class is named Agent in ..lib.agent
    from ..lib.agent import Agent as ActualAgent

    print("Successfully imported Agent from ..lib.agent")
except ImportError:
    print("Warning: Could not import Agent from ..lib.agent. Using dummy Agent.")


    class ActualAgent:  # Dummy Agent
        def __init__(self, verbose: bool = False,
                     tool_registry: Dict[str, Callable[..., Awaitable[Any]]] | None = None):
            self.verbose = verbose
            self.tool_registry = tool_registry if tool_registry else {}
            if self.verbose:
                print(f"[Dummy Agent] Initialized. Tools: {list(self.tool_registry.keys())}")

        async def run(self, task_prompt: str) -> str:
            if self.verbose:
                print(f"[Dummy Agent] Received task: {task_prompt}")

            if "question for user" in task_prompt.lower() and "ask_user_tool" in self.tool_registry:
                question_to_ask = "What is your favorite color for this task?"  # Example
                if self.verbose:
                    print(f"[Dummy Agent] Using 'ask_user_tool' to ask: {question_to_ask}")
                try:
                    user_response = await self.tool_registry["ask_user_tool"](question=question_to_ask)
                    return f"Dummy agent processed: '{task_prompt}'. User responded: '{user_response}'"
                except Exception as e:
                    print(f"[Dummy Agent] Error calling 'ask_user_tool': {e}")
                    return f"Dummy agent tried to ask user but failed: {e}"

            await asyncio.sleep(1)  # Simulate work
            return f"Dummy agent processed: '{task_prompt}'"

AgentType = ActualAgent  # Use this type hint


class ApiServer:
    # --- Default Configurations ---
    DEFAULT_CSV_FILE_PATH = "scheduled_tasks.csv"
    CSV_HEADERS = ["id", "prompt", "scheduled_time_iso", "status", "created_at_iso", "result", "error_message"]
    DEFAULT_SCHEDULER_INTERVAL_SECONDS = 30

    def __init__(self,
                 agent_class: type[AgentType] = ActualAgent,
                 agent_verbose: bool = True,
                 # Pass any specific args your real Agent might need
                 # agent_constructor_args: dict | None = None,
                 csv_file_path: str = DEFAULT_CSV_FILE_PATH,
                 scheduler_interval: int = DEFAULT_SCHEDULER_INTERVAL_SECONDS
                 ):
        self.csv_file_path = csv_file_path
        self.scheduler_interval = scheduler_interval
        self.scheduler_task_handle: asyncio.Task | None = None

        # Tool registry for the agent: maps tool names to server methods
        self.tool_registry: Dict[str, Callable[..., Awaitable[Any]]] = {
            "ask_user_tool": self._ask_user_via_server
            # Add other server-side functions the agent can call here
            # e.g., "get_server_time": self._get_current_server_time
        }

        print("Initializing agent...")
        # agent_args = agent_constructor_args if agent_constructor_args else {}
        self.agent: AgentType = agent_class(
            self,
            verbose=agent_verbose # Pass server-side tools to the agent
            # **agent_args # Spread other constructor args if any
        )
        print("Agent initialized.")

        self.app = FastAPI(
            title="Agent Processing API with Scheduling (Class-based)",
            description="An API to submit tasks to an AI agent, including scheduling.",
            version="1.3.0",
            lifespan=self._lifespan_manager  # Register lifespan context manager
        )
        self._register_routes()

    async def _ask_user_via_server(self, question: str) -> str:
        """
        This is a server-side function that the Agent can call via its tool_registry.
        It's a placeholder for interacting with a user, perhaps via Firebase or another channel.
        """
        # TODO: Implement actual user interaction logic (e.g., via Firebase, websocket, etc.)
        print(f"[Server Tool - _ask_user_via_server] Agent asked: '{question}'")
        # For now, simulate getting input or returning a placeholder
        await asyncio.sleep(0.1)  # Simulate a tiny delay for I/O
        return "User responded: 'I have no Idea, generate some temp data'. (Placeholder from server)"

    # --- CSV Helper Methods ---
    def _initialize_csv(self):
        if not os.path.exists(self.csv_file_path):
            with open(self.csv_file_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.CSV_HEADERS)
            print(f"Initialized {self.csv_file_path}")

    def _add_task_to_csv(self, task_id: str, prompt: str, scheduled_time: datetime):
        created_at = datetime.now(timezone.utc)
        if scheduled_time.tzinfo is None:
            scheduled_time_utc = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time_utc = scheduled_time.astimezone(timezone.utc)

        with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                task_id, prompt, scheduled_time_utc.isoformat(), "PENDING", created_at.isoformat(), "", ""
            ])
        print(f"Task {task_id} added to CSV for {scheduled_time_utc.isoformat()}")

    def _read_all_tasks_from_csv(self) -> list[dict]:
        if not os.path.exists(self.csv_file_path):
            return []
        tasks = []
        with open(self.csv_file_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tasks.append(row)
        return tasks

    def _write_all_tasks_to_csv(self, tasks_data: list[dict]):
        with open(self.csv_file_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
            writer.writeheader()
            writer.writerows(tasks_data)

    def _get_and_mark_due_tasks_as_running(self) -> list[dict]:
        all_tasks = self._read_all_tasks_from_csv()
        due_tasks_to_run = []
        now_utc = datetime.now(timezone.utc)
        modified = False

        for task in all_tasks:
            if task['status'] == "PENDING":
                try:
                    scheduled_time_utc = datetime.fromisoformat(task['scheduled_time_iso'])
                    if scheduled_time_utc.tzinfo is None:
                        scheduled_time_utc = scheduled_time_utc.replace(tzinfo=timezone.utc)
                    if scheduled_time_utc <= now_utc:
                        task['status'] = "RUNNING"
                        due_tasks_to_run.append(dict(task))  # Add a copy
                        modified = True
                        print(f"Scheduler: Marking task {task['id']} as RUNNING.")
                except ValueError as e:
                    print(f"Error parsing scheduled_time for task {task['id']}: {e}. Marking as FAILED.")
                    task['status'] = "FAILED"
                    task['error_message'] = f"Invalid scheduled_time format: {e}"
                    modified = True
        if modified:
            self._write_all_tasks_to_csv(all_tasks)
        return due_tasks_to_run

    def _update_task_final_status_in_csv(self, task_id: str, final_status: str, result: str = "",
                                         error_message: str = ""):
        all_tasks = self._read_all_tasks_from_csv()
        modified = False
        for task in all_tasks:
            if task['id'] == task_id:
                task['status'] = final_status
                task['result'] = result
                task['error_message'] = error_message
                modified = True
                print(f"Scheduler: Updated task {task_id} to {final_status} in CSV.")
                break
        if modified:
            self._write_all_tasks_to_csv(all_tasks)

    # --- Agent Task Execution Method ---
    async def _run_agent_task_async(self, task_prompt: str, task_id: str | None = None) -> tuple[str, str | None]:
        prefix = f"[Agent Task ID: {task_id}]" if task_id else "[Agent Task]"
        print(f"\n--- {prefix} Executing: {task_prompt} ---")
        try:
            response = await self.agent.run(task_prompt)  # Use self.agent
            print(f"\n--- {prefix} Finished. Response: {response} ---")
            return response, None
        except Exception as e:
            error_msg = f"Error processing task: {str(e)}"
            print(f"\n--- {prefix} Error during execution: {e} ---")
            return "", error_msg

    # --- Scheduler Logic Method ---
    async def _scheduler_loop(self):
        print(f"Scheduler loop started. Will check for tasks every {self.scheduler_interval} seconds.")
        while True:
            try:
                print(f"Scheduler: Woke up at {datetime.now(timezone.utc).isoformat()}. Checking for due tasks...")
                due_tasks = self._get_and_mark_due_tasks_as_running()

                if not due_tasks:
                    print("Scheduler: No due tasks found this cycle.")

                for task_data in due_tasks:
                    task_id = task_data['id']
                    prompt = task_data['prompt']
                    print(f"Scheduler: Processing due task ID {task_id}: \"{prompt[:50]}...\"")

                    async def execute_and_update_scheduled_task(current_task_id, current_prompt):
                        agent_response_str, error_str = await self._run_agent_task_async(current_prompt,
                                                                                         current_task_id)
                        if error_str:
                            self._update_task_final_status_in_csv(current_task_id, "FAILED", error_message=error_str)
                        else:
                            self._update_task_final_status_in_csv(current_task_id, "COMPLETED",
                                                                  result=agent_response_str)

                    asyncio.create_task(execute_and_update_scheduled_task(task_id, prompt))
            except Exception as e:
                print(f"SCHEDULER LOOP ERROR: {e}")  # Log error and continue loop
            await asyncio.sleep(self.scheduler_interval)

    # --- FastAPI Lifespan Method ---
    @asynccontextmanager
    async def _lifespan_manager(self, app: FastAPI):  # app argument is passed by FastAPI
        print("Application startup: Initializing CSV and starting scheduler...")
        self._initialize_csv()
        self.scheduler_task_handle = asyncio.create_task(self._scheduler_loop())
        print("Scheduler started.")
        yield  # Application runs here
        print("Application shutdown: Stopping scheduler...")
        if self.scheduler_task_handle:
            self.scheduler_task_handle.cancel()
            try:
                await self.scheduler_task_handle
            except asyncio.CancelledError:
                print("Scheduler task cancelled successfully.")
            except Exception as e:  # Catch any other exceptions during cancellation
                print(f"Error during scheduler task cancellation: {e}")
        print("Scheduler stopped.")


    def wait_for_input(self, prompt: str) -> str:
        print("Waiting for input...")
        return "I have no idea. Generate some default values"
    # --- API Endpoints Registration ---
    def _register_routes(self):
        @self.app.post("/process_task", response_model=AgentResponse)
        async def process_task_endpoint(task_request: TaskRequest):
            print(f"\n--- [Server] Received request for immediate processing: {task_request.prompt} ---")
            agent_output_str, error_str = await self._run_agent_task_async(task_request.prompt)
            if error_str:
                raise HTTPException(status_code=500, detail=error_str)
            return AgentResponse(
                status="completed",
                message="Agent processing finished.",
                agent_output=agent_output_str
            )

        @self.app.post("/process_task_fire_and_forget", response_model=AgentResponse)
        async def process_task_fire_and_forget_endpoint(task_request: TaskRequest, background_tasks: BackgroundTasks):
            task_id = str(uuid.uuid4())
            print(f"\n--- [Server] Received fire-and-forget request (ID: {task_id}): {task_request.prompt} ---")

            async def background_wrapper(prompt, t_id):
                agent_response, error = await self._run_agent_task_async(prompt, t_id)
                if error:
                    print(f"Background task {t_id} failed: {error}")
                else:
                    print(f"Background task {t_id} completed. Result: {agent_response[:50]}...")

            background_tasks.add_task(background_wrapper, task_request.prompt, task_id)
            return AgentResponse(
                status="submitted",
                message="Task submitted for background processing. Check server logs for completion.",
                task_id=task_id
            )

        @self.app.post("/schedule_task", response_model=AgentResponse)
        async def schedule_task_endpoint(schedule_request: ScheduleTaskRequest):
            prompt = schedule_request.prompt
            scheduled_time = schedule_request.scheduled_time
            if scheduled_time.tzinfo is None:
                scheduled_time_utc = scheduled_time.replace(tzinfo=timezone.utc)
            else:
                scheduled_time_utc = scheduled_time.astimezone(timezone.utc)

            if scheduled_time_utc <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Scheduled time must be in the future.")

            task_id = str(uuid.uuid4())
            try:
                self._add_task_to_csv(task_id, prompt, scheduled_time_utc)
                return AgentResponse(
                    status="scheduled",
                    message=f"Task scheduled successfully for {scheduled_time_utc.isoformat()}.",
                    task_id=task_id
                )
            except Exception as e:
                print(f"Error scheduling task: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to schedule task: {str(e)}")

        @self.app.get("/view_tasks", response_model=list[dict])
        async def view_tasks_endpoint():  # No 'self' if it's a local function inside _register_routes
            # but it needs self to access _read_all_tasks_from_csv
            # So, it should be defined to capture `self` from the outer scope
            # or be passed `self` if that were possible with decorators directly.
            # The current way it's defined inside _register_routes, it captures `self`.
            tasks = self._read_all_tasks_from_csv()  # Correctly uses self from the outer scope
            if not tasks and not os.path.exists(self.csv_file_path):
                return [{"message": "No CSV file found, or no tasks scheduled yet."}]
            return tasks

    def run_server(self, host: str = "127.0.0.1", port: int = 8001, reload: bool = False,
                   uvicorn_log_level: str = "info"):
        """Runs the Uvicorn server for this FastAPI application."""
        print(f"Starting Uvicorn server on http://{host}:{port}")
        print(f"Scheduler will check for tasks every {self.scheduler_interval} seconds.")
        print(f"Access OpenAPI docs at http://{host}:{port}/docs")

        if reload:
            # For reload=True, Uvicorn typically needs an "app string" like "module:instance.app_attribute".
            # This is hard to make perfectly generic for programmatic start if script/instance names vary.
            # The string provided in your original script "Backend.Server.server:app" assumes 'app' is a global.
            # If this file is 'server.py' and the instance is 'api_server_instance' (see __main__),
            # the string would be "server:api_server_instance.app".
            print("Reload is enabled. For programmatic start, ensure Uvicorn can find the app string.")
            print("It's often better to run 'uvicorn module:instance.app --reload' from CLI for reload.")
            # Provide a placeholder string; this will likely need adjustment based on your file and instance names.
            # Example: if this file is `my_server_module.py` and instance is `my_server = ApiServer()`
            # then "my_server_module:my_server.app"
            uvicorn.run("server:api_server_instance.app", host=host, port=port, reload=True,
                        log_level=uvicorn_log_level)
        else:
            uvicorn.run(self.app, host=host, port=port, reload=False, log_level=uvicorn_log_level)


# --- Main Block to Run Uvicorn ---
# This part allows running the server directly from this script.
# For Uvicorn reload from CLI to work (e.g., `uvicorn server:api_server_instance.app --reload`),
# `api_server_instance` needs to be a global variable in this module.
api_server_instance = ApiServer(
    agent_class=ActualAgent,  # Pass the actual or dummy Agent class
    agent_verbose=True,
    csv_file_path="class_based_scheduled_tasks.csv",  # Example: custom CSV path
    scheduler_interval=ApiServer.DEFAULT_SCHEDULER_INTERVAL_SECONDS
)

if __name__ == "__main__":
    # When running the script directly (e.g., `python server.py`)
    # For development with reload, it's often easier to run from the command line:
    # uvicorn server:api_server_instance.app --reload
    # (assuming this file is server.py and api_server_instance is globally accessible as defined above)

    # The run_server method handles non-reload cases well when called directly.
    # For reload=True, the app_string in run_server needs to be accurate.
    api_server_instance.run_server(reload=False)  # Set reload=True if you've configured the app string correctly.