from oliview_core.vector import ChromaVectorClient


def test_chroma_client_preserves_citation_metadata_and_product_filter():
    client = ChromaVectorClient("http://chroma-green:8000")
    requests: list[tuple[str, str, object]] = []

    def fake_request(method, path, payload=None):
        requests.append((method, path, payload))
        if path.endswith("/collections"):
            return [{"id": "collection-id", "name": "oliview_review_sentences_v2"}]
        return {
            "ids": [["42"]],
            "documents": [["커버력이 좋아요"]],
            "metadatas": [
                [
                    {
                        "source_review_id": 7,
                        "review_id": 7,
                        "product_id": 2,
                    }
                ]
            ],
        }

    client._request = fake_request  # type: ignore[method-assign]
    result = client.query([0.1, 0.2], product_id=2, limit=1)

    assert result[0]["source_review_id"] == 7
    assert result[0]["product_id"] == 2
    assert result[0]["text"] == "커버력이 좋아요"
    assert requests[-1][2]["where"] == {"product_id": 2}
