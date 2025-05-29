import os
import json
import logging
import sys
from functools import wraps
import base64
# from email.mime.text import MIMEText # Replaced
from email.message import EmailMessage  # Using EmailMessage as per Google's guide

import firebase_admin
from firebase_admin import credentials, auth
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

from llama_index.llms.gemini import Gemini
from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Configuration & Setup ---
load_dotenv()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize Firebase Admin SDK
try:
    SERVICE_ACCOUNT_KEY_PATH = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")
    if not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
        logger.error(f"Firebase service account key not found at {SERVICE_ACCOUNT_KEY_PATH}")
        sys.exit(1)
    cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK initialized.")
except Exception as e:
    logger.error(f"Error initializing Firebase Admin SDK: {e}")
    sys.exit(1)

# Initialize Gemini LLM
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    logger.error("Error: GOOGLE_API_KEY not found in .env file or environment variables.")
    sys.exit(1)
llm = Gemini(api_key=GEMINI_API_KEY, model_name="gemini-2.0-flash")


# --- Authentication Decorator ---
def firebase_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = None
        access_token = None
        auth_header = request.headers.get('Authorization')
        goog_access_token_header = request.headers.get('X-Goog-Access-Token')

        if auth_header and auth_header.startswith('Bearer '):
            id_token = auth_header.split('Bearer ')[1]
        if goog_access_token_header:
            access_token = goog_access_token_header

        if not id_token:
            return jsonify({"error": "Authorization token is missing (Firebase ID Token)"}), 401
        if not access_token:
            return jsonify({"error": "Google Access token is missing (X-Goog-Access-Token header)"}), 401

        try:
            decoded_token = auth.verify_id_token(id_token)
            request.user = decoded_token
            request.google_access_token = access_token
            print(access_token)
            logger.info(f"User {decoded_token.get('email')} authenticated.")
        except firebase_admin.auth.InvalidIdTokenError as e:
            logger.error(f"Invalid Firebase ID token: {e}")
            return jsonify({"error": "Invalid Firebase authorization token"}), 401
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return jsonify({"error": "Token verification failed"}), 500
        return f(*args, **kwargs)

    return decorated_function


# --- Gmail API Helpers ---
def get_gmail_service(user_google_access_token: str):
    """Initializes and returns a Gmail API service object."""
    if not user_google_access_token:
        raise ValueError("Google access token is required to initialize Gmail service.")
    print(f"token --- {user_google_access_token}")
    creds = GoogleCredentials(token=user_google_access_token)
    try:
        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
        logger.info("Gmail API service initialized for user.")
        return service
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {e}")
        raise


def create_gmail_message_body(to_email: str, subject: str, message_text: str) -> dict:
    """Creates a Gmail API-compatible message body (base64url encoded) using EmailMessage."""
    message = EmailMessage()
    message.set_content(message_text)  # For plain text content
    message['To'] = to_email
    message['Subject'] = subject
    # 'From' will be set by Gmail API based on authenticated user (userId='me')
    # If you needed to set 'From' explicitly (e.g. for a delegated sender), you would do:
    # message['From'] = "sender@example.com"
    # But ensure the authenticated user has rights to send as that address.

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw_message}


# ... (other imports and setup remain the same) ...

