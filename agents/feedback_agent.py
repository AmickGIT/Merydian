"""
Feedback Agent - Converts natural language user input into structured events.
Uses Google Gemini to parse free-form text and extract meaningful events.
"""
import logging
import json
from typing import Optional

from .config import Config
from .llm_client import get_llm_client
from .schemas import FeedbackEvent, EventType, ConfidenceLevel

logger = logging.getLogger(__name__)


class FeedbackAgent:
    """
    Agent responsible for parsing user feedback into structured events.
    This is the ONLY place where free-form language enters the system.
    """
    
    def __init__(self):
        """Initialize the Feedback Agent with Gemini API."""
        try:
            Config.validate()
        except ValueError as e:
            logger.warning(f"Config validation failed: {e}")
            logger.warning("Using demo mode with mock responses")
            self.demo_mode = True
            self.model = None
            return
            
        self.client = get_llm_client()
        self.model_name = Config.GROQ_MODEL
        self.demo_mode = False
        logger.info(f"FeedbackAgent initialized with model: {Config.GROQ_MODEL}")
    
    def parse(self, user_input: str, context: Optional[dict] = None) -> FeedbackEvent:
        """
        Parse user input into a structured event.
        
        Args:
            user_input: Natural language text from the user
            context: Optional context (family_id, current_day, etc.)
        
        Returns:
            FeedbackEvent with structured data
        """
        logger.info(f"Parsing user input: '{user_input}'")
        
        if self.demo_mode:
            return self._demo_parse(user_input, context)
        
        try:
            prompt = self._build_prompt(user_input, context)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
            )
            response_text = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                # Find the actual JSON content
                lines = response_text.split("\n")
                json_lines = [line for line in lines if not line.startswith("```")]
                response_text = "\n".join(json_lines).strip()
            
            # Parse the JSON
            parsed_data = json.loads(response_text)
            
            # Add raw input
            parsed_data["raw_input"] = user_input
            
            # Strictly enforce the explicit family_id from the context if the user selected one
            if context and context.get("family_id"):
                parsed_data["family_id"] = context["family_id"]
            
            # Validate and construct FeedbackEvent
            event = FeedbackEvent(**parsed_data)
            logger.info(f"Successfully parsed event: {event.event_type}")
            
            return event
            
        except Exception as e:
            logger.error(f"Error parsing user input: {e}")
            # Return a fallback event
            return FeedbackEvent(
                event_type=EventType.UNKNOWN,
                confidence=ConfidenceLevel.LOW,
                raw_input=user_input,
                metadata={"error": str(e)}
            )
    
    def _build_prompt(self, user_input: str, context: Optional[dict]) -> str:
        """Build the prompt for Gemini API."""
        
        context_str = ""
        if context:
            context_str = f"\n\nContext information: {json.dumps(context, indent=2)}"
        
        prompt = f"""You are a travel itinerary feedback parser. Your job is to convert natural language user feedback into structured JSON events.

User Input: "{user_input}"{context_str}

Extract the following information and return ONLY valid JSON (no markdown, no explanation):

{{
  "event_type": "MUST_VISIT_ADDED" | "NEVER_VISIT_ADDED" | "POI_RATING" | "DAY_RATING" | "DELAY_REPORTED" | "TRANSPORT_ISSUE" | "UNKNOWN",
  "family_id": "FAM_A" | "FAM_B" | "FAM_C" | null,
  "poi_id": "LOC_XXX" or null if not identifiable,
  "poi_name": "Name of the place" or null,
  "rating": 0-10 number or null,
  "day": integer or null,
  "transport_mode": "BUS" | "METRO" | "AUTO" | "CAB" | null,
  "disruption_from_poi": "POI name or LOC_XXX" | null,
  "disruption_to_poi": "POI name or LOC_XXX" | null,
  "confidence": "HIGH" | "MEDIUM" | "LOW"
}}

Event Type Guidelines:
- MUST_VISIT_ADDED: User expresses strong desire to visit a place, uses words like "must", "definitely want", "loved it"
- NEVER_VISIT_ADDED: User wants to exclude/avoid a place, uses words like "skip", "avoid", "don't want"
- POI_RATING: User rates a specific location
- DAY_RATING: User rates their experience for a day
- DELAY_REPORTED: User mentions being late or delayed
- TRANSPORT_ISSUE: User mentions transport problems
  * Global disruption: "METRO is shut down", "All buses unavailable" → set transport_mode only
  * Route-specific disruption: "METRO from India Gate to Lotus Temple is closed" → set transport_mode, disruption_from_poi, disruption_to_poi
  * Extract POI names or IDs if specific route mentioned
- UNKNOWN: Cannot determine intent

Return ONLY the JSON object, nothing else."""
        
        return prompt
    
    def _demo_parse(self, user_input: str, context: Optional[dict]) -> FeedbackEvent:
        """Simple demo parsing using keyword matching (fallback when no API key)."""
        
        user_lower = user_input.lower()
        
        # Simple keyword-based parsing
        if any(word in user_lower for word in ["must", "definitely", "loved", "want to visit"]):
            event_type = EventType.MUST_VISIT_ADDED
            confidence = ConfidenceLevel.HIGH
        elif any(word in user_lower for word in ["skip", "avoid", "don't want", "never", "not interested"]):
            event_type = EventType.NEVER_VISIT_ADDED
            confidence = ConfidenceLevel.HIGH
        elif "rating" in user_lower or "rate" in user_lower or any(str(i) + "/10" in user_lower for i in range(11)) or any("out of 10" in user_lower for i in range(11)):
            if "day" in user_lower or "today" in user_lower:
                event_type = EventType.DAY_RATING
            else:
                event_type = EventType.POI_RATING
            confidence = ConfidenceLevel.MEDIUM
        elif "delay" in user_lower or "late" in user_lower or "running" in user_lower:
            event_type = EventType.DELAY_REPORTED
            confidence = ConfidenceLevel.MEDIUM
        elif "metro" in user_lower or "bus" in user_lower or "transport" in user_lower or "auto" in user_lower or "cab" in user_lower:
            event_type = EventType.TRANSPORT_ISSUE
            confidence = ConfidenceLevel.HIGH
            # Extract transport mode
            transport_mode = None
            if "metro" in user_lower:
                transport_mode = "METRO"
            elif "bus" in user_lower:
                transport_mode = "BUS"
            elif "auto" in user_lower:
                transport_mode = "AUTO"
            elif "cab" in user_lower:
                transport_mode = "CAB"
            
            return FeedbackEvent(
                event_type=event_type,
                confidence=confidence,
                raw_input=user_input,
                family_id=context.get("family_id") if context else None,
                transport_mode=transport_mode,
                disruption_from_poi=context.get("from_poi") if context else None,
                disruption_to_poi=context.get("to_poi") if context else None,
                metadata={"demo_mode": True}
            )
        else:
            event_type = EventType.UNKNOWN
            confidence = ConfidenceLevel.LOW
        
        return FeedbackEvent(
            event_type=event_type,
            confidence=confidence,
            raw_input=user_input,
            family_id=context.get("family_id") if context else None,
            metadata={"demo_mode": True}
        )


# Test function for standalone execution
if __name__ == "__main__":
    agent = FeedbackAgent()
    
    # Test cases
    test_inputs = [
        "We loved Akshardham, we definitely want to visit it tomorrow.",
        "Please skip the Red Fort, we're not interested.",
        "I'd rate today a 9 out of 10!",
        "The Lotus Temple was amazing, 10/10",
        "We're running 30 minutes late due to traffic"
    ]
    
    print("=" * 80)
    print("FEEDBACK AGENT TEST")
    print("=" * 80)
    
    for test_input in test_inputs:
        print(f"\nInput: {test_input}")
        event = agent.parse(test_input)
        print(f"Event Type: {event.event_type}")
        print(f"Confidence: {event.confidence}")
        print(f"Full Event: {event.model_dump_json(indent=2)}")
        print("-" * 80)
