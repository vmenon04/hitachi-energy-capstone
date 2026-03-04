"""
System and human prompt constants used in the AI pipeline.
"""

INSIGHTS_SYSTEM = (
    "You are a business intelligence analyst. "
    "Your task is to analyze CSV data and provide actionable insights. "
    "Use the available tools to examine the data thoroughly before providing your analysis."
)

INSIGHTS_HUMAN = (
    "Analyze the provided CSV data and give me 3-5 concise, actionable insights "
    "for a business stakeholder. Use the tools to explore the data first."
)
