import asyncio
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from dotenv import dotenv_values
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ARCHIVE = ROOT / 'gallery_guest_1784132581189.zip'
ENV = dotenv_values('.env')
PROMPT = (
    'We have time for exactly one more RAISE experiment. Using your knowledge '
    'from all the existing runs, try to one-shot the optimal parameters. '
    'Choose exactly one formulation to target a 65-degree contact angle. '
    'Return ethanol (v/v%), SDS (w/v%), and a brief rationale. '
    'Do not conduct the experiment or call any tools.'
)

async def main():
    with ZipFile(ARCHIVE) as archive:
        record = json.loads(archive.read('gallery_guest_1784132581189/conversation_019f6697_full.json'))
    history_raw = record['main_messages'][:54]
    history_json = json.dumps(history_raw, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    history = ModelMessagesTypeAdapter.validate_python(history_raw)
    provider = OpenAIProvider(base_url=ENV['LITELLM_OPENAI_BASE_URL'], api_key=ENV['LITELLM_API_KEY'])
    agent = Agent(OpenAIResponsesModel('gpt-5.5', provider=provider),
                  instructions='Choose one candidate from the provided history. Do not run experiments or call tools.')
    metadata = {'model': 'gpt-5.5', 'provider_api': 'OpenAI Responses via LiteLLM',
                'history': 'main_messages[0:54]', 'history_sha256': hashlib.sha256(history_json.encode()).hexdigest(),
                'prompt': PROMPT, 'tools': [], 'repetitions_planned': 10}
    metadata_path = OUT / 'metadata.json'
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text())
        for key in ('model', 'provider_api', 'history', 'history_sha256', 'prompt', 'tools'):
            if previous[key] != metadata[key]:
                raise ValueError(f'Cannot mix runs: {key} differs from existing metadata')
    (OUT / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n')
    for i in range(1, 11):
        path = OUT / f'run-{i:02}.json'
        if path.exists():
            continue
        result = await agent.run(PROMPT, message_history=history)
        data = {'run': i, 'output': result.output, 'usage': result.usage.opentelemetry_attributes()}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps(data, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
