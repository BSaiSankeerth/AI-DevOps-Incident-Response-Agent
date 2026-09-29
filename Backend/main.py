import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.agent.graph import graph
from app.rag.pdf_loader import extract_text_from_pdf
from app.rag.ingest import ingest_document


app = FastAPI(
    title="AI DevOps Incident Response Agent",
    description="AI-powered DevOps incident analysis and response system",
    version="1.0.0"
)


# -------------------------
# Request Models
# -------------------------

class ChatRequest(BaseModel):
    message: str


# -------------------------
# Root
# -------------------------

@app.get("/")
def root():
    return {
        "message": "AI DevOps Incident Response Agent is running"
    }


# -------------------------
# Health Check
# -------------------------

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


# -------------------------
# Chat
# -------------------------

@app.post("/chat")
def chat(request: ChatRequest):

    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": request.message
                }
            ]
        }
    )

    final_message = result["messages"][-1]

    return {
        "answer": final_message.content
    }


# -------------------------
# PDF Upload
# -------------------------

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):

    # Check file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    temp_path = None

    try:

        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:

            content = await file.read()

            temp_file.write(content)

            temp_path = temp_file.name

        # Extract text from PDF
        text = extract_text_from_pdf(temp_path)

        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the PDF."
            )

        # Store chunks and embeddings in Qdrant
        chunks_added = ingest_document(
            text=text,
            source=file.filename
        )

        return {
            "message": "PDF uploaded and indexed successfully.",
            "filename": file.filename,
            "chunks_added": chunks_added
        }

    finally:

        # Delete temporary file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
