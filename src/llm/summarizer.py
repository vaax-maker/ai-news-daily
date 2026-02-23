# EXPERIMENTAL: This module is superseded by src/generators/llm.py which implements
# the full fallback chain (OpenAI → Grok → Gemini). This file is kept for reference only
# and is NOT used in the main pipeline.
import os
import openai
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

class Summarizer:
    def __init__(self):
        openai.api_key = os.getenv('OPENAI_API_KEY')
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o')
    
    def summarize(self, content: str, title: str) -> Dict[str, any]:
        """Generate summary, bullets, and keywords from content."""
        
        prompt = f"""You are a content analyzer. Analyze the following content and provide:
1. A brief summary (2-3 sentences, Korean)
2. 3-5 bullet points capturing key information (Korean, each under 50 chars)
3. 5-10 keywords (Korean or English, single words)

Content Title: {title}
Content: {content[:3000]}

Respond in JSON format:
{{
    "summary": "summary text",
    "bullets": ["bullet1", "bullet2", "bullet3"],
    "keywords": ["keyword1", "keyword2"]
}}"""
        
        response = openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful content analyzer."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        
        # Ensure bullets are under 400 chars total
        total = sum(len(b) for b in result['bullets'])
        if total >= 400:
            result['bullets'] = result['bullets'][:3]
        
        return result
    
    def generate_html_summary(self, content: str, title: str) -> str:
        """Generate HTML-ready summary for Bento Grid."""
        result = self.summarize(content, title)
        
        # Add context about being AI-generated
        result['summary'] += ' [AI 요약]'
        
        return result
