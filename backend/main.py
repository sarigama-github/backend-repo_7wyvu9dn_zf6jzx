from fastapi import FastAPI, UploadFile, File as FastAPIFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import io

from database import create_document, get_documents, update_document, delete_document, get_document
from schemas import Activity, Finance, File as FileSchema, ActivityOut, FinanceOut, FileOut

# Simple AI summary placeholder (could be replaced with actual LLM)
def generate_summary(month: int, year: int, activities: List[Dict[str, Any]], finances: List[Dict[str, Any]]) -> str:
    total_acts = len(activities)
    by_cat: Dict[str, int] = {}
    for a in activities:
        by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
    income = sum(f.get("income", 0) for f in finances)
    expense = sum(f.get("expense", 0) for f in finances)
    top_cat = max(by_cat, key=by_cat.get) if by_cat else "-"
    return (
        f"Monthly Summary for {year}-{month:02d}:\n"
        f"Total activities: {total_acts}. Top category: {top_cat}.\n"
        f"Activities by category: {by_cat}.\n"
        f"Finance — Income: {income:.2f}, Expense: {expense:.2f}, Net: {income-expense:.2f}."
    )

app = FastAPI(title="Monthly Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health
@app.get("/test")
def test():
    return {"status": "ok"}

# File upload storage: save to local /tmp/uploads and serve by URL field
import os
UPLOAD_DIR = os.path.join("/tmp", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/files", response_model=FileOut)
async def upload_file(file: UploadFile = FastAPIFile(...)):
    contents = await file.read()
    path = os.path.join(UPLOAD_DIR, f"{int(datetime.utcnow().timestamp()*1000)}_{file.filename}")
    with open(path, "wb") as f:
        f.write(contents)
    doc = create_document("file", {
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "url": path,
        "size": len(contents)
    })
    return doc

@app.get("/files/{file_id}")
async def get_file(file_id: str):
    doc = get_document("file", file_id)
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")
    path = doc.get("url")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File missing on disk")
    def iterfile():
        with open(path, "rb") as f:
            yield from f
    return StreamingResponse(iterfile(), media_type=doc.get("content_type", "application/octet-stream"))

# Activities CRUD
@app.post("/activities", response_model=ActivityOut)
async def create_activity(payload: Activity):
    doc = create_document("activity", payload.dict())
    return doc

@app.get("/activities", response_model=List[ActivityOut])
async def list_activities(month: Optional[int] = None, year: Optional[int] = None):
    filter_q: Dict[str, Any] = {}
    docs = get_documents("activity", filter_q, sort=[("date", 1)])
    # Client-side can filter; for simplicity, do minimal filtering here
    if month or year:
        res = []
        for d in docs:
            d_date = datetime.fromisoformat(str(d["date"])) if not isinstance(d["date"], datetime) else d["date"]
            if (not year or d_date.year == year) and (not month or d_date.month == month):
                res.append(d)
        return res
    return docs

@app.put("/activities/{id}", response_model=ActivityOut)
async def update_activity(id: str, payload: Activity):
    doc = update_document("activity", id, payload.dict())
    return doc

@app.delete("/activities/{id}")
async def remove_activity(id: str):
    ok = delete_document("activity", id)
    return {"success": ok}

# Finances CRUD
@app.post("/finances", response_model=FinanceOut)
async def create_finance(payload: Finance):
    doc = create_document("finance", payload.dict())
    return doc

@app.get("/finances", response_model=List[FinanceOut])
async def list_finances(month: Optional[int] = None, year: Optional[int] = None):
    docs = get_documents("finance", sort=[("date", 1)])
    if month or year:
        res = []
        for d in docs:
            d_date = datetime.fromisoformat(str(d["date"])) if not isinstance(d["date"], datetime) else d["date"]
            if (not year or d_date.year == year) and (not month or d_date.month == month):
                res.append(d)
        return res
    return docs

@app.put("/finances/{id}", response_model=FinanceOut)
async def update_finance(id: str, payload: Finance):
    doc = update_document("finance", id, payload.dict())
    return doc

@app.delete("/finances/{id}")
async def remove_finance(id: str):
    ok = delete_document("finance", id)
    return {"success": ok}

# Aggregate endpoints
class RecapResponse(BaseModel):
    month: int
    year: int
    total_activities: int
    activities_by_category: Dict[str, int]
    total_income: float
    total_expense: float
    net: float
    summary: str

@app.get("/recap", response_model=RecapResponse)
async def monthly_recap(month: int, year: int):
    acts = await list_activities(month=month, year=year)
    fins = await list_finances(month=month, year=year)
    by_cat: Dict[str, int] = {}
    for a in acts:
        by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
    total_income = sum(x.get("income", 0) for x in fins)
    total_expense = sum(x.get("expense", 0) for x in fins)
    summary = generate_summary(month, year, acts, fins)
    return RecapResponse(
        month=month,
        year=year,
        total_activities=len(acts),
        activities_by_category=by_cat,
        total_income=total_income,
        total_expense=total_expense,
        net=total_income-total_expense,
        summary=summary,
    )

# Export endpoints (PDF/Excel)
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import xlsxwriter

@app.get("/export/pdf")
async def export_pdf(month: int, year: int):
    recap = await monthly_recap(month, year)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    textobject = c.beginText(40, 800)
    textobject.textLines([
        f"Monthly Report {recap.year}-{recap.month:02d}",
        f"Total activities: {recap.total_activities}",
        f"Activities by category: {recap.activities_by_category}",
        f"Income: {recap.total_income:.2f}",
        f"Expense: {recap.total_expense:.2f}",
        f"Net: {recap.net:.2f}",
        "",
        "Summary:",
        recap.summary,
    ])
    c.drawText(textobject)
    c.showPage()
    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=report_{year}_{month:02d}.pdf"})

@app.get("/export/excel")
async def export_excel(month: int, year: int):
    acts = await list_activities(month=month, year=year)
    fins = await list_finances(month=month, year=year)
    output = io.BytesIO()
    import pandas as pd
    # If pandas not in requirements, we can build with xlsxwriter directly
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    ws1 = workbook.add_worksheet("Activities")
    headers_a = ["date","name","category","duration_hours","output","notes"]
    for i, h in enumerate(headers_a): ws1.write(0, i, h)
    for r, a in enumerate(acts, start=1):
        ws1.write(r, 0, str(a.get("date")))
        ws1.write(r, 1, a.get("name"))
        ws1.write(r, 2, a.get("category"))
        ws1.write(r, 3, a.get("duration_hours", 0))
        ws1.write(r, 4, a.get("output"))
        ws1.write(r, 5, a.get("notes"))
    ws2 = workbook.add_worksheet("Finance")
    headers_f = ["date","category","income","expense","notes"]
    for i, h in enumerate(headers_f): ws2.write(0, i, h)
    for r, f in enumerate(fins, start=1):
        ws2.write(r, 0, str(f.get("date")))
        ws2.write(r, 1, f.get("category"))
        ws2.write(r, 2, f.get("income", 0))
        ws2.write(r, 3, f.get("expense", 0))
        ws2.write(r, 4, f.get("notes"))
    workbook.close()
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=report_{year}_{month:02d}.xlsx"})
