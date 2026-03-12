from pydantic import BaseModel
from typing import Optional, List

class IntentResult(BaseModel):
    intent: str
    confidence: float

class AIResponse(BaseModel):
    message: str
    data: Optional[List[dict]] = None
