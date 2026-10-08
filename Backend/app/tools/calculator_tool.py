import ast
import operator

MAX_EXPONENT = 100

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

FUNCTIONS = {"round": round, "abs": abs, "min": min, "max": max}


def calculate(node):
    """Recursively evaluate a safe mathematical expression."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("Only numbers are allowed.")

    if isinstance(node, ast.BinOp):
        left, right = calculate(node.left), calculate(node.right)
        op = OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported operator.")
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError("Exponent too large.")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported operator.")
        return op(calculate(node.operand))

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
        return FUNCTIONS[node.func.id](*[calculate(a) for a in node.args])

    raise ValueError("Invalid mathematical expression.")


def calculator_tool(expression: str) -> str:
    """
    Safely calculate a math expression, e.g. "((800 - 200) / 200) * 100".
    Commas and % signs are tolerated ("1,250" -> 1250).
    """
    try:
        cleaned = str(expression).replace(",", "").replace("%", "").replace("×", "*").strip()
        result = calculate(ast.parse(cleaned, mode="eval").body)
        if isinstance(result, float):
            result = int(result) if result.is_integer() else round(result, 4)
        return str(result)
    except ZeroDivisionError:
        return "Calculation error: division by zero."
    except Exception as e:
        return f"Calculation error: {e}"


if __name__ == "__main__":
    print(calculator_tool("((800 - 200) / 200) * 100"))