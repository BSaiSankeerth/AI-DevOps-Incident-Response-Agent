def calculator_tool(expression: str) -> str:
    """
    Calculate a mathematical expression accurately.
    """

    try:
        result = eval(expression, {"__builtins__": {}}, {})

        return str(result)

    except Exception as e:
        return f"Calculation error: {str(e)}"


if __name__ == "__main__":
    print(calculator_tool("((800 - 200) / 200) * 100"))