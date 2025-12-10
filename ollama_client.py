import aiohttp
import json
from typing import Optional, List

class OllamaClient:
    """Client for interacting with local Ollama instance"""

    def __init__(self, host: str):
        self.host = host
        self.api_url = f"{host}/api"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Create the session when entering async context"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the session when exiting async context"""
        if self.session:
            await self.session.close()
            self.session = None

    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        context: Optional[List] = None):
        """Generate a response from Ollama with streaming support"""
        if not self.session:
            raise RuntimeError("OllamaClient session not initialized. Use async with context manager.")
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True
        }
        
        if system:
            payload["system"] = system
        
        if context:
            payload["context"] = context
        
        try:
            async with self.session.post(f"{self.api_url}/generate", json=payload) as response:
                if response.status == 200:
                    full_response = ""
                    final_context = None
                    
                    # Stream the response line by line
                    async for line in response.content:
                        if line:
                            try:
                                chunk = json.loads(line.decode('utf-8'))
                                token = chunk.get('response', '')
                                full_response += token
                                
                                # Get context from final chunk
                                if chunk.get('done', False):
                                    final_context = chunk.get('context')
                                
                                # Yield each token as it arrives
                                if token:
                                    yield token, False, final_context
                            except json.JSONDecodeError:
                                continue
                    
                    # Signal completion
                    yield '', True, final_context
                else:
                    error_text = await response.text()
                    yield f"Error: Ollama returned status {response.status}: {error_text}", True, None
        except aiohttp.ClientError as e:
            yield f"Error connecting to Ollama: {str(e)}", True, None
    
    async def list_models(self) -> List[str]:
        """Get list of available models"""
        if not self.session:
            raise RuntimeError("OllamaClient session not initialized. Use async with context manager.")
        
        try:
            async with self.session.get(f"{self.api_url}/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    return [model['name'] for model in data.get('models', [])]
                else:
                    return []
        except aiohttp.ClientError:
            return []
    
    async def check_connection(self) -> bool:
        """Check if Ollama is accessible"""
        if not self.session:
            raise RuntimeError("OllamaClient session not initialized. Use async with context manager.")
        
        try:
            async with self.session.get(f"{self.host}") as response:
                return response.status == 200
        except aiohttp.ClientError:
            return False
