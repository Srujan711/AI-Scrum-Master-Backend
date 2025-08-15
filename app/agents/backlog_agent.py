from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime, timezone
from ..services.ai_engine import AIEngine
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BacklogAgent(BaseAgent):
    """Agent responsible for backlog grooming and analysis"""
    
    def __init__(self, ai_engine: AIEngine):
        super().__init__(ai_engine)
    
    def get_agent_prompt(self) -> str:
        return """You are a Backlog Grooming Agent. Your responsibilities include:

1. Analyzing backlog items for clarity and completeness
2. Identifying potential duplicates or conflicts
3. Suggesting improvements to user stories
4. Estimating complexity and effort
5. Recommending prioritization based on value vs effort

When analyzing stories:
- Check for clear acceptance criteria
- Identify missing or vague requirements  
- Suggest story splitting for large items
- Flag potential technical dependencies
- Assess business value indicators

Provide specific, actionable recommendations."""
    
    async def execute(self, team_id: int, backlog_item_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """Execute backlog grooming workflow"""
        
        logger.info(f"Running backlog grooming for team {team_id}")
        
        try:
            # Step 1: Get backlog items to analyze
            backlog_items = await self._get_backlog_items(team_id, backlog_item_ids)
            
            # Step 2: Analyze each item
            analysis_results = []
            for item in backlog_items:
                analysis = await self._analyze_backlog_item(item)
                analysis_results.append(analysis)
            
            # Step 3: Find duplicates and conflicts
            duplicates = await self._find_duplicates(backlog_items)
            
            # Step 4: Generate prioritization suggestions
            prioritization = await self._suggest_prioritization(backlog_items, analysis_results)
            
            result = {
                "team_id": team_id,
                "items_analyzed": len(backlog_items),
                "analysis_results": analysis_results,
                "duplicate_groups": duplicates,
                "prioritization_suggestions": prioritization,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Backlog grooming error: {str(e)}")
            raise
    
    async def _get_backlog_items(self, team_id: int, item_ids: Optional[List[int]]) -> List[Dict[str, Any]]:
        """Retrieve backlog items for analysis"""
        # This would integrate with your database and Jira
        # For now, return placeholder data
        return [
            {
                "id": 1,
                "title": "User Login Feature",
                "description": "As a user, I want to log in to access my account",
                "story_points": None,
                "priority": "high",
                "status": "to_do"
            }
        ]
    
    async def _analyze_backlog_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze individual backlog item"""
        
        prompt = f"""
        Analyze this backlog item and provide structured feedback:
        
        Title: {item.get('title')}
        Description: {item.get('description')}
        Current Priority: {item.get('priority')}
        Story Points: {item.get('story_points')}
        
        Please analyze and return JSON with this structure:
        {{
            "clarity_score": 0.8,
            "missing_elements": ["acceptance criteria", "mockups"],
            "complexity_estimate": "medium",
            "suggested_improvements": ["Add specific acceptance criteria", "Define edge cases"],
            "potential_risks": ["Unclear authentication requirements"],
            "estimated_effort": "5-8 story points",
            "business_value": "high"
        }}
        """
        
        response = await self.ai_engine.generate_response(
            prompt=prompt,
            operation_type="backlog_analysis"
        )
        
        try:
            analysis = json.loads(response["response"])
            analysis["item_id"] = item["id"]
            return analysis
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse analysis for item {item['id']}")
            return {"item_id": item["id"], "error": "Analysis failed"}
    
    async def _find_duplicates(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find potential duplicate backlog items using embeddings"""
        
        if len(items) < 2:
            return []
        
        # Use vector similarity to find duplicates
        duplicates = []
        
        for i, item1 in enumerate(items):
            for j, item2 in enumerate(items[i+1:], i+1):
                similarity = await self._calculate_similarity(item1, item2)
                if similarity > 0.8:  # High similarity threshold
                    duplicates.append({
                        "item1_id": item1["id"],
                        "item2_id": item2["id"],
                        "similarity_score": similarity,
                        "reason": "High content similarity detected"
                    })
        
        return duplicates
    
    async def _calculate_similarity(self, item1: Dict[str, Any], item2: Dict[str, Any]) -> float:
        """Calculate semantic similarity between two items"""
        
        text1 = f"{item1.get('title', '')} {item1.get('description', '')}"
        text2 = f"{item2.get('title', '')} {item2.get('description', '')}"
        
        if not self.ai_engine.vector_store:
            return 0.0
        
        try:
            # Create embeddings
            embedding1 = await self.ai_engine.embeddings.aembed_query(text1)
            embedding2 = await self.ai_engine.embeddings.aembed_query(text2)
            
            # Calculate cosine similarity
            import numpy as np
            similarity = np.dot(embedding1, embedding2) / (
                np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
            )
            
            return float(similarity)
            
        except Exception as e:
            logger.warning(f"Similarity calculation failed: {str(e)}")
            return 0.0
    
    async def _suggest_prioritization(self, items: List[Dict[str, Any]], analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate prioritization suggestions"""
        
        # Combine items with their analyses
        enriched_items = []
        for item in items:
            analysis = next((a for a in analyses if a.get("item_id") == item["id"]), {})
            enriched_items.append({**item, "analysis": analysis})
        
        prompt = f"""
        Based on these backlog items and their analyses, suggest optimal prioritization:
        
        {json.dumps(enriched_items, indent=2)}
        
        Return a JSON array with prioritization suggestions:
        [
            {{
                "item_id": 1,
                "suggested_priority": "high",
                "reasoning": "High business value with clear requirements",
                "recommended_action": "Move to next sprint",
                "dependencies": []
            }}
        ]
        
        Consider: business value, effort estimation, risk factors, and dependencies.
        """
        
        response = await self.ai_engine.generate_response(
            prompt=prompt,
            operation_type="backlog_analysis"
        )
        
        try:
            return json.loads(response["response"])
        except json.JSONDecodeError:
            logger.warning("Failed to parse prioritization suggestions")
            return []