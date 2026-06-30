def greet(name, greeting="Hello"):
    return f"{greeting}, {name}! Welcome!"

if __name__ == "__main__":
    name = input("Enter your name: ")
    print(greet(name))