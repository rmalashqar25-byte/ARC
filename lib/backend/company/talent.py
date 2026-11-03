"""An explicitly fictional profile shows how the human directory works."""


def example_profile():
    return {
        "id": "example-human-profile",
        "name": "Maya Chen",
        "role": "Research & product designer",
        "summary": (
            "Example: helps a small team turn customer interviews into clear "
            "insights, a focused product brief, and a clickable prototype. "
            "A good fit when you need to understand users before building."
        ),
        "skills": ["Customer research", "Product design", "Prototyping"],
        "department": "general",
        "availability": "unavailable",
        "rate": 25,
        "pricing": "hour",
        "published": True,
        "is_mine": False,
        "is_example": True,
    }
