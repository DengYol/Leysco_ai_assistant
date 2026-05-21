"""Training and onboarding intent handlers"""

from typing import Dict, Any
import logging
from ..base_handler import BaseHandler
from app.ai_engine.training_actions import TrainingActions

logger = logging.getLogger(__name__)


class TrainingHandler(BaseHandler):
    """Handler for training and onboarding intents"""
    
    def __init__(self, action_router):
        super().__init__(action_router)
        self.training_actions = TrainingActions()
    
    def handle_module(self, entities: dict, message: str, language: str) -> dict:
        """Handle training module request."""
        result = self.training_actions.handle_training_module(entities, message, language)
        return {"message": result, "data": []}
    
    def handle_video(self, entities: dict, message: str, language: str) -> dict:
        """Handle training video request."""
        result = self.training_actions.handle_training_video(entities, message, language)
        return {"message": result, "data": []}
    
    def handle_guide(self, entities: dict, message: str, language: str) -> dict:
        """Handle training guide request."""
        result = self.training_actions.handle_training_guide(entities, message, language)
        return {"message": result, "data": []}
    
    def handle_faq(self, entities: dict, message: str, language: str) -> dict:
        """Handle training FAQ request."""
        result = self.training_actions.handle_training_faq(entities, message, language)
        return {"message": result, "data": []}
    
    def handle_glossary(self, entities: dict, message: str, language: str) -> dict:
        """Handle training glossary request."""
        result = self.training_actions.handle_training_glossary(entities, message, language)
        return {"message": result, "data": []}
    
    def handle_webinar(self, entities: dict, message: str, language: str) -> dict:
        """Handle training webinar request."""
        result = self.training_actions.handle_training_webinar(entities, message, language)
        return {"message": result, "data": []}
    
    def handle_onboarding(self, language: str) -> str:
        """Handle onboarding welcome."""
        return self.training_actions.handle_onboarding_welcome(language)