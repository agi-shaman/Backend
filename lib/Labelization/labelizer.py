import os
from google import genai

genai.configure(api_key=os.environ["GeminiKey"])
MODEL   = "gemini-1.5-pro-latest"
TEMP    = 0.0               
MAX_OUT = 8                 

SYSTEM_PROMPT = (
    "You are a concise topic generator.\n"
    "Given ONE user request, respond with 2-5 words that best describe the topic.\n"
    "No punctuation, all lower-case, no explanations."
)

def topicize(sentence: str) -> str:
    """Return a 2-5 word, lower-case topic string for the given sentence."""
    model = genai.GenerativeModel(MODEL)
    resp  = model.generate_content(
        contents=[
            {"role": "system", "parts": SYSTEM_PROMPT},
            {"role": "user",   "parts": sentence}
        ],
        generation_config=genai.GenerationConfig(
            temperature=TEMP,
            max_output_tokens=MAX_OUT
        ),
    )
    return resp.text.strip().lower()

if __name__ == "__main__":
    examples = [
        "Can you help me cook for ten people tonight?",
        "I need to file my US federal tax return for 2024.",
        "Renew my Israeli passport, please.",
        "What exercises improve lower-back strength?"
    ]
    for s in examples:
        print(f"{s}  →  {topicize(s)}")
