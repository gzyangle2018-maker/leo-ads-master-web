"""
Leo Ads Master - FastAPI Backend
"""
import os
import sys
import json
import traceback
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

from database import Database
from analyzer_engine import AdsAnalyzerEngine
from excel_exporter import ExcelExporter
from llm_client import LLMClient

app = FastAPI(title="Leo Ads Master API", version="2.1")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()

# --- Auth ---

def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    return hashlib.sha256((password + salt).encode()).hexdigest(), salt

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "member"
    display_name: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ResetPasswordRequest(BaseModel):
    new_password: str

class SetQuotaRequest(BaseModel):
    quota_analysis: int = -1
    quota_llm: int = -1

class AnalysisRequest(BaseModel):
    stage: str = "growth"
    asin: str = ""
    acos: float = 25.0
    tacos: float = 12.0
    unit_session_pct: float = 10.0
    budget_limit_pct: float = 10.0

@app.post("/api/login")
def api_login(req: LoginRequest, request: Request):
    user = db.authenticate(req.username, req.password)
    if not user:
        db.log_login(None, req.username, 'login_failed', ip=request.client.host, user_agent=request.headers.get('user-agent', ''))
        raise HTTPException(status_code=401, detail="Invalid credentials")
    db.log_login(user['id'], user['username'], 'login_success', ip=request.client.host, user_agent=request.headers.get('user-agent', ''))
    return {"success": True, "user": user}

@app.get("/api/users")
def api_list_users():
    return db.list_users("admin")

@app.post("/api/users")
def api_create_user(req: CreateUserRequest):
    ok, msg = db.create_user(req.username, req.password, req.role, req.display_name, "admin")
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@app.post("/api/users/{user_id}/reset-password")
def api_reset_password(user_id: int, req: ResetPasswordRequest):
    ok, msg = db.reset_password(user_id, req.new_password, "admin")
    return {"success": ok, "message": msg}

@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: int):
    ok, msg = db.delete_user(user_id, "admin")
    return {"success": ok, "message": msg}

