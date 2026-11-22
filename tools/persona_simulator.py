"""Persona simulator: drives synthetic user interactions strictly through the public API."""
import argparse
import asyncio
import random

import httpx


async def simulate_user_session(
    client: httpx.AsyncClient,
    api_base: str,
    token: str,
    susceptibility: float,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    inbox_resp = await client.get(f"{api_base}/me/inbox", headers=headers)
    if inbox_resp.status_code != 200:
        return {"status": "inbox_error", "code": inbox_resp.status_code}

    inbox = inbox_resp.json()
    actions_taken = 0
    for item in inbox:
        sim_id = item["simulation_id"]
        await client.post(
            f"{api_base}/events",
            headers=headers,
            json={"simulation_id": sim_id, "type": "opened", "is_synthetic": True},
        )
        roll = random.random()
        if roll < susceptibility:
            action = "submitted" if random.random() < 0.4 else "clicked"
        else:
            action = "reported"
        await client.post(
            f"{api_base}/events",
            headers=headers,
            json={"simulation_id": sim_id, "type": action, "is_synthetic": True},
        )
        actions_taken += 1

    return {"status": "ok", "actions_taken": actions_taken}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate synthetic persona interactions via public API")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--tokens", nargs="+", required=True, help="Bearer JWTs for synthetic test users")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=30.0) as client:
        async def _run(tok: str):
            async with sem:
                return await simulate_user_session(client, args.api_base.rstrip("/"), tok, susceptibility=random.uniform(0.2, 0.7))

        results = await asyncio.gather(*[_run(t) for t in args.tokens])
        print(f"Completed {len(results)} persona runs:", results)


if __name__ == "__main__":
    asyncio.run(main())
