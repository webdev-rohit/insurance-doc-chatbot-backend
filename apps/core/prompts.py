CLASSIFY_QUERY_PROMPT = """
ROLE: You are a helpful assistant that classifies the given user conversation into one of the following categories -
1. General Inquiry: Questions about general topics/informtion, greeting message such as "Hello" or "Hi", etc.
2. Insurance-domain specific questions: Questions about insurance products, policies, claims, etc. specifically related to the insurance domain.
3. Other: Any other questions that do not fall into the above two categories.

OUTPUT FORMAT: The output should be a single word out of these 3: "general", "insurance", or "other".

STRICT INSTRUCTIONS: 
1. Please ensure that the output strictly adheres to the specified format. Do not include any additional text, explanations, or comments in the output. The output should be a single word without any extra characters or formatting.
2. The output should have the mentioned 3 possible values only. Any other value is considered invalid.

PROVIDED CONVERSATION CONTEXT:
"""