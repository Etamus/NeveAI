from neveai.retrieval.vector.main import VectorDBBase
from neveai.retrieval.vector.dbs.chroma import ChromaClient


class Vector:

    @staticmethod
    def get_vector(vector_type: str = "chroma") -> VectorDBBase:
        """Return NeveAI's local vector database implementation."""
        if vector_type.lower() != "chroma":
            raise ValueError("NeveAI supports only the local Chroma vector database")
        return ChromaClient()


VECTOR_DB_CLIENT = Vector.get_vector()
