"""
VECTOR STORE SERVICE
====================
RAG (Retrieval-Augmented Generation) for A.D.A
- Loads learning data from database/learning_data/
- Embeds text using HuggingFace sentence-transformers
- Stores in FAISS vector database
- Retrieves relevant context for LLM queries
"""

import os
import logging
from pathlib import Path
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from config_ada import (
    LEARNING_DATA_DIR, 
    VECTOR_STORE_DIR, 
    EMBEDDING_MODEL, 
    CHUNK_SIZE, 
    CHUNK_OVERLAP
)

logger = logging.getLogger("ADA")

class VectorStoreService:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'}
        )
        self.vectorstore = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
    
    def create_vector_store(self):
        """Load learning data and create FAISS index"""
        logger.info("[VECTOR STORE] Creating vector store...")
        
        documents = []
        
        # Load all .txt files from learning_data directory
        if LEARNING_DATA_DIR.exists():
            for txt_file in LEARNING_DATA_DIR.glob("*.txt"):
                try:
                    loader = TextLoader(str(txt_file), encoding='utf-8')
                    docs = loader.load()
                    # Add source metadata
                    for doc in docs:
                        doc.metadata = {"source": f"learning_data/{txt_file.name}"}
                    documents.extend(docs)
                    logger.info(f"[VECTOR STORE] Loaded: {txt_file.name}")
                except Exception as e:
                    logger.warning(f"[VECTOR STORE] Failed to load {txt_file.name}: {e}")
        
        if not documents:
            logger.info("[VECTOR STORE] No learning data found, creating empty store")
            # Create empty vector store
            self.vectorstore = FAISS.from_texts(
                ["No learning data available"],
                self.embeddings
            )
        else:
            # Split documents into chunks
            texts = self.text_splitter.split_documents(documents)
            logger.info(f"[VECTOR STORE] Split into {len(texts)} chunks")
            
            # Create FAISS index
            self.vectorstore = FAISS.from_documents(texts, self.embeddings)
            logger.info("[VECTOR STORE] FAISS index created")
        
        # Save to disk
        self.save_vector_store()
        logger.info("[VECTOR STORE] Vector store ready")
    
    def save_vector_store(self):
        """Save vector store to disk"""
        if self.vectorstore and VECTOR_STORE_DIR:
            self.vectorstore.save_local(str(VECTOR_STORE_DIR))
            logger.info(f"[VECTOR STORE] Saved to {VECTOR_STORE_DIR}")
    
    def load_vector_store(self):
        """Load vector store from disk if exists"""
        if VECTOR_STORE_DIR.exists() and (VECTOR_STORE_DIR / "index.faiss").exists():
            try:
                self.vectorstore = FAISS.load_local(
                    str(VECTOR_STORE_DIR),
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info("[VECTOR STORE] Loaded from disk")
                return True
            except Exception as e:
                logger.warning(f"[VECTOR STORE] Failed to load: {e}")
        return False
    
    def get_retriever(self, k: int = 10):
        """Get retriever for similarity search"""
        if not self.vectorstore:
            self.load_vector_store() or self.create_vector_store()
        return self.vectorstore.as_retriever(search_kwargs={"k": k})
    
    def get_context(self, query: str, k: int = 10) -> str:
        """Get relevant context for a query"""
        if not self.vectorstore:
            self.load_vector_store() or self.create_vector_store()
        
        docs = self.vectorstore.similarity_search(query, k=k)
        
        if not docs:
            return ""
        
        context = "\n\n".join([doc.page_content for doc in docs])
        logger.info(f"[VECTOR STORE] Retrieved {len(docs)} chunks")
        return context
    
    def add_learning_data(self, content: str, source: str = "manual"):
        """Add new learning data"""
        if not self.vectorstore:
            self.load_vector_store() or self.create_vector_store()
        
        # Create document
        doc = Document(
            page_content=content,
            metadata={"source": source}
        )
        
        # Split and add
        texts = self.text_splitter.split_documents([doc])
        self.vectorstore.add_documents(texts)
        self.save_vector_store()
        
        logger.info(f"[VECTOR STORE] Added {len(texts)} chunks from {source}")
