def inspect(text: str, labels: list[str]) -> bool:
    return all(label in text for label in labels)
