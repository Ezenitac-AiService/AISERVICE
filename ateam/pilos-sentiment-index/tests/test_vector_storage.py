import unittest

from unittest.mock import Mock, patch

from pilos.storage.vector_storage import (
    EMBEDDING_DIMENSION,
    load_completed_chunks,
    search_vector_chunks,
)


class VectorStorageVersionFilterTest(unittest.TestCase):
    @patch("pilos.storage.vector_storage.get_vector_collection")
    def test_load_filters_completed_chunks_by_document_version(
        self,
        get_vector_collection,
    ):
        collection = Mock()
        collection.get.return_value = {
            "ids": ["chunk-1"],
            "documents": ["service document"],
            "metadatas": [
                {
                    "source_label": "service guide",
                    "document_version": "1.0",
                    "chunk_index": 0,
                    "status": "completed",
                }
            ],
        }
        get_vector_collection.return_value = collection

        result = load_completed_chunks(
            document_version="1.0",
        )

        self.assertEqual(result[0]["chunk_id"], "chunk-1")
        self.assertEqual(
            collection.get.call_args.kwargs["where"],
            {
                "$and": [
                    {"status": {"$eq": "completed"}},
                    {
                        "document_version": {
                            "$eq": "1.0",
                        }
                    },
                ]
            },
        )

    @patch("pilos.storage.vector_storage.get_vector_collection")
    def test_vector_search_filters_by_same_document_version(
        self,
        get_vector_collection,
    ):
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "ids": [["chunk-1"]],
            "documents": [["service document"]],
            "metadatas": [[
                {
                    "source_label": "service guide",
                    "document_version": "1.0",
                    "chunk_index": 0,
                    "status": "completed",
                }
            ]],
            "distances": [[0.1]],
        }
        get_vector_collection.return_value = collection

        result = search_vector_chunks(
            query_embedding=[0.0] * EMBEDDING_DIMENSION,
            document_version="1.0",
        )

        self.assertEqual(result[0]["chunk_id"], "chunk-1")
        self.assertEqual(
            collection.query.call_args.kwargs["where"],
            {
                "$and": [
                    {"status": {"$eq": "completed"}},
                    {
                        "document_version": {
                            "$eq": "1.0",
                        }
                    },
                ]
            },
        )

    @patch("pilos.storage.vector_storage.get_vector_collection")
    def test_blank_document_version_is_rejected(
        self,
        get_vector_collection,
    ):
        collection = Mock()
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        get_vector_collection.return_value = collection

        with self.assertRaises(ValueError):
            load_completed_chunks(document_version="   ")


if __name__ == "__main__":
    unittest.main()
