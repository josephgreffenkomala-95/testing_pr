#!/usr/bin/env python3
import sys

def calculate(expression):
    try:
        result = eval(expression)
        return result
    except:
        return "Error: Invalid expression"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        expr = ' '.join(sys.argv[1:])
        print(f"Result: {calculate(expr)}")
    else:
        print("Usage: python3 calculator.py <expression>")
        print("Example: python3 calculator.py '2 + 3 * 4'")