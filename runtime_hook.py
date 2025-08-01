# Create runtime_hook.py:
import asyncio
import nest_asyncio
nest_asyncio.apply()
if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())