# --- LLM Email Content Generation (Further Refined for 100% Ready Emails) ---
def generate_email_content_with_gemini(prompt_for_email: str, recipient_email: str) -> tuple[str, str]:
    logger.info(f"Generating 100% ready email content for: {prompt_for_email} (to: {recipient_email})")

    # We can try to infer the relationship or key details from the prompt to help the LLM
    # This is a simple example; more sophisticated parsing could be done.
    # For instance, if 'dad' or 'father' is in the prompt, we can hint that.
    relationship_hint = ""
    if "dad" in prompt_for_email.lower() or "father" in prompt_for_email.lower():
        relationship_hint = "The email is likely for the user's father."
    elif "mom" in prompt_for_email.lower() or "mother" in prompt_for_email.lower():
        relationship_hint = "The email is likely for the user's mother."
    elif "friend" in prompt_for_email.lower():
        relationship_hint = "The email is likely for a friend."
    # Add more hints as needed

    full_prompt = f"""
    You are an AI assistant helping to draft a complete, personalized, and 100% ready-to-send email.
    The recipient is: {recipient_email}
    The user's request for the email is: "{prompt_for_email}"
    {relationship_hint}

    Your task is to generate a suitable subject line and a professional, heartfelt, or appropriate email body based on the user's request.
    The email you generate MUST be fully complete. Do NOT include any placeholders like "[mention something]", "[e.g., ...]", or similar bracketed instructions.
    If the user's request is somewhat vague (e.g., "write a birthday email to my dad"), you should be creative and fill in plausible, warm, and specific-sounding (but general enough) details.
    For example, instead of "[mention a specific quality]", you should invent a positive quality like "your incredible kindness" or "your unwavering determination".
    Instead of "[mention a shared activity]", invent a plausible shared activity like "our talks over coffee" or "the time we went hiking in the mountains."

    The goal is a polished email that the user can send immediately without any further editing.

    Return ONLY a valid JSON object with two keys: "subject" and "body".
    Ensure the body is a single string, using newline characters (\\n) for line breaks.
    Do not include any text or explanations before or after the JSON object.
    Do not include salutations like "Dear [Name]," or closings like "Best regards,\n[Your Name]" unless the user's prompt specifically asks for them or it's highly implied by the context (e.g. a very formal letter, but generally avoid for typical emails). The core message is key.

    Example of your exact output format for a request "wish my friend Alex a happy birthday":
    {{
      "subject": "Happy Birthday, Alex!",
      "body": "Just wanted to send a huge happy birthday your way, Alex! I hope you have an absolutely fantastic day filled with joy, laughter, and everything you wished for. Thinking of all the great times we've had, especially that hilarious karaoke night last year! Let's catch up soon and celebrate properly. All the best!"
    }}

    Now, based on the user's request "{prompt_for_email}", generate the subject and body.
    """
    try:
        response = llm.complete(full_prompt)
        llm_output_text = response.text.strip()
        logger.info(f"Raw LLM output for 100% ready email: {llm_output_text}")

        if llm_output_text.startswith("```json"):
            llm_output_text = llm_output_text.replace("```json", "", 1).strip()
        if llm_output_text.startswith("```"):
            llm_output_text = llm_output_text.replace("```", "", 1).strip()
        if llm_output_text.endswith("```"):
            llm_output_text = llm_output_text[:-3].strip()

        content = json.loads(llm_output_text)
        subject = content.get("subject")
        body = content.get("body")

        if not subject or not body:
            logger.warning("LLM output parsed, but 'subject' or 'body' key is missing/empty for 100% ready email.")
            subject = f"Generated Content for: {prompt_for_email}"
            body = f"The AI tried to generate a complete email, but the subject/body was incomplete in the JSON. Raw AI output:\n{llm_output_text}"
        else:
            # Further check if common placeholders are still present (as a safeguard)
            placeholders = ["[mention", "[e.g.,", "[Location", "[Date", "[Time", "[RSVP Date"]
            if any(p.lower() in body.lower() for p in placeholders) or \
                    any(p.lower() in subject.lower() for p in placeholders):
                logger.warning(f"LLM generated email still contains placeholders: Subject='{subject}', Body='{body}'")
                # You could choose to append a warning to the body or handle this differently
                # For now, we'll let it pass but log it.
            else:
                logger.info("100% ready email content generated and parsed successfully.")

        return subject, body

    except json.JSONDecodeError as e:
        logger.error(f"LLM did not return valid JSON for 100% ready email. Raw output: '{response.text}'. Error: {e}")
        subject = f"Draft for: {prompt_for_email} (JSON parse error)"
        body = f"Could not parse LLM output as JSON. Raw output below:\n\n{response.text}"
        return subject, body
    except AttributeError:
        logger.error(f"LLM response object error for 100% ready email. Response: {response}")
        subject = f"Draft for: {prompt_for_email} (LLM response format error)"
        body = f"Error processing LLM response. Raw response: {str(response)}"
        return subject, body
    except Exception as e:
        logger.error(f"Error generating 100% ready email content: {e}")
        subject = f"Error processing: {prompt_for_email}"
        body = f"Could not generate email body due to an unexpected error: {e}\n\nRaw LLM response (if available): {str(response.text if hasattr(response, 'text') else response)}"
        return subject, body


