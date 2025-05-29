from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.llms.gemini import Gemini
from dotenv import load_dotenv
import os
from llama_index.core.tools import FunctionTool
from llama_index.core.memory import BaseMemory
from llama_index.core.memory import ChatMemoryBuffer


load_dotenv()
GeminiKey = os.getenv("GeminiKey")

llm = Gemini(
    model="gemini-2.5-flash-preview-04-17",
    api_key=GeminiKey,
)

class Agent:
    def __init__(self, system_prompt: str, name: str = "Main_Agent", verbose: bool = False):
        self.name = name
        self.tools = []
        self.verbose = verbose
        self.SubWorkers = {}
        self._add_tools()

        self.worker = FunctionAgent(
            tools=self.tools,
            llm=llm,
            system_prompt=system_prompt,)

        self.memory = ChatMemoryBuffer.from_defaults(token_limit=390000)
        print(f"Initialized '{self.name}' with system prompt: '{system_prompt}' and {len(self.tools)} tools.")

    async def run(self, user_msg: str) -> str:
        if (self.verbose): 
            print(f"\n--- [{self.name}] Task received: {user_msg} ---")
        try:
            agent_response = await self.worker.run(user_msg=user_msg, memory=self.memory)
            response = str(agent_response.response)

            if (self.verbose): 
                print(f"--- [{self.name}] Response: {response} ---")
            return response
        except Exception as e:
            print(f"--- [{self.name}] Error during run: {e} ---")
            return f"Error in {self.name}: {str(e)}"

    def _add_tools(self):
        """Helper method to create and add tools for sub-agent management."""

        def _list_sub_agents_tool_func() -> str:
            """Internal wrapper for the ListSubAgents tool."""
            print("calling list")
            return self.ListSubAgents()

        list_tool = FunctionTool.from_defaults(
            fn=_list_sub_agents_tool_func,
            name="list_sub_agents",
            description="Lists the names of all currently available sub-agents that can be called for specialized tasks."
        )
        self.tools.append(list_tool)

        def _create_sub_agent_tool_func(name: str, system_prompt_for_subagent: str) -> str:
            """
            Internal wrapper for the CreateSubAgent tool.
            This tool allows the agent to create a new sub-agent with a specific name and system prompt.
            It does NOT allow specifying tools for the sub-agent via this LLM tool for simplicity and security.
            """
            print("calling create")
            return self.CreateSubAgent(name=name, system_prompt=system_prompt_for_subagent)

        create_tool = FunctionTool.from_defaults(
            fn=_create_sub_agent_tool_func,
            name="create_new_sub_agent",
            description=(
                "Creates a new specialized sub-agent. Use this when a new, distinct expertise is required that existing sub-agents don't cover. "
                "You need to provide a unique 'name' for the new sub-agent and a 'system_prompt_for_subagent' that defines its role and expertise. "
                "Example: create_new_sub_agent(name='MathExpert', system_prompt_for_subagent='You are an expert in advanced calculus and algebra.')"
            )
        )
        self.tools.append(create_tool)

        async def _call_sub_agent_tool_func(sub_agent_name: str, task_for_subagent: str) -> str:
            """
            Internal wrapper for a generic CallSubAgent tool.
            Delegates a task to a specified sub-agent by its name.
            """
            print("calling call")
            full_sub_agent_name = sub_agent_name if "/" in sub_agent_name else f"{self.name}/{sub_agent_name}"
            return await self.CallSubAgent(name=full_sub_agent_name, task=task_for_subagent)

        call_tool = FunctionTool.from_defaults(
            fn=_call_sub_agent_tool_func,
            name="call_specific_sub_agent",
            description=(
                "Delegates a specific 'task_for_subagent' to a sub-agent identified by 'sub_agent_name'. "
                "First, ensure the sub-agent exists (e.g., using 'list_sub_agents' or if it was recently created). "
                "Then, provide the exact name of the sub-agent and the detailed task for it to perform. "
                "This is useful for explicitly directing tasks to known sub-agents."
            )
        )
        self.tools.append(call_tool)

    def ListSubAgents(self) -> str:
        """Lists the names of all created sub-agents."""
        return str(list(self.SubWorkers.keys()))

    def CreateSubAgent(self, name: str, system_prompt: str) -> str:
        """
        Creates a new sub-agent and adds a tool to the parent agent to call this sub-agent.

        Args:
            name: The name of the sub-agent.
            system_prompt: The system prompt for the sub-agent.

        Returns:
            The created sub-agent instance.
        """
        try:
            name = self.name + "/" + name
            if name in self.SubWorkers:
                msg = f"Warning: Sub-agent with name '{name}' already exists. Returning existing instance."
                print(msg)
                return msg
            if self.verbose:
                print(f"--- [{self.name}] Creating SubAgent: '{name}' ---")
            sub_agent = Agent(
                system_prompt=system_prompt,
                name=name,
                verbose=self.verbose
            )
            self.SubWorkers[name] = sub_agent
            return f"Sub-agent '{name}' created successfully with system prompt: '{system_prompt}'. It can now be called using its name."
        except Exception as e:
            msg = f"Error creating sub-agent '{name}': {str(e)}"
            print(msg)
            return msg

    async def CallSubAgent(self, name: str, task: str) -> str:
        """
        Allows direct programmatic calling of a sub-agent's run method.
        This is not for the LLM to use as a tool, but for direct orchestration from code.

        Args:
            name: The name of the sub-agent to call.
            task: The task string to pass to the sub-agent's run method.

        Returns:
            The result from the sub-agent's run method or an error message.
        """
        if name in self.SubWorkers:
            sub_agent = self.SubWorkers[name]
            if self.verbose:
                print(f"--- [{self.name}] Directly calling SubAgent '{name}' with task: {task} ---")
            return await sub_agent.run(task)
        else:
            error_msg = f"Error: Sub-agent '{name}' not found in '{self.name}'."
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
            return error_msg
