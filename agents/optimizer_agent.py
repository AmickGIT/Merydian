"""
Optimizer Agent - Integrates with ml_or.itinerary_optimizer.ItineraryOptimizer
Handles re-optimization based on user preference changes.
"""
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from .config import Config
from .poi_mapper import load_locations_map, get_poi_id
from .preference_builder import load_base_preferences, apply_event_to_preferences, save_preferences
from .transport_graph_modifier import create_disrupted_transport_graph

logger = logging.getLogger(__name__)


class OptimizerAgent:
    """
    Agent responsible for running the optimizer and explainability pipeline.
    Integrates with ml_or.itinerary_optimizer.ItineraryOptimizer.
    """
    
    def __init__(self):
        """Initialize the Optimizer Agent."""
        self.ml_or_dir = Config.ML_OR_DIR
        self.test_data_dir = Config.TEST_DATA_DIR
        self.agents_dir = Config.AGENTS_DIR
        self.output_dir = self.agents_dir / "tests"
        self.output_dir.mkdir(exist_ok=True)
        
        # Data paths
        self.data_dir = self.ml_or_dir / "data"
        self.locations_path = self.data_dir / "locations.json"
        self.hotels_path = self.data_dir / "hotels.json"
        self.transport_path = self.data_dir / "transport_graph.json"
        self.base_itinerary_path = self.data_dir / "base_itinerary_clustered.json"
        self.base_prefs_path = self.data_dir / "family_preferences_3fam_strict.json"
        
        # Load locations map (merge locations and hotels)
        self.locations_map = load_locations_map(self.locations_path)
        self.locations_map.update(load_locations_map(self.hotels_path))
        
        logger.info("OptimizerAgent initialized with real optimizer")
    
    def _apply_transport_disruption(
        self,
        transport_file: str,
        disruption_mode: str,
        from_poi: Optional[str] = None,
        to_poi: Optional[str] = None
    ) -> str:
        """Create temporary transport graph with disruptions."""
        import json
        from pathlib import Path
        
        with open(transport_file, 'r') as f:
            graph = json.load(f)
        
        disrupted_count = 0
        
        if from_poi and to_poi:
            for edge in graph:
                if edge.get("mode") == disruption_mode:
                    if (edge["from"] == from_poi and edge["to"] == to_poi) or \
                       (edge["from"] == to_poi and edge["to"] == from_poi):
                        edge["available"] = False
                        disrupted_count += 1
            logger.info(f"Applied route-specific disruption: {disruption_mode} from {from_poi} to {to_poi} ({disrupted_count} edges)")
        else:
            for edge in graph:
                if edge.get("mode") == disruption_mode:
                    edge["available"] = False
                    disrupted_count += 1
            logger.info(f"Applied global disruption: All {disruption_mode} routes ({disrupted_count} edges)")
        
        temp_file = Path(transport_file).parent / f"transport_disrupted_{disruption_mode}.json"
        with open(temp_file, 'w') as f:
            json.dump(graph, f, indent=2)
        
        logger.info(f"Temporary transport graph saved: {temp_file}")
        return str(temp_file)
        
    def update_preferences_only(
        self,
        preferences: Dict[str, Any],
        output_dir: Optional[Path] = None,
        current_prefs_path: Optional[Path] = None
    ) -> Dict[str, Path]:
        """Update and save preferences without running the heavy optimizer."""
        logger.info("Running lightweight preference update...")
        
        run_dir = Path(output_dir) if output_dir else (self.output_dir / "temp")
        run_dir.mkdir(parents=True, exist_ok=True)
        
        prefs_file = current_prefs_path if current_prefs_path else self.base_prefs_path
        base_prefs = load_base_preferences(prefs_file)
        
        poi_id = None
        if preferences and preferences.get("poi_name"):
            poi_id = get_poi_id(preferences["poi_name"], self.locations_map)
            
        updated_prefs = apply_event_to_preferences(
            preferences=base_prefs.copy(),
            event=preferences or {},
            poi_id=poi_id,
            locations_map=self.locations_map
        )
        
        updated_prefs_path = run_dir / "family_preferences_updated.json"
        save_preferences(updated_prefs, updated_prefs_path)
        
        return {"family_preferences": updated_prefs_path}
    
    def run(
        self,
        preferences: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        base_solution_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        current_prefs_path: Optional[Path] = None,
        session_manager: Optional[Any] = None,  # TripSessionManager
        trip_id: Optional[str] = None,
        current_solution: Optional[Dict] = None,  # Existing trip solution for re-opt
        user_input: str = "",  # User's natural language request
        start_day: int = 0  # 0-indexed day to start optimization from (freeze prior days)
    ) -> Dict[str, Path]:
        """
        Run the optimizer with updated preferences/constraints.
        
        Args:
            preferences: FeedbackEvent dictionary with user preference change
            constraints: Updated constraints (currently unused)
            base_solution_path: Path to baseline solution for comparison (optional)
            output_dir: Directory to save outputs (optional, defaults to agents/tests/run_*)
            user_input: Original user text for explainability context
        
        Returns:
            Dictionary with paths to generated files
        """
        from datetime import datetime
        
        logger.info("Running optimizer with real ItineraryOptimizer...")
        
        # Determine output directory
        context_start_day = start_day  # Freeze days before this index
        if output_dir:
            run_dir = Path(output_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Default: Create timestamped output directory in agents/tests
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = self.output_dir / f"run_{timestamp}"
            run_dir.mkdir(exist_ok=True)
        
        logger.info(f"Saving results to: {run_dir}")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 1: Build Updated Family Preferences
        # ═══════════════════════════════════════════════════════════════
        
        # Load current preferences (cumulative) or fall back to base
        prefs_file = current_prefs_path if current_prefs_path else self.base_prefs_path
        logger.info(f"Loading preferences from: {prefs_file}")
        base_prefs = load_base_preferences(prefs_file)
        
        # Ensure all families have at least empty preferences
        all_families = ["FAM_A", "FAM_B", "FAM_C"]
        for fam_id in all_families:
            if fam_id not in base_prefs:
                base_prefs[fam_id] = {
                    "must_visit_locations": [],
                    "never_visit_locations": [],
                    "interests": []
                }
        
        # Map POI name to ID
        poi_id = None
        if preferences and preferences.get("poi_name"):
            poi_id = get_poi_id(preferences["poi_name"], self.locations_map)
            if not poi_id:
                logger.error(f"Could not find POI ID for: {preferences['poi_name']}")
        
        # Apply event to preferences
        updated_prefs = apply_event_to_preferences(
            preferences=base_prefs.copy(),
            event=preferences or {},
            poi_id=poi_id,
            locations_map=self.locations_map
        )
        
        # Save updated preferences
        updated_prefs_path = run_dir / "family_preferences_updated.json"
        save_preferences(updated_prefs, updated_prefs_path)
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 1.5: GEOGRAPHIC LOOK-AHEAD (NEW!)
        # ═══════════════════════════════════════════════════════════════
        
        target_day = None
        day_constraints = None
        
        event_type = preferences.get('event_type') if preferences else None
        
        if event_type == 'MUST_VISIT_ADDED' and poi_id:
            logger.info("[LOOK-AHEAD] Analyzing candidate days...")
            candidate_days = []
            
            # Case A: Use Session Manager (if available)
            if session_manager and trip_id:
                session = session_manager.get_session(trip_id)
                before_day = preferences.get('before_day')
                if before_day:
                    candidate_days = session.get_candidate_days(
                        constraint="before_day_N",
                        before_day=before_day
                    )
                else:
                    candidate_days = session.get_candidate_days(
                        constraint="current_and_future"
                    )
            # Case B: Standalone / Demo Mode (Fallback)
            else:
                # Assume standard 3-day trip or derive from base itinerary
                num_days = 3
                with open(self.base_itinerary_path, 'r') as f:
                    base_data = json.load(f)
                    if 'days' in base_data:
                        num_days = len(base_data['days'])
                candidate_days = list(range(num_days))
                logger.info(f"  [Fallback] No session manager, considering all {num_days} days")
            
            logger.info(f"  Candidate days: {[d+1 for d in candidate_days]}")
            
            # Geographic look-ahead if candidates exist
            if len(candidate_days) > 0:
                # Load base itinerary
                with open(self.base_itinerary_path, 'r') as f:
                    base_itinerary = json.load(f)
                
                # Create temporary optimizer just for look-ahead
                from ml_or.itinerary_optimizer import ItineraryOptimizer
                temp_optimizer = ItineraryOptimizer(
                    locations_file=str(self.locations_path),
                    hotels_file=str(self.hotels_path),
                    transport_file=str(self.transport_path),
                    base_itinerary_file=str(self.base_itinerary_path),
                    family_prefs_file=str(self.base_prefs_path)
                )
                
                # Run geographic look-ahead
                best_day, distance = temp_optimizer.find_best_day_for_poi(
                    poi_id=poi_id,
                    candidate_days=candidate_days,
                    base_itinerary=base_itinerary
                )
                
                logger.info(f"  [✓] Best day: Day {best_day + 1} (avg distance: {distance:.2f} km)")
                target_day = best_day
                
                # Create Constraints to ENFORCE this decision
                # 1. Force Include on Best Day
                # 2. Force Exclude on All Other Candidate Days
                day_constraints = {}
                
                # Force Include
                day_constraints[best_day] = {
                    "force_include": [poi_id],
                    "force_exclude": []
                }
                
                # Force Exclude on others to prevent "greedy theft" by earlier days
                for d in candidate_days:
                    if d != best_day:
                        if d not in day_constraints:
                            day_constraints[d] = {"force_include": [], "force_exclude": []}
                        day_constraints[d]["force_exclude"].append(poi_id)
                
                logger.info(f"  [CONSTRAINT] Enforcing placement on Day {best_day + 1}")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 1.8: Hotel & Skeleton Backbone Optimization
        # ═══════════════════════════════════════════════════════════════
        logger.info("Running HotelSkeletonOptimizer...")
        
        from ml_or.hotel_optimizer import HotelSkeletonOptimizer
        
        # Initialize Hotel Optimizer
        # Uses updated preferences to respect constraints
        hotel_opt = HotelSkeletonOptimizer(
            locations_file=str(self.locations_path),
            hotels_file=str(self.hotels_path),
            base_itinerary_file=str(self.base_itinerary_path),
            family_prefs_file=str(updated_prefs_path)
        )
        
        # Optimize Hotel Backbone
        backbone_file = run_dir / "optimized_backbone.json"
        hotel_opt.optimize(output_file=str(backbone_file))
        
        logger.info(f"Hotel backbone saved to: {backbone_file}")

        # ═══════════════════════════════════════════════════════════════
        # STEP 2: Initialize and Run Optimizer
        # ═══════════════════════════════════════════════════════════════
        
        from ml_or.itinerary_optimizer import ItineraryOptimizer
        from .schemas import EventType
        
        # Apply transport disruption if needed
        transport_file_to_use = str(self.transport_path)
        transport_disruption_active = False
        
        # Fix: Check if event_type string contains TRANSPORT_ISSUE
        event_type_str = str(preferences.get('event_type', '')) if preferences else ''
        if 'TRANSPORT_ISSUE' in event_type_str:
            transport_mode = preferences.get('transport_mode')
            from_poi = preferences.get('disruption_from_poi')
            to_poi = preferences.get('disruption_to_poi')
            
            if transport_mode:
                logger.info(f"Applying transport disruption: {transport_mode}" + 
                          (f" from {from_poi} to {to_poi}" if from_poi and to_poi else " (global)"))
                
                # Use the new utility function
                transport_file_to_use = create_disrupted_transport_graph(
                    transport_graph_path=str(self.transport_path),
                    transport_mode=transport_mode,
                    from_poi=from_poi,
                    to_poi=to_poi,
                    output_dir=str(run_dir) if run_dir else None
                )
                transport_disruption_active = True
                logger.info(f"Using disrupted transport graph: {transport_file_to_use}")
        
        logger.info("Initializing ItineraryOptimizer...")
        optimizer = ItineraryOptimizer(
            locations_file=str(self.locations_path),
            hotels_file=str(self.hotels_path),
            transport_file=transport_file_to_use,
            base_itinerary_file=str(self.base_itinerary_path),
            family_prefs_file=str(updated_prefs_path),
            optimized_backbone_file=str(backbone_file)  # Incorporate Backbone
        )
        
        # Decide: Single-day re-opt or full trip?
        if target_day is not None and current_solution:
            # Single-day re-optimization (faster, preserves completed days)
            logger.info(f"Running single-day re-optimization for Day {target_day + 1}...")
            new_solution = optimizer.reoptimize_from_current_state(
                current_solution=current_solution,
                target_day_index=target_day,
                family_ids=["FAM_A", "FAM_B", "FAM_C"],
                lambda_divergence=0.05,
                day_constraints=day_constraints  # NEW: Enforce look-ahead
            )
        else:
            # Partial Optimization Architecture:
            # 1. Load History (Immutable Past)
            # 2. Optimize Future (Adaptive Future)
            # 3. Stitch Together
            
            logger.info(f"Running partial optimization starting from Day {context_start_day + 1}...")
            
            initial_history = None
            
            # Step 1: Load History from Base Solution
            if context_start_day > 0 and base_solution_path:
                try:
                    with open(base_solution_path, 'r') as f:
                        base_sol = json.load(f)
                    
                    initial_history = {fid: set() for fid in ["FAM_A", "FAM_B", "FAM_C"]}
                    # Extract history for days strictly BEFORE start_day
                    for i in range(context_start_day):
                        if i < len(base_sol.get('days', [])):
                            day_data = base_sol['days'][i]
                            # Handle both 'families' (new format) and 'family_itineraries' (old format if any)
                            families_data = day_data.get('families', {})
                            
                            for fid, fam_data in families_data.items():
                                if fid in initial_history:
                                    for poi in fam_data.get('pois', []):
                                        initial_history[fid].add(poi['location_id'])
                                        
                    logger.info(f"Loaded history for Days 1-{context_start_day} to ensure continuity.")
                except Exception as e:
                    logger.error(f"Failed to load base solution for history: {e}")
                    initial_history = None

            # Step 2: Optimize Future Days
            try:
                new_solution = optimizer.optimize_trip(
                    family_ids=["FAM_A", "FAM_B", "FAM_C"],
                    num_days=3,
                    lambda_divergence=0.05,
                    day_constraints=day_constraints,
                    start_day_index=context_start_day,
                    initial_visited_history=initial_history
                )
            except Exception as e:
                logger.error(f"CRITICAL: optimize_trip failed with exception: {e}", exc_info=True)
                new_solution = {}

            # Step 3: Stitching (Merge History + Future)
            if context_start_day > 0 and base_solution_path and new_solution:
                try:
                    logger.info(f"Stitching: Prepending immutable history (Days 1-{context_start_day}) to new plan...")
                    with open(base_solution_path, 'r') as f:
                        base_sol = json.load(f)
                    
                    preserved_days = []
                    # Extract days strictly before start_day
                    for i in range(context_start_day):
                        if i < len(base_sol.get('days', [])):
                            preserved_days.append(base_sol['days'][i])
                            
                    # Prepend preserved days to new solution
                    new_solution['days'] = preserved_days + new_solution['days']
                    
                    # Recalculate totals
                    new_solution['total_trip_cost'] = sum(d['total_transport_cost'] for d in new_solution['days'])
                    new_solution['total_trip_time_min'] = sum(d['total_transport_time_min'] for d in new_solution['days'])
                    
                    logger.info(f"Stitching complete. Final itinerary has {len(new_solution['days'])} days.")
                    
                except Exception as e:
                    logger.error(f"Failed to stitch partial solution: {e}")
            
            if not new_solution:
                logger.error("Optimizer returned empty solution or failed.")
                return {}
        
        logger.info("Optimization completed successfully")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 3: Load Baseline for Comparison
        # ═══════════════════════════════════════════════════════════════
        
        baseline_solution = None
        if base_solution_path and Path(base_solution_path).exists():
            with open(base_solution_path, 'r') as f:
                baseline_solution = json.load(f)
            logger.info(f"Loaded baseline solution from: {base_solution_path}")
        else:
            # Use demo baseline
            demo_baseline = self.test_data_dir / "optimized_solution.json"
            if demo_baseline.exists():
                with open(demo_baseline, 'r') as f:
                    baseline_solution = json.load(f)
                logger.info("Using demo baseline solution for comparison")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 4: Run Explainability Pipeline
        # ═══════════════════════════════════════════════════════════════
        
        from ml_or.explainability.diff_engine import ItineraryDiffEngine
        from ml_or.explainability.causal_tagger import CausalTagger
        from ml_or.explainability.delta_engine import DeltaEngine
        from ml_or.explainability.payload_builder import ExplanationPayloadBuilder
        
        logger.info("Running explainability pipeline...")
        
        # Initialize decision traces (will be populated later with disruption info)
        decision_traces = optimizer.decision_traces
        
        # Compare solutions
        diff_engine = ItineraryDiffEngine()
        if baseline_solution:
            diffs = diff_engine.compare_optimized_solutions(
                baseline_optimized=baseline_solution,
                new_optimized=new_solution,
                days_to_compare=None,
                decision_traces=decision_traces  # Pass for transport disruption detection
            )
        else:
            # First run - no baseline
            logger.warning("No baseline solution, diffs may be incomplete")
            diffs = {}
        
        # Tag changes with causal reasoning
        tagger = CausalTagger()
        
        # Add disruption info to decision traces if needed
        if transport_disruption_active and preferences:
            # Add active_disruptions to each day's decision trace
            transport_mode = preferences.get('transport_mode')
            for day_idx in range(len(new_solution.get('days', []))):
                if day_idx not in decision_traces:
                    decision_traces[day_idx] = {"candidates": [], "constraints": []}
                
                # Add disruption information
                if "active_disruptions" not in decision_traces[day_idx]:
                    decision_traces[day_idx]["active_disruptions"] = []
                
                decision_traces[day_idx]["active_disruptions"].append({
                    "disruption_id": f"{transport_mode}_DISRUPTION",
                    "affected_modes": [transport_mode],
                    "reason": "USER_REPORTED",
                    "severity": "SEVERE"
                })
        
        tagged_diffs = tagger.tag_changes(diffs, decision_traces)
        
        # Calculate cost/satisfaction deltas
        delta_engine = DeltaEngine()
        enriched_diffs = delta_engine.compute_deltas(
            tagged_diffs,
            decision_traces,
            optimizer.locations,
            baseline_solution=baseline_solution,
            new_solution=new_solution
        )
        
        # Build LLM payloads
        builder = ExplanationPayloadBuilder()
        payloads = builder.build_payloads(
            enriched_diffs,
            optimizer.locations,
            user_input=user_input
        )
        
        logger.info(f"Generated {len(payloads)} explanation payload(s)")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 5: Save All Outputs
        # ═══════════════════════════════════════════════════════════════
        
        # Save optimized solution
        solution_path = run_dir / "optimized_solution.json"
        with open(solution_path, 'w') as f:
            json.dump(new_solution, f, indent=2)
        
        # Save decision traces
        traces_path = run_dir / "decision_traces.json"
        with open(traces_path, 'w') as f:
            json.dump({str(k): v for k, v in decision_traces.items()}, f, indent=2)
        
        # Save enriched diffs
        diffs_path = run_dir / "enriched_diffs.json"
        with open(diffs_path, 'w') as f:
            output = {}
            for fid, day_map in enriched_diffs.items():
                output[fid] = {str(d): changes for d, changes in day_map.items()}
            json.dump(output, f, indent=2)
        
        # Save LLM payloads
        payloads_path = run_dir / "llm_payloads.json"
        with open(payloads_path, 'w') as f:
            json.dump(payloads, f, indent=2)
        
        logger.info("All outputs saved successfully")
        
        return {
            "optimized_solution": solution_path,
            "decision_traces": traces_path,
            "enriched_diffs": diffs_path,
            "llm_payloads": payloads_path,
            "family_preferences": updated_prefs_path  # Source of truth for preferences
        }
    
    def load_solution(self, solution_path: Path) -> Dict[str, Any]:
        """Load an optimized solution from file."""
        try:
            with open(solution_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading solution from {solution_path}: {e}")
            return {}
    
    def _load_base_itinerary(self, base_path: str) -> Optional[Dict]:
        """
        Load the base itinerary for comparison.
        Prioritizes 'solved_base_itinerary.json' (full details) over 'base_itinerary_final.json' (skeleton).
        """
        if not base_path:
            return None
            
        p = Path(base_path)
        
        # Check if a solved version exists in the same directory
        # This is CRITICAL for partial optimization to work correctly with transport history
        solved_path = p.parent / "solved_base_itinerary.json"
        if solved_path.exists():
            logger.info(f"Found solved baseline at {solved_path}. Using this for history/comparison.")
            target_path = solved_path
        else:
            logger.info(f"Using provided baseline at {p}")
            target_path = p
            
        if target_path.exists():
            try:
                with open(target_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load baseline from {target_path}: {e}")
                return None
        return None
    
    def load_decision_traces(self, traces_path: Path) -> Dict[str, Any]:
        """Load decision traces from file."""
        try:
            with open(traces_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading decision traces from {traces_path}: {e}")
            return {}
    
    def load_enriched_diffs(self, diffs_path: Path) -> Dict[str, Any]:
        """Load enriched diffs from file."""
        try:
            with open(diffs_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading enriched diffs from {diffs_path}: {e}")
            return {}


# Test function for standalone execution
if __name__ == "__main__":
    print("=" * 80)
    print("OPTIMIZER AGENT TEST - REAL OPTIMIZER")
    print("=" * 80)
    
    agent = OptimizerAgent()
    
    # Test with a preference change
    print("\nRunning optimizer with MUST_VISIT_ADDED event...")
    test_event = {
        "event_type": "MUST_VISIT_ADDED",
        "poi_name": "Akshardham",
        "family_id": "FAM_B"
    }
    
    result = agent.run(preferences=test_event)
    
    print("\nGenerated files:")
    for key, path in result.items():
        exists = "✓" if path.exists() else "✗"
        print(f"  {exists} {key}: {path}")
    
    print("\n" + "=" * 80)
