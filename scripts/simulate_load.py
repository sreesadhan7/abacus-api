from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class DemoResult:
    expected_total: int
    observed_total: int


async def post_number(client: httpx.AsyncClient, base_url: str, number: int) -> None:
    response = await client.post(f"{base_url}/abacus/number", json={"number": number})
    response.raise_for_status()


async def reset_total(client: httpx.AsyncClient, base_url: str) -> None:
    response = await client.delete(f"{base_url}/abacus/sum")
    response.raise_for_status()


async def fetch_total(client: httpx.AsyncClient, base_url: str) -> int:
    response = await client.get(f"{base_url}/abacus/sum")
    response.raise_for_status()
    return int(response.json()["total"])


async def run_demo(endpoints: list[str], requests: int, concurrency: int, number: int) -> DemoResult:
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(10.0, connect=5.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        await reset_total(client, endpoints[0])

        semaphore = asyncio.Semaphore(concurrency)

        async def worker(index: int) -> None:
            async with semaphore:
                endpoint = endpoints[index % len(endpoints)]
                await post_number(client, endpoint, number)

        await asyncio.gather(*(worker(index) for index in range(requests)))
        observed_total = await fetch_total(client, endpoints[0])

    return DemoResult(expected_total=requests * number, observed_total=observed_total)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a two-node consistency and load demo.")
    parser.add_argument(
        "--endpoints",
        nargs="+",
        default=["http://127.0.0.1:8000", "http://127.0.0.1:8001"],
        help="Base URLs for the running API nodes.",
    )
    parser.add_argument("--requests", type=int, default=100, help="Number of POST requests to send.")
    parser.add_argument("--concurrency", type=int, default=20, help="Maximum in-flight requests.")
    parser.add_argument("--number", type=int, default=1, help="Value added by each POST.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    result = await run_demo(args.endpoints, args.requests, args.concurrency, args.number)

    print(f"Expected total: {result.expected_total}")
    print(f"Observed total: {result.observed_total}")

    if result.expected_total != result.observed_total:
        print("Consistency check failed.")
        return 1

    print("Consistency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
