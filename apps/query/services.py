from sqlalchemy.orm import Session
from google.genai import types

from apps.core.ai_models import get_genai_client
from apps.core.prompts import CLASSIFY_QUERY_PROMPT
from apps.core.config import settings
from apps.core.global_utils import logOperation
from .schemas import TokenUsage

class QueryService:
    client = get_genai_client() # class variable to hold the shared GenAI client

    def __init__(self, db: Session):
        self.db = db
        # self.repo = QueryRepository(db)

    @logOperation
    def get_token_usage(self, llm_response) -> TokenUsage:
        """
        Extracts token usage information from the LLM response.
        """
        usage         = llm_response.usage_metadata
        input_tokens  = usage.prompt_token_count
        output_tokens = usage.candidates_token_count
        total_tokens  = usage.total_token_count

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens
        )

    @logOperation
    def classify_query(self, user_query: str) -> tuple[str, TokenUsage]:
        """
        Classifies the user query and returns the classification along with token usage.
        """
        # Use the LLM to classify the query
        classification_prompt = CLASSIFY_QUERY_PROMPT + f"\n{user_query}"
        llm_response = self.client.models.generate_content(
            model=settings.llm_name,
            contents=classification_prompt,
            config=types.GenerateContentConfig(
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
            ),
        )
        classification = llm_response.text.strip().lower()

        # Post-processing to ensure the classification is one of the expected categories
        if classification not in ["general", "insurance", "other"]:
            classification = "other"  # Default to 'other' if classification is unclear

        token_usage = self.get_token_usage(llm_response)
        return classification, token_usage

    @logOperation
    def process_general_query(self, user_query: str):
        """
        Processes general queries that are not specific to the insurance domain.
        """
        llm_response = self.client.models.generate_content(
            model=settings.llm_name,
            contents=user_query,
            config=types.GenerateContentConfig(
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
            ),
        )

        answer = llm_response.text.strip()
        token_usage = self.get_token_usage(llm_response)
        return answer, token_usage
    
    @logOperation
    def process_insurance_query(self, user_query: str, user_id: str):
        """
        Processes insurance-domain specific queries.
        """
        return "placeholder", TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)  # Placeholder implementation
    
    @logOperation
    def process_query(self, user_query: str, user_id: str) -> tuple[str, TokenUsage]:
        # Classify the query using the LLM
        classification, classification_token_usage = self.classify_query(user_query)
        print(f"Query classified as: {classification} with token usage: {classification_token_usage}")

        # Process the query based on its classification
        if classification == "general":
            answer, token_usage = self.process_general_query(user_query)
        elif classification == "insurance":
            answer, token_usage = self.process_insurance_query(user_query, user_id)
        else:
            answer = "This is something I am unable to answer at the moment. Please contact support for further assistance."
            token_usage = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)

        print(f"Answer generated: {answer} with token usage: {token_usage}")

        # Combine token usage from classification and query processing
        final_token_usage = TokenUsage(
            input_tokens=classification_token_usage.input_tokens + token_usage.input_tokens,
            output_tokens=classification_token_usage.output_tokens + token_usage.output_tokens,
            total_tokens=classification_token_usage.total_tokens + token_usage.total_tokens
        )

        print(f"Final token usage after combining classification and processing: {final_token_usage}")

        return answer, final_token_usage