import asyncio
import math
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings

try:
    import chromadb  # type: ignore
    from chromadb.config import Settings as ChromaSettings  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    chromadb = None
    ChromaSettings = None


class LocalRagService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.openai = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self._index_rows: list[dict[str, Any]] = []
        self._collection = None

        if chromadb is not None:
            client = chromadb.PersistentClient(
                path=self.settings.chroma_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(name=self.settings.kb_collection)

    async def initialize(self) -> None:
        docs = self._load_knowledge_docs()
        if not docs:
            self._index_rows = []
            return

        embeddings = await self._embed_texts([d["content"] for d in docs])

        if self._collection is not None:
            Path(self.settings.chroma_dir).mkdir(parents=True, exist_ok=True)
            count = await asyncio.to_thread(self._collection.count)
            if count == 0:
                await asyncio.to_thread(
                    self._collection.add,
                    ids=[d["id"] for d in docs],
                    embeddings=embeddings,
                    metadatas=[d["metadata"] for d in docs],
                    documents=[d["content"] for d in docs],
                )
            return

        self._index_rows = []
        for idx, doc in enumerate(docs):
            self._index_rows.append(
                {
                    "id": doc["id"],
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "embedding": embeddings[idx],
                }
            )

    async def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        query_embedding = (await self._embed_texts([query]))[0]

        if self._collection is not None:
            result = await asyncio.to_thread(
                self._collection.query,
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            documents = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            rows = []
            for index, doc in enumerate(documents):
                rows.append(
                    {
                        "content": doc,
                        "metadata": metadatas[index] if index < len(metadatas) else {},
                        "distance": distances[index] if index < len(distances) else None,
                    }
                )
            return rows

        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in self._index_rows:
            sim = self._cosine_similarity(query_embedding, row["embedding"])
            ranked.append((sim, row))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        output: list[dict[str, Any]] = []
        for sim, row in ranked[:top_k]:
            output.append(
                {
                    "content": row["content"],
                    "metadata": row.get("metadata", {}),
                    "distance": 1 - sim,
                }
            )
        return output

    def _load_knowledge_docs(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        kb_dir = self.settings.kb_path
        kb_dir.mkdir(parents=True, exist_ok=True)

        for file in kb_dir.glob("*.md"):
            raw_text = file.read_text(encoding="utf-8")
            chunks = self._chunk_text(raw_text, chunk_size=1200, overlap=200)
            for idx, chunk in enumerate(chunks):
                docs.append(
                    {
                        "id": f"{file.stem}-{idx}",
                        "content": chunk,
                        "metadata": {"source": file.name, "chunk": idx},
                    }
                )
        return docs

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = await self.openai.embeddings.create(model=self.settings.openai_embedding_model, input=texts)
        return [item.embedding for item in response.data]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for i in range(len(a)):
            dot += a[i] * b[i]
            norm_a += a[i] * a[i]
            norm_b += b[i] * b[i]

        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))

    @staticmethod
    def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = max(end - overlap, 0)
        return chunks


rag_service = LocalRagService()
