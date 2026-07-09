"""
Agent Controller - Orchestrates all agents in a deterministic flow.
This is the conductor that coordinates the entire agent system.
"""
import logging
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path

from .config import Config
from .schemas import FeedbackEvent, PolicyDecision, ActionType
from .feedback_agent import FeedbackAgent
from .decision_policy_agent import DecisionPolicyAgent
from .optimizer_agent import OptimizerAgent
from .explainability_agent import ExplainabilityAgent

logger = logging.getLogger(__name__)


class AgentController:
    """
    Main orchestration layer for the agent system.
    Implements the core flow: User Input → Event → Decision → Action → Explanation
    """
    
    def __init__(self):
        """Initialize the agent controller and all agents."""
        logger.info("Initializing AgentController...")
        
        self.feedback_agent = FeedbackAgent()
        self.policy_agent = DecisionPolicyAgent()
        self.optimizer_agent = OptimizerAgent()
        self.explainability_agent = ExplainabilityAgent()
        
        logger.info("AgentController initialized successfully")
    
    def process_user_input(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process user input through the complete agent pipeline.
        
        Args:
            user_input: Natural language text from user
            context: Optional context (family_id, current_day, etc.)
        
        Returns:
            Dictionary with results from each stage:
            - event: Parsed FeedbackEvent
            - decision: PolicyDecision
            - optimizer_output: Paths to generated files (if optimizer ran)
            - explanations: List of explanations (if available)
        """
        logger.info("=" * 80)
        logger.info(f"Processing user input: '{user_input}'")
        logger.info("=" * 80)
        
        # Stage 1: Parse user input into structured event
        logger.info("\n[STAGE 1] Feedback Agent - Parsing user input...")
        event = self.feedback_agent.parse(user_input, context)
        logger.info(f"✓ Event generated: {event.event_type} (confidence: {event.confidence})")
        
        # Stage 2: Decide what action to take
        logger.info("\n[STAGE 2] Decision/Policy Agent - Making decision...")
        decision = self.policy_agent.decide(event)
        logger.info(f"✓ Decision: {decision.action}")
        logger.info(f"  Reason: {decision.reason}")
        
        result = {
            "event": event,
            "decision": decision,
            "optimizer_output": None,
            "explanations": []
        }
        
        # Stage 3: Execute action based on decision
        if decision.action == ActionType.RUN_OPTIMIZER:
            logger.info("\n[STAGE 3] Optimizer Agent - Running optimizer...")
            
            # Prepare preferences from event
            preferences = {
                "event_type": event.event_type,
                "family_id": event.family_id,
                "poi_name": event.poi_name,
                "poi_id": event.poi_id,
                # Transport disruption fields (FIX: pass these to optimizer)
                "transport_mode": getattr(event, 'transport_mode', None),
                "disruption_from_poi": getattr(event, 'disruption_from_poi', None),
                "disruption_to_poi": getattr(event, 'disruption_to_poi', None)
            }
            
            # Get previous optimized solution for comparison (NOT base_itinerary)
            # base_itinerary = skeleton (stays same), previous_solution = last optimized result
            previous_solution_path = None
            if context and context.get("previous_solution"):
                previous_solution_path = Path(context["previous_solution"])
            
            # Get output directory from context
            output_dir_path = None
            if context and context.get("output_dir"):
                output_dir_path = Path(context["output_dir"])
            
            current_prefs_path = None
            if context and context.get("current_preferences_path"):
                current_prefs_path = Path(context["current_preferences_path"])
            
            # Get current_day for partial optimization (freeze past days)
            start_day = 0
            if context and context.get("current_day") is not None:
                start_day = int(context["current_day"])
            
            # Run optimizer with event data and previous solution for comparison
            optimizer_output = self.optimizer_agent.run(
                preferences=preferences,
                base_solution_path=previous_solution_path,  # For diff comparison
                output_dir=output_dir_path,  # Where to save outputs
                current_prefs_path=current_prefs_path,  # Current cumulative preferences
                user_input=user_input,  # Original user text for context
                start_day=start_day  # Freeze days before this index
            )
            result["optimizer_output"] = optimizer_output
            logger.info(f"✓ Optimizer completed")
            
            # Stage 4: Generate explanations
            # NOTE: helping reduce API calls for demo mode, as run_demo.py handles this explicitly
            # If enabled here AND in run_demo.py, we get double the API usage.
            # logger.info("\n[STAGE 4] Explainability Agent - Generating explanations...")
            
            # if optimizer_output.get("llm_payloads") and \
            #    optimizer_output["llm_payloads"].exists():
                
            #     logger.info(f"Loading LLM payloads from: {optimizer_output['llm_payloads']}")
                
            #     with open(optimizer_output["llm_payloads"], 'r') as f:
            #         payload_data = json.load(f)
                
            #     # Handle new dict structure (families list + travel_agent dict)
            #     # We want to explain all family payloads AND the travel agent payload
            #     payloads_to_explain = []
                
            #     if isinstance(payload_data, dict):
            #         # Add family payloads
            #         if "families" in payload_data:
            #             payloads_to_explain.extend(payload_data["families"])
            #         # Add travel agent payload
            #         if "travel_agent" in payload_data:
            #             payloads_to_explain.append(payload_data["travel_agent"])
            #     elif isinstance(payload_data, list):
            #         # Fallback for old list format
            #         payloads_to_explain = payload_data
                
            #     logger.info(f"Loaded {len(payloads_to_explain)} payload(s) from optimizer")
                
            #     if payloads_to_explain:
            #         # Generate explanations using the actual payloads
            #         explanations = self.explainability_agent.explain_batch(payloads_to_explain)
            #         result["explanations"] = explanations
                    
            #         logger.info(f"✓ Generated {len(explanations)} explanations")
                    
            #         # Display explanations
            #         for i, exp in enumerate(explanations, 1):
            #             logger.info(f"  {i}. {exp.summary}")
            #     else:
            #         logger.info("No payloads to explain found.")
            # else:
            #     logger.warning("No llm_payloads.json file found from optimizer")
        
        elif decision.action == ActionType.UPDATE_PREFERENCES_ONLY:
            logger.info("\n[STAGE 3] Updating preferences (optimizer not run)")
            
            # Construct preferences payload for soft constraints
            preferences = {
                "event_type": event.event_type,
                "family_id": event.family_id,
                "poi_name": event.poi_name,
                "poi_id": event.poi_id,
                "rating": getattr(event, 'rating', None)
            }
            
            output_dir_path = Path(context["output_dir"]) if (context and context.get("output_dir")) else None
            current_prefs_path = Path(context["current_preferences_path"]) if (context and context.get("current_preferences_path")) else None
            
            # Delegate to OptimizerAgent's lightweight method
            pref_output = self.optimizer_agent.update_preferences_only(
                preferences=preferences,
                output_dir=output_dir_path,
                current_prefs_path=current_prefs_path
            )
            result["preference_output"] = pref_output
            logger.info("  Preference update acknowledged and saved.")
        
        else:
            logger.info(f"\n[STAGE 3] No action required")
            logger.info(f"  {decision.reason}")
        
        logger.info("\n" + "=" * 80)
        logger.info("Pipeline completed successfully")
        logger.info("=" * 80 + "\n")
        
        return result
    
    def _extract_payloads_from_diffs(self, diffs: Dict[str, Any]) -> list:
        """
        Extract explanation payloads from enriched diffs.
        This is a simplified version for demo purposes.
        
        Args:
            diffs: Enriched diffs data
        
        Returns:
            List of payload dictionaries
        """
        payloads = []
        
        # For demo, create a sample payload
        # In production, this would parse the actual diffs structure
        payloads.append({
            "change_type": "itinerary_optimized",
            "poi_name": "Sample Location",
            "day": 1,
            "reason": "Preferences updated based on user feedback"
        })
        
        return payloads
    
    def run_demo_scenarios(self):
        """Run a set of demo scenarios to showcase the system."""
        print("\n" + "=" * 80)
        print("AGENT SYSTEM DEMO - RUNNING SCENARIOS")
        print("=" * 80 + "\n")
        
        scenarios = [
            {
                "input": "We loved Akshardham, we definitely want to visit it tomorrow.",
                "context": {"family_id": "FAM_B"},
                "description": "User adds a must-visit location"
            },
            {
                "input": "Please skip the Red Fort, we're not interested.",
                "context": {"family_id": "FAM_A"},
                "description": "User excludes a location"
            },
            {
                "input": "The Metro is on strike tomorrow.",
                "context": {
                    "family_id": "FAM_C", 
                    "transport_mode": "METRO",    # Mode being disrupted
                    "disruption_from_poi": "LOC_001",
                    "disruption_to_poi": "LOC_002"
                },
                "description": "Transport Disruption (Metro Strike)"
            }
        ]
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n{'#' * 80}")
            print(f"SCENARIO {i}: {scenario['description']}")
            print(f"{'#' * 80}\n")
            print(f"User: \"{scenario['input']}\"\n")
            
            result = self.process_user_input(
                scenario["input"],
                scenario["context"]
            )
            
            # Display summary
            print("\n--- SUMMARY ---")
            print(f"Event Type: {result['event'].event_type}")
            print(f"Decision: {result['decision'].action}")
            print(f"Optimizer Run: {'Yes' if result['optimizer_output'] else 'No'}")
            if result['explanations']:
                print(f"Explanations Generated: {len(result['explanations'])}")
            
            # Don't wait after the last scenario
            if i < len(scenarios):
                print("\n⏱️  Waiting 35 seconds before next scenario (free tier rate limiting)...")
                time.sleep(35)  # Ensure we stay within 2 RPM globally
                print("Ready for next scenario!\n")
        
        print("\n" + "=" * 80)
        print("DEMO COMPLETED")
        print("=" * 80 + "\n")


# Main execution
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("VOYAGEUR AGENT SYSTEM - CONTROLLER TEST")
    print("=" * 80)
    
    controller = AgentController()
    
    # Run demo scenarios
    controller.run_demo_scenarios()