# ... (rest of the Flask app code remains the same) ...


# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/generate_email', methods=['POST'])
@firebase_auth_required
def generate_email_route():
    data = request.get_json()
    recipient = data.get('recipient')
    prompt = data.get('prompt')

    if not recipient or not prompt:
        return jsonify({"error": "Recipient and prompt are required"}), 400

    try:
        subject, body = generate_email_content_with_gemini(prompt, recipient)
        return jsonify({"subject": subject, "body": body}), 200
    except Exception as e:
        logger.error(f"Error in /generate_email: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/send_email', methods=['POST'])
@firebase_auth_required
def send_email_route():
    data = request.get_json()
    recipient = data.get('recipient')
    subject = data.get('subject')
    body = data.get('body')
    user_google_access_token = request.google_access_token

    if not all([recipient, subject, body]):
        return jsonify({"error": "Recipient, subject, and body are required"}), 400

    try:
        service = get_gmail_service(user_google_access_token)
        message_payload = create_gmail_message_body(to_email=recipient, subject=subject, message_text=body)

        sent_message = service.users().messages().send(userId='me', body=message_payload).execute()
        msg_id = sent_message.get('id', 'N/A')
        logger.info(f"Email sent by {request.user.get('email')}. Message ID: {msg_id}")
        return jsonify({"message": f"Email sent successfully! Message ID: {msg_id}"}), 200
    except HttpError as error:
        logger.error(
            f"An API error occurred while sending email for {request.user.get('email')}: {error.resp.status} - {error._get_reason()}")
        error_details = error.content.decode() if isinstance(error.content, bytes) else str(error.content)
        try:
            error_json = json.loads(error_details)
            error_message = error_json.get("error", {}).get("message", "Failed to send email due to API error.")
        except (json.JSONDecodeError, AttributeError):
            error_message = f"Failed to send email: {error._get_reason()}"
        return jsonify({"error": error_message}), error.resp.status
    except Exception as e:
        logger.error(f"Error sending email for {request.user.get('email')}: {e}")
        return jsonify({"error": f"Failed to send email: {str(e)}"}), 500


@app.route('/draft_email', methods=['POST'])
@firebase_auth_required
def draft_email_route():
    data = request.get_json()
    recipient = data.get('recipient')
    subject = data.get('subject')
    body = data.get('body')
    user_google_access_token = request.google_access_token

    if not all([recipient, subject, body]):
        return jsonify({"error": "Recipient, subject, and body are required"}), 400

    try:
        service = get_gmail_service(user_google_access_token)
        message_payload = create_gmail_message_body(to_email=recipient, subject=subject, message_text=body)

        draft_body = {'message': message_payload}  # For drafts, the 'raw' message is nested under 'message'
        created_draft = service.users().drafts().create(userId='me', body=draft_body).execute()
        draft_id = created_draft.get('id', 'N/A')
        logger.info(f"Draft created by {request.user.get('email')}. Draft ID: {draft_id}")
        return jsonify({"message": f"Draft created successfully! Draft ID: {draft_id}"}), 200
    except HttpError as error:
        logger.error(
            f"An API error occurred while creating draft for {request.user.get('email')}: {error.resp.status} - {error._get_reason()}")
        error_details = error.content.decode() if isinstance(error.content, bytes) else str(error.content)
        try:
            error_json = json.loads(error_details)
            error_message = error_json.get("error", {}).get("message", "Failed to create draft due to API error.")
        except (json.JSONDecodeError, AttributeError):
            error_message = f"Failed to create draft: {error._get_reason()}"
        return jsonify({"error": error_message}), error.resp.status
    except Exception as e:
        logger.error(f"Error creating draft for {request.user.get('email')}: {e}")
        return jsonify({"error": f"Failed to create draft: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
