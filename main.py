def greet(name: str) -> str:
    """Return a friendly greeting message."""
    return f"Hello, {name}! Welcome to Interactcode."


if __name__ == "__main__":
    user_name = input("Enter your name: ").strip() or "Developer"
    print(greet(user_name))