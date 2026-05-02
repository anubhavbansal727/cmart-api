"""Pinecone namespace isolation test.

Verifies that two accounts cannot see each other's vectors.
Uses random vectors — no OpenAI call needed, no cost.

Usage:
    uv run python scripts/test_namespace_isolation.py

Requires PINECONE_API_KEY and PINECONE_INDEX_NAME in .env
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cmart.config import get_settings
from cmart.services.vector_store.pinecone import PineconeVectorStoreClient


def random_vector(dim: int) -> list[float]:
    return [random.uniform(-1, 1) for _ in range(dim)]


async def run_test() -> None:
    settings = get_settings()
    client = PineconeVectorStoreClient()
    dim = settings.pinecone_vector_dim

    ns_a = str(uuid.uuid4())  # simulates account A's namespace
    ns_b = str(uuid.uuid4())  # simulates account B's namespace

    vec_a = random_vector(dim)
    vec_b = random_vector(dim)

    print(f"\nNamespace A: {ns_a}")
    print(f"Namespace B: {ns_b}")
    print("\n--- Upserting vectors ---")

    await client.upsert(
        namespace=ns_a,
        vectors=[{"id": "doc_a_chunk_0", "values": vec_a, "metadata": {"doc_id": "doc_a", "account_id": ns_a, "content": "Account A secret"}}],
    )
    print("  [ok] Upserted doc_a into namespace A")

    await client.upsert(
        namespace=ns_b,
        vectors=[{"id": "doc_b_chunk_0", "values": vec_b, "metadata": {"doc_id": "doc_b", "account_id": ns_b, "content": "Account B secret"}}],
    )
    print("  [ok] Upserted doc_b into namespace B")

    print("\n--- Running isolation checks ---")
    passed = True

    # Check 1: Namespace A query returns doc_a
    results_a = await client.query(namespace=ns_a, vector=vec_a, top_k=5)
    ids_a = [r["id"] for r in results_a]
    if "doc_a_chunk_0" in ids_a and "doc_b_chunk_0" not in ids_a:
        print("  [PASS] Namespace A sees doc_a and NOT doc_b")
    else:
        print(f"  [FAIL] Namespace A results: {ids_a}")
        passed = False

    # Check 2: Namespace B query returns doc_b
    results_b = await client.query(namespace=ns_b, vector=vec_b, top_k=5)
    ids_b = [r["id"] for r in results_b]
    if "doc_b_chunk_0" in ids_b and "doc_a_chunk_0" not in ids_b:
        print("  [PASS] Namespace B sees doc_b and NOT doc_a")
    else:
        print(f"  [FAIL] Namespace B results: {ids_b}")
        passed = False

    # Check 3: Cross-query — query namespace A using B's vector
    cross_results = await client.query(namespace=ns_a, vector=vec_b, top_k=5)
    cross_ids = [r["id"] for r in cross_results]
    if "doc_b_chunk_0" not in cross_ids:
        print("  [PASS] Querying namespace A with B's vector does NOT return doc_b")
    else:
        print(f"  [FAIL] Cross-query leaked doc_b into namespace A: {cross_ids}")
        passed = False

    # Check 4: Query namespace B using A's vector
    cross_results_2 = await client.query(namespace=ns_b, vector=vec_a, top_k=5)
    cross_ids_2 = [r["id"] for r in cross_results_2]
    if "doc_a_chunk_0" not in cross_ids_2:
        print("  [PASS] Querying namespace B with A's vector does NOT return doc_a")
    else:
        print(f"  [FAIL] Cross-query leaked doc_a into namespace B: {cross_ids_2}")
        passed = False

    print("\n--- Cleaning up test vectors ---")
    await client.delete(namespace=ns_a, doc_id="doc_a")
    await client.delete(namespace=ns_b, doc_id="doc_b")
    print("  [ok] Test vectors deleted")

    print("\n" + ("=" * 40))
    if passed:
        print("  RESULT: ALL CHECKS PASSED — namespace isolation is working correctly")
    else:
        print("  RESULT: FAILED — namespace isolation is BROKEN, do not proceed to retrieval build")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    asyncio.run(run_test())