@app.post("/api/users/me/password")
def api_change_password(req: ChangePasswordRequest, request: Request):
    # For simplicity, pass user_id via header (frontend will send it)
    user_id = request.headers.get('x-user-id')
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    ok, msg = db.change_password(int(user_id), req.old_password, req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@app.get("/api/users/{user_id}/quota")
def api_get_quota(user_id: int):
    return db.get_user_usage(user_id)

@app.post("/api/users/{user_id}/quota")
def api_set_quota(user_id: int, req: SetQuotaRequest):
    db.set_user_quota(user_id, req.quota_analysis, req.quota_llm)
    return {"success": True, "message": "配额已更新"}

# --- Upload & Analysis ---

@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    try:
        content = await file.read()
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))
        file_type = "sp_search_term"
        rows = len(df)
        cols = list(df.columns)
        return {"success": True, "filename": file.filename, "rows": rows, "columns": cols, "preview": df.head(5).to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/analyze")
def api_analyze(req: AnalysisRequest, request: Request):
    try:
        user_id = request.headers.get('x-user-id')
        if user_id:
            usage = db.get_user_usage(int(user_id))
            if usage['quota_analysis'] >= 0 and usage['analysis_count'] >= usage['quota_analysis']:
                raise HTTPException(status_code=403, detail="分析次数已用完，请联系管理员")

        engine = AdsAnalyzerEngine({})
        campaigns = []
        demo = [
            {"campaign": "Auto-Close", "ad_group": "Close Match", "acos_3d": 15, "acos_30d": 18, "bid": 1.2, "clicks": 45, "orders": 3, "keyword": "power cord", "budget": 20, "sv": "185000", "ar": "1200"},
            {"campaign": "Auto-Loose", "ad_group": "Loose Match", "acos_3d": 42, "acos_30d": 45, "bid": 0.8, "clicks": 120, "orders": 0, "keyword": "cable wire", "budget": 15, "sv": "8500", "ar": "65000"},
            {"campaign": "Broad-Prospect", "ad_group": "Broad", "acos_3d": 28, "acos_30d": 32, "bid": 1.5, "clicks": 80, "orders": 4, "keyword": "ac power cable", "budget": 25, "sv": "95000", "ar": "3800"},
            {"campaign": "Exact-Harvest", "ad_group": "Exact", "acos_3d": 12, "acos_30d": 14, "bid": 2.0, "clicks": 60, "orders": 8, "keyword": "3 prong power cord", "budget": 30, "sv": "35000", "ar": "28000"},
            {"campaign": "Brand-Defense", "ad_group": "Brand", "acos_3d": 5, "acos_30d": 6, "bid": 1.8, "clicks": 40, "orders": 5, "keyword": "brand term", "budget": 15, "sv": "2000", "ar": "150000"},
            {"campaign": "Auto-Close-2", "ad_group": "Close Match", "acos_3d": 22, "acos_30d": 25, "bid": 1.0, "clicks": 35, "orders": 2, "keyword": "power adapter", "budget": 18, "sv": "92000", "ar": "2100"},
            {"campaign": "Broad-Comp", "ad_group": "Broad", "acos_3d": 38, "acos_30d": 40, "bid": 0.9, "clicks": 95, "orders": 1, "keyword": "extension cord", "budget": 20, "sv": "68000", "ar": "4500"},
            {"campaign": "Exact-Premium", "ad_group": "Exact", "acos_3d": 8, "acos_30d": 10, "bid": 2.5, "clicks": 55, "orders": 6, "keyword": "heavy duty power cord", "budget": 35, "sv": "22000", "ar": "18000"},
        ]
        for d in demo:
            campaigns.append({
                "asin": req.asin or "B0XXXXXX",
                "campaign": d["campaign"], "ad_group": d["ad_group"], "ad_type": "SP",
                "budget": d["budget"], "acos_3d": d["acos_3d"], "acos_30d": d["acos_30d"],
                "bid": d["bid"], "clicks": d["clicks"], "orders": d["orders"],
                "keyword": d["keyword"], "cvr": d["orders"] / d["clicks"] * 100 if d["clicks"] > 0 else 0,
                "is_core": d["keyword"] in ("power cord", "3 prong power cord", "heavy duty power cord"),
                "search_volume": d.get("sv", "缺失"), "aba_rank": d.get("ar", "缺失")
            })

        metrics = {
            "acos": req.acos, "tacos": req.tacos,
            "unit_session_pct": req.unit_session_pct,
            "budget_limit_pct": req.budget_limit_pct,
            "impressions": 10000, "clicks": 500, "orders": 25, "budget": 100
        }

        diagnosis = engine.diagnose(metrics)
        traffic_tree = engine.build_traffic_tree(campaigns)
        actions = engine.analyze_12_dimensions(campaigns, metrics, req.stage)
        monitor_plan = engine.generate_monitor_plan(metrics)
        three_plans = engine.generate_three_plans(metrics, req.stage)

        today_add = [a for a in actions if a.get("category") == "加法"][:30]
        today_sub = [a for a in actions if a.get("category") == "减法"][:30]

        result = {
            "diagnosis": diagnosis,
            "traffic_tree": traffic_tree,
            "actions": actions,
            "today_add": today_add,
            "today_sub": today_sub,
            "monitor_plan": monitor_plan,
            "three_plans": three_plans,
            "stage": req.stage,
            "asin": req.asin
        }

        # Save report and log usage
        if user_id:
            uid = int(user_id)
            db.save_report(uid, f"{req.asin or '未知'}_{req.stage}_分析", "12维分析",
                           asin=req.asin, data_summary=f"ACOS:{req.acos}% TACOS:{req.tacos}%",
                           result_json=json.dumps(result, ensure_ascii=False))
            db.increment_usage(uid, 'analysis_count')
            db.log_login(uid, '', 'analysis_run', ip=request.client.host)

        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export")
def api_export(req: AnalysisRequest):
    try:
        resp = api_analyze(req, Request(scope={"type": "http", "headers": [], "client": ("127.0.0.1", 0)}))
        result = resp["result"]
        exporter = ExcelExporter()
        buf = BytesIO()
        exporter.export_report(result, buf)
        buf.seek(0)
        filename = f"{req.asin or 'report'}_12维分析_{datetime.now().strftime('%m%d')}.xlsx"
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Reports ---

@app.get("/api/reports")
def api_list_reports(request: Request):
    user_id = request.headers.get('x-user-id')
    role = request.headers.get('x-user-role', 'member')
    reports = db.get_all_reports(role=role, user_id=int(user_id) if user_id else None)
    return reports

# --- Logs ---

@app.get("/api/logs")
def api_logs(request: Request, user_id: int = None):
    role = request.headers.get('x-user-role', 'member')
    if role != 'admin':
        user_id = request.headers.get('x-user-id')
    logs = db.get_login_logs(user_id=int(user_id) if user_id else None, role=role, limit=200)
    return logs

# --- LLM Config ---

@app.get("/api/llm/providers")
def api_llm_providers():
    return LLMClient.PROVIDERS

@app.post("/api/llm/test")
def api_llm_test(provider: str, api_key: str, base_url: str = "", model: str = ""):
    try:
        client = LLMClient(provider=provider, api_key=api_key, base_url=base_url, model=model)
        ok, msg = client.test_connection()
        return {"success": ok, "message": msg}
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- Config ---

@app.get("/api/config")
def api_get_config():
    return db.get_config("llm_provider", "")

@app.post("/api/config")
def api_set_config(key: str, value: str):
    db.set_config(key, value)
    return {"success": True}

# --- Health ---

@app.get("/")
def root():
    return {"status": "ok", "service": "Leo Ads Master API", "version": "2.1"}

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.1"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
