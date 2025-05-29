import requests
import json
import time

# The base URL of your FastAPI server
SERVER_URL = "http://127.0.0.1:8000"

# The task prompt you want to send
USER_TASK = "load Backend/test.pdf at the current dir, and fill in the information needed with place holders, in a new pdf file(copy the current file and change the fields needed for change), then send a gmail to eitankorh123@gmail.com with it in it, and with some message related to the file"
ANOTHER_TASK = "Summarize the benefits of using FastAPI for web development."


def test_process_task_endpoint(prompt: str):
    """Tests the /process_task endpoint which waits for completion."""
    endpoint = f"{SERVER_URL}/process_task"
    payload = {"prompt": prompt}

    print(f"\n--- [Client Test] Sending task to {endpoint} ---")
    print(f"Payload: {json.dumps(payload)}")

    try:
        start_time = time.time()
        response = requests.post(endpoint, json=payload, timeout=60)  # Added timeout
        end_time = time.time()

        print(f"\n--- [Client Test] Response from {endpoint} ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {end_time - start_time:.2f} seconds")

        if response.status_code == 200:
            response_data = response.json()
            print("Response JSON:")
            print(json.dumps(response_data, indent=2))
            if response_data.get("agent_output"):
                print(f"\nAgent Output: {response_data['agent_output']}")
        else:
            print(f"Error: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"\n--- [Client Test] Error connecting to server or during request: {e} ---")


def test_fire_and_forget_endpoint(prompt: str):
    """Tests the /process_task_fire_and_forget endpoint."""
    endpoint = f"{SERVER_URL}/process_task_fire_and_forget"
    payload = {"prompt": prompt}

    print(f"\n--- [Client Test] Sending task to {endpoint} (fire-and-forget) ---")
    print(f"Payload: {json.dumps(payload)}")

    try:
        start_time = time.time()
        response = requests.post(endpoint, json=payload, timeout=10)  # Shorter timeout
        end_time = time.time()

        print(f"\n--- [Client Test] Response from {endpoint} ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {end_time - start_time:.2f} seconds")

        if response.status_code == 200:
            response_data = response.json()
            print("Response JSON:")
            print(json.dumps(response_data, indent=2))
            print("\nNote: For fire-and-forget, actual processing happens in the background on the server.")
            print("Check server logs for completion of the task.")
        else:
            print(f"Error: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"\n--- [Client Test] Error connecting to server or during request: {e} ---")


if __name__ == "__main__":
    print("=== Testing FastAPI Agent Server ===")

    # Test 1: Standard processing endpoint
    test_process_task_endpoint(USER_TASK)

    print("\n" + "=" * 30 + "\n")

    # Test 2: Fire-and-forget endpoint
    test_fire_and_forget_endpoint(ANOTHER_TASK)

    print("\n--- [Client Test] All tests finished. ---")
    print("Remember to check your server's console output for logs, especially for the fire-and-forget task.")