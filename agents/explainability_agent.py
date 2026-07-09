"""
Explainability Agent - Converts decision payloads into human-readable summaries.
Uses Google Gemini to generate natural language explanations.
"""
import logging
import json
from typing import Dict, Any, List

from .config import Config
from .llm_client import get_llm_client
from .schemas import AgentExplanation

logger = logging.getLogger(__name__)


class ExplainabilityAgent:
    """
    Agent responsible for generating human-readable explanations.
    Processes decision payloads from the explainability pipeline.
    """
    
    def __init__(self):
        """Initialize the Explainability Agent with Gemini API."""
        try:
            Config.validate()
        except ValueError as e:
            logger.warning(f"Config validation failed: {e}")
            logger.warning("Using demo mode with simple templates")
            self.demo_mode = True
            self.model = None
            return
            
        self.client = get_llm_client()
        self.model_name = Config.GROQ_MODEL
        self.demo_mode = False
        logger.info(f"ExplainabilityAgent initialized with model: {Config.GROQ_MODEL}")
    
    def explain(self, payload: Dict[str, Any]) -> AgentExplanation:
        """
        Generate a human-readable explanation from a decision payload.
        
        Args:
            payload: Decision payload from the explainability pipeline
        
        Returns:
            AgentExplanation with summary text
        """
        logger.info("Generating explanation from payload...")
        
        if self.demo_mode:
            return self._demo_explain(payload)
        
        try:
            prompt = self._build_prompt(payload)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
            )
            summary = response.choices[0].message.content.strip()
            
            return AgentExplanation(
                summary=summary,
                payload_source=payload
            )
            
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return AgentExplanation(
                summary=f"Error generating explanation: {str(e)}",
                payload_source=payload
            )
    
    def explain_batch(self, payloads: List[Dict[str, Any]]) -> List[AgentExplanation]:
        """
        Generate explanations for multiple payloads.
        
        Args:
            payloads: List of decision payloads
        
        Returns:
            List of AgentExplanations
        """
        return [self.explain(payload) for payload in payloads]
    
    def _build_prompt(self, payload: Dict[str, Any]) -> str:
        """Build the prompt for Groq API based on audience."""
        audience = payload.get("audience", "FAMILY")
        
        if audience == "TRAVEL_AGENT":
            return self._build_agent_prompt(payload)
        else:
            return self._build_family_prompt(payload)

    def _build_family_prompt(self, payload: Dict[str, Any]) -> str:
        """Build a persuasive, warm prompt for families."""
        payload_str = json.dumps(payload, indent=2)
        
        prompt = f"""You are a helpful and persuasive travel assistant. Your goal is to explain itinerary changes to a family in a way that feels personal and exciting.

Context:
{payload_str}

**Key Guidelines:**
1. **Tone:** Warm, enthusiastic, and personal. Use "we" to refer to the optimization system.
2. **Interest Alignment:** Emphasize that changes were made because "we identified you like this place" or it matches their interests.
3. **Cost Framing:** 
   - If there is an extra cost, frame it softly e.g., "for an extra cost of only X".
   - If there are savings, highlight them as "saving you X".
   - Do NOT mention "transport costs" separately unless it's a major saving.
4. **Hide Technical Metrics:** Do NOT mention "satisfaction gain", "score", or "lambda". Instead say "it's a great fit" or "you'll love it".
5. **Format:** Keep it conversational. Avoid bullet points unless listing multiple distinct changes.

**Causal Tag Translations (Use these to explain the 'WHY' persuasively):**
- INTEREST_VECTOR_DOMINANCE -> "Matches your interests perfectly"
- SHARED_ANCHOR_REQUIRED -> "Great for the whole group to spend time together"
- OPTIMIZER_SELECTED -> "Highly recommended for your trip based on your preferences"
- OPTIMIZER_TRADEOFF -> "A smart choice that fits perfectly into your schedule"
- TRANSPORT_ROUTING_OPTIMIZATION -> "Optimized for the smoothest travel experience"
- BUS_UNAVAILABLE -> "Since bus services are currently unavailable"
- METRO_UNAVAILABLE -> "Due to the metro strike"
- AUTO_UNAVAILABLE -> "Since auto options are limited right now"
- CAB_FALLBACK_UNAVAILABLE -> "Due to cab unavailability"
- TRANSPORT_DISRUPTED -> "To avoid travel disruptions"
- ROUTE_REROUTED / ROUTE_OPTIMIZED -> "We found a better route for you"
- LOW_INTEREST_DROPPED -> "We found other places you might enjoy more"
- OBJECTIVE_DOMINATED -> "We prioritized options that give you the best value and experience"
- HISTORY_BAN -> "Already visited this place before, so we focused on new experiences"

Generate a short, engaging explanation for the changes in the payload. Focus on the 'WHY' and the 'VALUE'."""
        return prompt

    def _build_agent_prompt(self, payload: Dict[str, Any]) -> str:
        """Build an analytical, metric-heavy prompt for travel agents."""
        payload_str = json.dumps(payload, indent=2)
        
        prompt = f"""You are an explainability agent for a travel optimization system. Provide a professional, analytical report for a Travel Agent.

Decision Payload:
{payload_str}

**Guidelines:**
1. **Tone:** Professional, objective, concise.
2. **Metrics:** Explicitly mention Financial Deltas (Net Cost) and Satisfaction Deltas.
3. **Structure:** Group by Family if necessary, but focus on the aggregate impact.
4. **Causal Tags:** Use the technical definitions provided below.

**Technical Tag Definitions:**
- INTEREST_VECTOR_DOMINANCE: Strong interest match (>1.2)
- SHARED_ANCHOR_REQUIRED: Critical for group coordination
- OPTIMIZER_SELECTED: Selected by optimizer (score 0.8-1.2)
- OPTIMIZER_TRADEOFF: Selected for logistical efficiency despite low interest
- TRANSPORT_ROUTING_OPTIMIZATION: Route/POI selected due to transport changes
- BUS/METRO/AUTO/CAB_UNAVAILABLE: Transport mode unavailability
- TRANSPORT_DISRUPTED: Original mode disrupted
- ROUTE_REROUTED: Found alternative mode
- ROUTE_OPTIMIZED: Route efficiency improvement
- LOW_INTEREST_DROPPED: Removed due to low relevance (<0.8)
- OBJECTIVE_DOMINATED: Removed due to cost/time constraints > value
- HISTORY_BAN: Removed due to site restrictions

Generate a structured report summarizing the changes, the reasons (using technical tags), and the net financial/satisfaction impact."""
        return prompt
    
    def _demo_explain(self, payload: Dict[str, Any]) -> AgentExplanation:
        """Simple template-based explanation (fallback when no API key). Handle dual audiences."""
        
        audience = payload.get("audience", "FAMILY")
        user_input = payload.get("user_input", "")
        
        if audience == "TRAVEL_AGENT":
            summary = f"ADMIN REPORT: Processed user request '{user_input}'. "
            fin = payload.get("financial_summary", {})
            summary += f"Net Cost Delta: {fin.get('total_cost_delta', 0)}, Sat Delta: {fin.get('total_satisfaction_delta', 0)}."
            return AgentExplanation(summary=summary, payload_source=payload)
        
        # Family Logic
        changes = payload.get("changes", [])
        if not changes:
            return AgentExplanation(summary="No significant changes made to your itinerary.", payload_source=payload)
        
        # Just grab the first change for the demo summary
        first_change = changes[0]
        poi_name = first_change["poi"]["name"]
        change_type = first_change["change_type"]
        
        reason_map = {
            "POI_ADDED": f"we added {poi_name} to your plan",
            "POI_REMOVED": f"we removed {poi_name} from your plan",
            "TIME_ADJUSTED": f"we adjusted the time for {poi_name}"
        }
        
        action = reason_map.get(change_type, f"we updated {poi_name}")
        summary = f"Based on your request regarding '{user_input}', {action} to ensure a smooth trip."
        
        return AgentExplanation(
            summary=summary,
            payload_source=payload
        )


# Test function for standalone execution
if __name__ == "__main__":
    print("=" * 80)
    print("EXPLAINABILITY AGENT TEST")
    print("=" * 80)
    
    agent = ExplainabilityAgent()
    
    # Test payloads
    test_payloads = [
        {
            "change_type": "visit_added",
            "poi_name": "Akshardham Temple",
            "day": 2,
            "reason": "User expressed strong interest",
            "details": {
                "preference_score": 9.2,
                "confidence": "HIGH"
            }
        },
        {
            "change_type": "visit_removed",
            "poi_name": "Red Fort",
            "day": 1,
            "reason": "User requested to skip",
            "details": {
                "constraint_type": "never_visit"
            }
        },
        {
            "change_type": "time_adjusted",
            "poi_name": "Lotus Temple",
            "day": 3,
            "reason": "Optimized for better routing",
            "details": {
                "old_time": "14:00",
                "new_time": "10:00"
            }
        }
    ]
    
    for i, payload in enumerate(test_payloads, 1):
        print(f"\nTest Case {i}:")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        explanation = agent.explain(payload)
        print(f"\nExplanation: {explanation.summary}")
        print("-" * 80)
