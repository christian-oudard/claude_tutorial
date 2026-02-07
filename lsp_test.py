from pathlib import Path

def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"

def main():
    path = Path(".")
    message = greet("world")
    print(message)

if __name__ == "__main__":
    main()
