from hld_assistant.index.embedder import HashingEmbedder, create_embedder


def test_hashing_embedder_is_deterministic_and_normalised():
    embedder = HashingEmbedder(dim=128)
    first = embedder.embed(["VehicleSpeed signal routing"])[0]
    second = embedder.embed(["VehicleSpeed signal routing"])[0]
    assert first == second
    assert len(first) == 128
    norm = sum(v * v for v in first) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_similar_texts_score_higher_than_unrelated():
    embedder = HashingEmbedder(dim=256)
    query = embedder.embed(["VehicleSpeed signal"])[0]
    related = embedder.embed(["The VehicleSpeed signal is routed via Com"])[0]
    unrelated = embedder.embed(["Diagnostic trouble code storage in NvM"])[0]
    assert _dot(query, related) > _dot(query, unrelated)


def test_create_embedder_forces_hashing(settings):
    embedder = create_embedder(settings)
    assert embedder.name.startswith("hashing")


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))
