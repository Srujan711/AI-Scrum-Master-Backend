from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from ..services.ai_engine import AIEngine
from ..config import settings

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all AI agents"""
    
    def __init__(self, ai_engine: AIEngine, tools: List[BaseTool] = None):
        self.ai_engine = ai_engine
        self.tools = tools or []
        self.agent_executor = None
        self._initialize_agent()
    
    @abstractmethod
    def get_agent_prompt(self) -> str:
        """Return the specific prompt template for this agent"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the agent's main functionality"""
        pass
    
    def _initialize_agent(self):
        """Initialize the LangChain agent with tools"""
        if self.tools:
            from langchain.prompts import ChatPromptTemplate
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.get_agent_prompt()),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ])
            
            agent = create_openai_functions_agent(
                llm=self.ai_engine.llm,
                tools=self.tools,
                prompt=prompt
            )
            
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                max_iterations=settings.max_agent_iterations,
                verbose=True
            )
    
    async def run_with_tools(self, input_text: str) -> Dict[str, Any]:
        """Run agent with tool execution capability"""
        if not self.agent_executor:
            raise ValueError("Agent not properly initialized with tools")
        
        try:
            result = await self.agent_executor.ainvoke({"input": input_text})
            return {
                "output": result["output"],
                "intermediate_steps": result.get("intermediate_steps", [])
            }
        except Exception as e:
            logger.error(f"Agent execution error: {str(e)}")
            raise