# client_test.py
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# The base URL of your FastAPI server
SERVER_URL = "http://127.0.0.1:8001"
SCHEDULER_INTERVAL_ON_SERVER = 30  # Match server.py's SCHEDULER_INTERVAL_SECONDS

# Task prompts
USER_TASK_PDF = "load Backend/test.pdf and process it, then send a gmail"
USER_TASK_SUMMARY = "Summarize the benefits of using FastAPI for web development."
USER_TASK_SCHEDULED_1 = "This is a scheduled task to run shortly."
USER_TASK_SCHEDULED_2 = "This is another scheduled task for a bit later."


def print_server_response(test_name: str, response: requests.Response, start_time: float):
    end_time = time.time()
    print(f"\n--- [Client Test] Response for '{test_name}' ---")
    print(f"Status Code: {response.status_code}")
    print(f"Response Time: {end_time - start_time:.2f} seconds")
    try:
        response_data = response.json()
        print("Response JSON:")
        print(json.dumps(response_data, indent=2))
        if response.status_code == 200 and response_data.get("agent_output"):
            print(f"\nAgent Output: {response_data['agent_output']}")
        elif response.status_code != 200:
            print(f"Error Detail: {response_data.get('detail', response.text)}")
    except json.JSONDecodeError:
        print(f"Response Text (not JSON): {response.text}")


def test_endpoint(test_name: str, method: str, endpoint_suffix: str, payload: dict | None = None, timeout: int = 30):
    full_endpoint = f"{SERVER_URL}{endpoint_suffix}"
    print(f"\n--- [Client Test] Running '{test_name}': {method} {full_endpoint} ---")
    if payload:
        print(f"Payload: {json.dumps(payload)}")

    try:
        start_time = time.time()
        if method.upper() == "POST":
            response = requests.post(full_endpoint, json=payload, timeout=timeout)
        elif method.upper() == "GET":
            response = requests.get(full_endpoint, timeout=timeout)
        else:
            print(f"Unsupported method: {method}")
            return
        print_server_response(test_name, response, start_time)
        if response.status_code == 200:
            return response.json()  # Return parsed JSON for further use if needed
    except requests.exceptions.RequestException as e:
        print(f"\n--- [Client Test] Error for '{test_name}': {e} ---")
    return None


if __name__ == "__main__":
    print("=== Testing FastAPI Agent Server with Scheduling ===")

    # Test 1: Standard processing endpoint
    test_endpoint("Immediate Task (PDF)", "POST", "/process_task", {"prompt": USER_TASK_PDF}, timeout=60)

    print("\n" + "=" * 50 + "\n")

    # Test 2: Fire-and-forget endpoint
    test_endpoint("Fire-and-Forget Task (Summary)", "POST", "/process_task_fire_and_forget",
                  {"prompt": USER_TASK_SUMMARY})

    print("\n" + "=" * 50 + "\n")

    # Test 3: Schedule tasks
    # Schedule a task to run after the next scheduler cycle
    # If scheduler runs every 30s, schedule for 40s to give it time to pick up.
    delay1_seconds = SCHEDULER_INTERVAL_ON_SERVER + 10
    future_time1 = datetime.now(timezone.utc) + timedelta(seconds=delay1_seconds)
    scheduled_time_iso1 = future_time1.isoformat()
    test_endpoint(
        f"Schedule Task 1 (in ~{delay1_seconds}s)", "POST", "/schedule_task",
        {"prompt": USER_TASK_SCHEDULED_1, "scheduled_time": scheduled_time_iso1}
    )

    delay2_seconds = SCHEDULER_INTERVAL_ON_SERVER * 2 + 15  # After two scheduler cycles + buffer
    future_time2 = datetime.now(timezone.utc) + timedelta(seconds=delay2_seconds)
    scheduled_time_iso2 = future_time2.isoformat()
    test_endpoint(
        f"Schedule Task 2 (in ~{delay2_seconds}s)", "POST", "/schedule_task",
        {"prompt": USER_TASK_SCHEDULED_2, "scheduled_time": scheduled_time_iso2}
    )

    print("\n" + "=" * 50 + "\n")

    # Test 4: View tasks immediately after scheduling
    print("--- [Client Test] Viewing tasks immediately after scheduling... ---")
    test_endpoint("View Tasks (Initial)", "GET", "/view_tasks")

    print(f"\n--- [Client Test] Initial tests submitted. ---")
    print(f"--- Monitor server logs for scheduled tasks execution. ---")
    print(f"--- The server's scheduler checks every {SCHEDULER_INTERVAL_ON_SERVER} seconds. ---")

    # Wait for a bit to allow scheduled tasks to run
    # This total wait time should be enough for the latest scheduled task to complete
    total_wait_time_for_client = delay2_seconds + SCHEDULER_INTERVAL_ON_SERVER + 10  # wait past last task + one cycle + buffer
    print(
        f"\nClient will wait for approximately {total_wait_time_for_client} seconds to observe server logs and then view tasks again...")

    # You can print a countdown or progress
    for i in range(total_wait_time_for_client, 0, -10):
        print(f"Client waiting... {i}s remaining before final check.", end='\r')
        time.sleep(min(10, i))
    print("\nClient finished waiting.                                       ")

    print("\n" + "=" * 50 + "\n")
    print("--- [Client Test] After waiting, viewing tasks again to see status updates: ---")
    test_endpoint("View Tasks (Final)", "GET", "/view_tasks")

    print("\n--- [Client Test] All tests finished. ---")
    print(f"Check your server's console output for detailed logs of all operations.")
    print(f"A '{CSV_FILE_PATH}' file should be created/updated in the server's directory.")