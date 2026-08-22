import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from mcp_client import ReliabilityMCPClient


def test_mcp_server_lists_and_calls_tools():
    async def exercise_server():
        client = ReliabilityMCPClient()
        await client.start()
        try:
            result = json.loads(await client.calculate_b_life(2.0, 1000.0, 10.0))
            assert result["result"] == 325  # noqa: PLR2004

            result = json.loads(
                await client.call_tool("calculate_mtbf", {"failure_times": [10.0, 20.0]})
            )
            assert result["mtbf"] == 15.0

            result = json.loads(
                await client.search_reliability_knowledge("Weibull shape parameter", 2)
            )
            assert result["matches"]
        finally:
            await client.close()

    asyncio.run(exercise_server())
