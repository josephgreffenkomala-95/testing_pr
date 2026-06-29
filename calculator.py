#!/usr/bin/env python3
import sys

def calculate(expression):
    try:
        result = eval(expression)
        return result
    except Exception as e:
        return f"Error: {str(e)}"


def multiply(a, b):
    """Multiply two numbers."""
    return a * b


def derivative(expression, at_point):
    """Compute numerical derivative of expression at a point using central difference."""
    h = 1e-7

    def f(x):
        return eval(expression, {"__builtins__": {}}, {"x": x})

    return (f(at_point + h) - f(at_point - h)) / (2 * h)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 calculator.py <expression>")
        print("  python3 calculator.py multiply <a> <b>")
        print("  python3 calculator.py derivative '<expr>' <x>")
        print("")
        print("Examples:")
        print("  python3 calculator.py '2 + 3 * 4'")
        print("  python3 calculator.py multiply 5 3")
        print("  python3 calculator.py derivative 'x**2' 4")
        sys.exit(1)

    command = sys.argv[1]

    if command == "multiply" and len(sys.argv) == 4:
        a, b = float(sys.argv[2]), float(sys.argv[3])
        print(f"Result: {multiply(a, b)}")
    elif command == "derivative" and len(sys.argv) == 4:
        expr = sys.argv[2]
        at_point = float(sys.argv[3])
        print(f"Result: {derivative(expr, at_point)}")
    else:
        expr = ' '.join(sys.argv[1:])
        print(f"Result: {calculate(expr)}")