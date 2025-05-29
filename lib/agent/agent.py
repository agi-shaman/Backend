from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.gemini import Gemini
from dotenv import load_dotenv
import os

load_dotenv()
GeminiKey = os.getenv("GeminiKey")

llm = Gemini(
    model="models/gemini-1.5-flash",
    api_key=GeminiKey,
)

class Agent:
    def __init__(self):
        self.agent = FunctionAgent(
        tools=[search_web],
        llm=llm,
        system_prompt="You are a helpful assistant that can search the web for information.",)
