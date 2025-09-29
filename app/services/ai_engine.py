from typing import Dict, Any, List, Optional, Union
from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.schema import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Pinecone
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
import openai
import json
import logging
from datetime import datetime, timezone
from ..config import settings
from ..models.ai_operation import AIOperation
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AIEngine:
    """Core AI engine for the Scrum Master application"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model_name=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.max_tokens,
            openai_api_key=settings.openai_api_key
        )
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.openai_api_key)
        self.vector_store = None
        self._initialize_vector_store()
    
    def _initialize_vector_store(self):
        """Initialize vector database connection"""
        # Skip vector store initialization if not configured
        if not settings.vector_db_provider or not settings.pinecone_api_key:
            logger.info("Vector database not configured - skipping initialization")
            return

        if settings.vector_db_provider == "pinecone":
            try:
                import pinecone
                pinecone.init(
                    api_key=settings.pinecone_api_key,
                    environment=settings.pinecone_environment
                )
                self.vector_store = Pinecone.from_existing_index(
                    index_name=settings.pinecone_index_name,
                    embedding=self.embeddings
                )
                logger.info("Pinecone vector store initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize vector store: {e}")
                self.vector_store = None
    
    async def generate_response(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        operation_type: str = "general",
        team_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate AI response with logging and context"""
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Retrieve relevant context if available
            if context and self.vector_store:
                context_docs = await self._retrieve_context(prompt, context)
                enhanced_prompt = self._enhance_prompt_with_context(prompt, context_docs)
            else:
                enhanced_prompt = prompt
            
            # Generate response
            messages = [
                SystemMessage(content=self._get_system_prompt(operation_type)),
                HumanMessage(content=enhanced_prompt)
            ]
            
            response = await self.llm.agenerate([messages])
            result = response.generations[0][0].text
            
            # Calculate metrics
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            tokens_used = self._estimate_tokens(enhanced_prompt + result)
            cost = self._estimate_cost(tokens_used)
            
            # Log the operation
            await self._log_ai_operation(
                operation_type=operation_type,
                input_data={"prompt": prompt, "context": context},
                output_data={"response": result},
                tokens_used=tokens_used,
                cost_usd=cost,
                duration_seconds=duration,
                team_id=team_id,
                user_id=user_id
            )
            
            return {
                "response": result,
                "tokens_used": tokens_used,
                "cost_usd": cost,
                "duration_seconds": duration,
                "confidence_score": self._calculate_confidence(result)
            }
            
        except Exception as e:
            logger.error(f"AI generation error: {str(e)}")
            raise
    
    async def _retrieve_context(self, query: str, context_filters: Dict[str, Any]) -> List[str]:
        """Retrieve relevant context from vector database"""
        if not self.vector_store:
            return []
        
        try:
            docs = await self.vector_store.asimilarity_search(
                query, 
                k=5,
                filter=context_filters
            )
            return [doc.page_content for doc in docs]
        except Exception as e:
            logger.warning(f"Context retrieval failed: {str(e)}")
            return []
    
    def _enhance_prompt_with_context(self, prompt: str, context_docs: List[str]) -> str:
        """Enhance prompt with retrieved context"""
        if not context_docs:
            return prompt
        
        context_section = "\n".join([f"Context {i+1}: {doc}" for i, doc in enumerate(context_docs)])
        return f"""Relevant Context:
{context_section}

Current Request:
{prompt}

Please provide a response that takes into account the relevant context above."""
    
    def _get_system_prompt(self, operation_type: str) -> str:
        """Get appropriate system prompt based on operation type"""
        
        base_prompt = """You are an AI Scrum Master assistant. You help agile teams with:
- Daily standup coordination and summaries
- Sprint planning and capacity analysis  
- Backlog grooming and prioritization
- Process improvements and risk identification

Always be objective, constructive, and focused on team productivity. Provide actionable insights."""

        specific_prompts = {
            "standup_summary": base_prompt + """

For standup summaries:
- Focus on completed work, planned work, and blockers
- Identify risks and dependencies
- Keep summaries concise but informative
- Format in clear bullet points or structured text""",
            
            "backlog_analysis": base_prompt + """

For backlog analysis:
- Assess story clarity and completeness
- Identify potential duplicates or conflicts
- Suggest acceptance criteria when missing
- Estimate complexity based on description""",
            
            "sprint_planning": base_prompt + """

For sprint planning:
- Consider team capacity and velocity
- Identify dependencies and risks
- Suggest realistic sprint goals
- Flag overcommitment or underutilization""",
            
            "retrospective": base_prompt + """

For retrospectives:
- Identify patterns in team feedback
- Suggest actionable improvements
- Categorize issues by theme
- Maintain positive, constructive tone"""
        }
        
        return specific_prompts.get(operation_type, base_prompt)
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for cost calculation"""
        # Rough estimation: ~4 characters per token
        return len(text) // 4
    
    def _estimate_cost(self, tokens: int) -> float:
        """Estimate cost based on token usage"""
        # GPT-4 pricing (approximate)
        cost_per_1k_tokens = 0.03
        return (tokens / 1000) * cost_per_1k_tokens
    
    def _calculate_confidence(self, response: str) -> float:
        """Calculate confidence score for response quality"""
        # Simple heuristic - can be improved with more sophisticated methods
        if not response or len(response.strip()) < 10:
            return 0.1
        
        # Check for completeness indicators
        confidence = 0.5
        
        if any(word in response.lower() for word in ["summary", "completed", "planned", "blocker"]):
            confidence += 0.2
        
        if len(response.split()) > 20:  # Reasonable length
            confidence += 0.2
        
        if response.count('\n') > 0 or response.count('-') > 0:  # Structure
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    async def _log_ai_operation(self, **kwargs):
        """Log AI operation for monitoring and improvement"""
        # This would integrate with your database session
        # For now, just log to application logs
        logger.info(f"AI Operation: {kwargs}")
