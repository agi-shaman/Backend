import tenacity
import google.api_core.exceptions
import time

# Define exceptions that should trigger a retry
RETRY_EXCEPTIONS = (
    google.api_core.exceptions.ResourceExhausted, # Rate limit exceeded
    google.api_core.exceptions.ServiceUnavailable, # Transient server errors
    google.api_core.exceptions.InternalServerError, # Transient internal errors
    # Add other relevant exceptions as identified during testing
)

def retry_gemini_api_call(func):
    """
    Decorator to apply retry logic with exponential backoff to Gemini API calls.
    """
    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=10, max=60),
        stop=tenacity.stop_after_attempt(5),
        retry=tenacity.retry_if_exception_type(RETRY_EXCEPTIONS),
        before_sleep=lambda retry_state: print(
            f"Retrying {retry_state.fn.__name__} after {retry_state.seconds_since_start:.2f}s, "
            f"attempt {retry_state.attempt_number} failed with {retry_state.outcome.exception()}"
        )
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

# Example usage (will be applied in agent.py)
# @retry_gemini_api_call
# def call_gemini_complete(...):
#     # Call the actual gemini complete method
#     pass

# @retry_gemini_api_call
# async def acall_gemini_complete(...):
#     # Call the actual async gemini complete method
#     pass