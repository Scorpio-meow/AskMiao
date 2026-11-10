from typing import List, Dict, Any, Optional, AsyncGenerator
import logging
from datetime import datetime
from .types import Document, RecursiveCharacterTextSplitter
from .retrievers.hybrid import HybridRetriever
from .tools import ResearchToolRegistry
from .agent import ResearchAgent
from app.core.llm_client import LlmEndpoint
logger = logging.getLogger(__name__)
class RAGPipeline:
    def __init__(
        self,
        retriever: HybridRetriever,
        chunk_size: int = 300,
        chunk_overlap: int = 100,
    ):
        self.retriever = retriever
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tool_registry = ResearchToolRegistry(retriever=self.retriever)
        self.agent = ResearchAgent(tool_registry=self.tool_registry)
        self.text_splitter = self._create_text_splitter()
    def _create_text_splitter(self) -> RecursiveCharacterTextSplitter:
        separators = [
            "\n\n---\n\n",
            "\n\n",
            "\n",
            "。", "！", "？", "；", "：", "，",
            ". ", "! ", "? ", ", ",
            " ", ""
        ]
        return RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=separators,
        )
    def split_documents(self, raw_documents: List[Document]) -> List[Document]:
        chunks: List[Document] = []
        for doc in raw_documents:
            if doc.metadata.get("preserve_whole", False):
                pieces = [doc.page_content]
            else:
                pieces = self.text_splitter.split_text(doc.page_content)
            for i, piece in enumerate(pieces):
                chunks.append(Document(
                    page_content=piece,
                    metadata={
                        **doc.metadata,
                        "chunk_index": i,
                        "original_doc_id": doc.metadata.get("document_id"),
                        "added_timestamp": datetime.now().isoformat()
                    }
                ))
        return chunks
    async def generate_response_stream(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
        *,
        endpoint: LlmEndpoint,
        model_name: str,
        reasoning_effort: Optional[str] = "medium",
        attachments: Optional[List[Any]] = None,
        approval_user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        mode: str,
        instructions: str,
        allow_web: bool
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async for event_item in self.agent.stream_research(
            query=query,
            endpoint=endpoint,
            model_name=model_name,
            conversation_history=conversation_history,
            reasoning_effort=reasoning_effort,
            attachments=attachments,
            approval_user_id=approval_user_id,
            conversation_id=conversation_id,
            mode=mode,
            instructions=instructions,
            allow_web=allow_web
        ):
            yield event_item