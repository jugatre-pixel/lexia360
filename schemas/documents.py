from pydantic import BaseModel

class PdfResponse(BaseModel):
    ok: bool = True

