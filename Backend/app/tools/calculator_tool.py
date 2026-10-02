import ast
import operator


# Supported mathematical operations
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def calculate(node):
    """
    Recursively evaluate a safe mathematical expression.
    """

    if isinstance(node, ast.Constant):

        if isinstance(node.value, (int, float)):
            return node.value

        raise ValueError("Only numbers are allowed.")

    if isinstance(node, ast.BinOp):

        left = calculate(node.left)
        right = calculate(node.right)

        operation = OPERATORS.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported operator.")

        return operation(left, right)

    if isinstance(node, ast.UnaryOp):

        operand = calculate(node.operand)

        operation = OPERATORS.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported operator.")

        return operation(operand)

    raise ValueError("Invalid mathematical expression.")


def calculator_tool(expression: str) -> str:
    """
    Safely calculate a mathematical expression.
    """

    try:

        tree = ast.parse(
            expression,
            mode="eval"
        )

        result = calculate(tree.body)

        return str(result)

    except ZeroDivisionError:

        return "Calculation error: division by zero."

    except Exception as e:

        return f"Calculation error: {str(e)}"


if __name__ == "__main__":

    print(
        calculator_tool(
            "((800 - 200) / 200) * 100"
        )
    )