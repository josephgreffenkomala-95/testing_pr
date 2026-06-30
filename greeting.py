def greet(name, greeting="Hello", time_of_day=None):
    if time_of_day:
        return f"Good {time_of_day}, {name}! Welcome!"
    return f"{greeting}, {name}! Welcome!"

if __name__ == "__main__":
    name = input("Enter your name: ")
    print(greet(name))