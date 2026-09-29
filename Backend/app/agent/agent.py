import json
import os

from dotenv import load_dotenv
from groq import Groq

from app.tools.rag_tool import rag_tool
from app.tools.calculator_tool import calculator_tool


# -------------------------
# Configuration
# -------------------------

load_dotenv()

MODEL = "openai/gpt-oss-20b"


# -------------------------
# Groq client
# -------------------------

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


# -------------------------
# Tool definition
# -------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "rag_tool",
            "description": (
                "Search the DevOps knowledge base and retrieve "
                "information from uploaded documentation and runbooks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "The question to search for in the "
                            "DevOps knowledge base."
                        ),
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator_tool",
            "description": (
                "Perform accurate mathematical calculations. "
                "Use this tool whenever the user asks for "
                "percentages, differences, ratios, or other calculations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "The mathematical expression to calculate."
                        ),
                    }
                },
                "required": ["expression"],
            },
        },
    },
]


# -------------------------
# Agent
# -------------------------

def run_agent(user_question: str):

    messages = [
        {
            "role": "system",
            "content": (
                "You are a DevOps incident response assistant. "
                "Use the available tools when they are useful. "
                "When a tool is used, base your answer on the information "
                "returned by that tool. Do not invent logs, metrics, commands, "
                "configuration details, or other facts that are not supported "
                "by the tool results. If the available information is "
                "insufficient, clearly say so."
            ),
        },
        {
            "role": "user",
            "content": user_question,
        },
    ]

    while True:

        # Ask Groq what to do next
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        response_message = response.choices[0].message

        # Add Groq's response to the conversation
        messages.append(response_message)

        # If Groq does not request a tool,
        # it has produced the final answer.
        if not response_message.tool_calls:
            return response_message.content

        # Execute every tool requested by Groq
        for tool_call in response_message.tool_calls:

            function_name = tool_call.function.name

            arguments = json.loads(
                tool_call.function.arguments
            )

            print(f"\nTool selected: {function_name}")
            print(f"Arguments: {arguments}")

            if function_name == "rag_tool":

                tool_result = rag_tool(
                    arguments["question"]
                )

            elif function_name == "calculator_tool":

                tool_result = calculator_tool(
                    arguments["expression"]
                )

            else:

                tool_result = "Unknown tool."

            # Give the tool result back to Groq
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": tool_result,
                }
            )


# -------------------------
# Test
# -------------------------

if __name__ == "__main__":

    question = (
    "The payment service latency increased from 200ms to 800ms. "
    "What is the percentage increase, and what does the runbook "
    "say I should check first?"
)

    answer = run_agent(question)

    print("\nFinal Answer:")
    print(answer)