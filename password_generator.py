#!/usr/bin/env python3
import random
import string
import sys

def generate_password(length=16, use_symbols=True):
    chars = string.ascii_letters + string.digits
    if use_symbols:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"
    return ''.join(random.choice(chars) for _ in range(length))

if __name__ == "__main__":
    length = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    use_symbols = sys.argv[2].lower() != 'no' if len(sys.argv) > 2 else True
    print(generate_password(length, use_symbols))