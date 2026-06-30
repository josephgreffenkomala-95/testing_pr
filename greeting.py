import datetime


def _detect_time_of_day():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"


def greet(name, greeting="Hello", time_of_day=None):
    if time_of_day is None:
        time_of_day = _detect_time_of_day()
    return f"Good {time_of_day}, {name}! Welcome!"


if __name__ == "__main__":
    name = input("Enter your name: ")
    print(greet(name))