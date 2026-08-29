import uuid
from typing import Dict, Optional

class KVCacheManager:
    def __init__(self, engine):
        self.engine = engine
        self._states: Dict[str, bytes] = {}

    def create_state(self, prefix_text: str) -> str:
        state_id = str(uuid.uuid4())
        
        self.engine.generate(prefix_text, max_tokens=1)
        state_bytes = self.engine.save_state()
        
        self._states[state_id] = state_bytes
        return state_id

    def load_state(self, state_id: str) -> bool:
        state_bytes = self._states.get(state_id)
        if not state_bytes:
            return False
            
        self.engine.load_state(state_bytes)
        return True

    def clear_state(self, state_id: str) -> None:
        if state_id in self._states:
            del self._states[state_id]