import json
import os
from typing import TypedDict

from dotenv import load_dotenv
from groq import Groq

from langgraph.graph import StateGraph, START, END

from app.tools.rag_tool import rag_tool
from app.tools.calculator_tool import calculator_tool
from app.tools.log_tool import log_tool
from app.tools.metrics_tool import metrics_tool


# -------------------------
# Configuration
# -------------------------

load_dotenv()

MODEL = "openai/gpt-oss-20b"

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


# -------------------------
# State
# -------------------------

class AgentState(TypedDict):
    messages: list


# -------------------------
# Tool definitions
# -------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "rag_tool",
            "description": (
                "Search the DevOps knowledge base. "
                "Use this when the user asks about information "
                "contained in runbooks, documentation, or policies."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Question to search in the DevOps knowledge base."
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator_tool",
            "description": (
                "Perform accurate mathematical calculations. "
                "Use this whenever the question requires arithmetic, "
                "percentages, ratios, differences, or other calculations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to calculate."
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "metrics_tool",
        "description": (
            "Retrieve payment service performance metrics "
            "such as CPU usage, memory usage, request count, "
            "error count, average latency, and P95 latency."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Describe the performance metrics "
                        "you want to investigate."
                    )
                }
            },
            "required": ["query"]
        }
    }
},
    {
    "type": "function",
    "function": {
        "name": "log_tool",
        "description": (
            "Analyze application logs for errors, warnings, "
            "exceptions, database timeouts, failed requests, "
            "and other indicators of incidents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Describe what you want to investigate "
                        "in the application logs."
                    )
                }
            },
            "required": ["query"]
        }
    }
}
]


# -------------------------
# Agent node
# -------------------------

def agent_node(state: AgentState):

    messages = [
        {
            "role": "system",
            "content": (
                "Base factual claims only on information returned by the tools "
                "or provided directly by the user.\n\n"
                "Do not invent SLAs, thresholds, time periods, infrastructure "
                "details, monitoring information, or units that are not provided.\n\n"
                "Do not add units, timestamps, time ranges, or qualifiers "
                "to numeric values unless they are explicitly provided.\n\n"
                "Clearly distinguish between:\n"
                "1. Observed evidence\n"
                "2. Reasonable inference\n"
                "3. Unknown or unverified information\n\n"
                "If the available evidence is insufficient to establish a "
                "root cause, say so."
            )
        }
    ] + state["messages"]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    return {
        "messages": state["messages"] + [response.choices[0].message]
    }


# -------------------------
# Tool node
# -------------------------

def tool_node(state: AgentState):

    last_message = state["messages"][-1]

    new_messages = list(state["messages"])

    for tool_call in last_message.tool_calls:

        function_name = tool_call.function.name

        arguments = json.loads(
            tool_call.function.arguments
        )

        print(f"\nTool selected: {function_name}")
        print(f"Arguments: {arguments}")

        if function_name == "rag_tool":

            result = rag_tool(
                arguments["question"]
            )

        elif function_name == "calculator_tool":

            result = calculator_tool(
                arguments["expression"]
            )
        
        elif function_name == "metrics_tool":
            
            result = metrics_tool(
                arguments["query"]
            )
        
        elif function_name == "log_tool":

             result = log_tool(
                arguments["query"]
            )

        else:

            result = "Unknown tool."

        new_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": result
            }
        )

    return {
        "messages": new_messages
    }


# -------------------------
# Routing
# -------------------------

def route_after_agent(state: AgentState):

    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "tools"

    return END


# -------------------------
# Build graph
# -------------------------

graph_builder = StateGraph(AgentState)

graph_builder.add_node(
    "agent",
    agent_node
)

graph_builder.add_node(
    "tools",
    tool_node
)

graph_builder.add_edge(
    START,
    "agent"
)

graph_builder.add_conditional_edges(
    "agent",
    route_after_agent,
    {
        "tools": "tools",
        END: END
    }
)

graph_builder.add_edge(
    "tools",
    "agent"
)


graph = graph_builder.compile()


# -------------------------
# Test
# -------------------------

if __name__ == "__main__":

    question = (
    "Why is the payment service experiencing high latency? "
    "Check the performance metrics and application logs."
)

    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a DevOps incident response assistant. "
                        "Use the available tools when necessary. "
                        "Use the calculator tool for calculations and "
                        "the RAG tool for information from the knowledge base. "
                        "Do not invent information that is not supported "
                        "by tool results."
                    )
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
        }
    )

    print("\nFinal Answer:")
    print(result["messages"][-1].content)