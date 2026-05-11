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

class SnapshotRequest(BaseModel):
    asin: str
    dimension: str = "week"
    snapshot_date: str
    metrics_json: str

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
        target_asin = req.asin or "B08N5WRWNW"
        demo = [
            # SP Auto campaigns
            {"campaign": "Auto_SP_B08N5WRWNW", "ad_group": "Close Match", "acos_3d": 16.2, "acos_30d": 18.5, "bid": 1.25, "clicks": 48, "orders": 4, "keyword": "power cord", "budget": 22, "sv": "185000", "ar": "1200", "ad_type": "SP"},
            {"campaign": "Auto_SP_B08N5WRWNW", "ad_group": "Loose Match", "acos_3d": 44.8, "acos_30d": 46.3, "bid": 0.75, "clicks": 135, "orders": 0, "keyword": "cable wire", "budget": 16, "sv": "8500", "ar": "65000", "ad_type": "SP"},
            {"campaign": "Auto_SP_B08N5WRWNW", "ad_group": "Substitutes", "acos_3d": 31.5, "acos_30d": 33.0, "bid": 0.95, "clicks": 72, "orders": 2, "keyword": "extension cord", "budget": 18, "sv": "68000", "ar": "4500", "ad_type": "SP"},
            {"campaign": "Auto_SP_B08N5WRWNW", "ad_group": "Complements", "acos_3d": 28.0, "acos_30d": 29.5, "bid": 0.88, "clicks": 65, "orders": 3, "keyword": "power adapter", "budget": 15, "sv": "92000", "ar": "2100", "ad_type": "SP"},
            # SP Broad campaigns
            {"campaign": "Broad_SP_B08N5WRWNW_Prospect", "ad_group": "Broad", "acos_3d": 29.5, "acos_30d": 32.1, "bid": 1.45, "clicks": 88, "orders": 4, "keyword": "ac power cable", "budget": 26, "sv": "95000", "ar": "3800", "ad_type": "SP"},
            {"campaign": "Broad_SP_B08N5WRWNW_Prospect", "ad_group": "Broad", "acos_3d": 38.2, "acos_30d": 40.5, "bid": 0.92, "clicks": 102, "orders": 1, "keyword": "6ft power cord", "budget": 20, "sv": "42000", "ar": "8500", "ad_type": "SP"},
            {"campaign": "Broad_SP_B08N5WRWNW_Prospect", "ad_group": "Broad", "acos_3d": 35.0, "acos_30d": 36.8, "bid": 0.85, "clicks": 90, "orders": 2, "keyword": "10ft extension cord", "budget": 18, "sv": "28000", "ar": "12000", "ad_type": "SP"},
            {"campaign": "Broad_SP_B08N5WRWNW_Prospect", "ad_group": "Broad", "acos_3d": 42.0, "acos_30d": 43.5, "bid": 0.78, "clicks": 115, "orders": 0, "keyword": "heavy duty extension cord", "budget": 16, "sv": "15000", "ar": "22000", "ad_type": "SP"},
            # SP Phrase campaigns
            {"campaign": "Phrase_SP_B08N5WRWNW_Mid", "ad_group": "Phrase", "acos_3d": 21.0, "acos_30d": 23.5, "bid": 1.65, "clicks": 62, "orders": 5, "keyword": "3 prong power cord", "budget": 28, "sv": "35000", "ar": "28000", "ad_type": "SP"},
            {"campaign": "Phrase_SP_B08N5WRWNW_Mid", "ad_group": "Phrase", "acos_3d": 24.5, "acos_30d": 26.0, "bid": 1.40, "clicks": 58, "orders": 4, "keyword": "ac power cord 6ft", "budget": 24, "sv": "18000", "ar": "32000", "ad_type": "SP"},
            {"campaign": "Phrase_SP_B08N5WRWNW_Mid", "ad_group": "Phrase", "acos_3d": 33.0, "acos_30d": 34.5, "bid": 1.10, "clicks": 70, "orders": 2, "keyword": "power cable extension", "budget": 20, "sv": "22000", "ar": "26000", "ad_type": "SP"},
            # SP Exact campaigns
            {"campaign": "Exact_SP_B08N5WRWNW_Harvest", "ad_group": "Exact", "acos_3d": 11.5, "acos_30d": 13.2, "bid": 2.05, "clicks": 64, "orders": 9, "keyword": "power cord", "budget": 32, "sv": "185000", "ar": "1200", "ad_type": "SP"},
            {"campaign": "Exact_SP_B08N5WRWNW_Harvest", "ad_group": "Exact", "acos_3d": 9.8, "acos_30d": 10.5, "bid": 2.45, "clicks": 56, "orders": 7, "keyword": "heavy duty power cord", "budget": 36, "sv": "22000", "ar": "18000", "ad_type": "SP"},
            {"campaign": "Exact_SP_B08N5WRWNW_Harvest", "ad_group": "Exact", "acos_3d": 7.5, "acos_30d": 8.2, "bid": 2.80, "clicks": 52, "orders": 8, "keyword": "3 prong ac power cord", "budget": 30, "sv": "28000", "ar": "15000", "ad_type": "SP"},
            {"campaign": "Exact_SP_B08N5WRWNW_Harvest", "ad_group": "Exact", "acos_3d": 13.0, "acos_30d": 14.5, "bid": 1.95, "clicks": 60, "orders": 6, "keyword": "6ft power cord", "budget": 28, "sv": "42000", "ar": "8500", "ad_type": "SP"},
            # SP Product Targeting
            {"campaign": "PT_SP_B08N5WRWNW_Comp", "ad_group": "Product Targeting", "acos_3d": 26.5, "acos_30d": 28.0, "bid": 1.20, "clicks": 42, "orders": 3, "keyword": "ASIN_B07XXXXXX", "budget": 18, "sv": "0", "ar": "0", "ad_type": "SP"},
            {"campaign": "PT_SP_B08N5WRWNW_Comp", "ad_group": "Product Targeting", "acos_3d": 18.0, "acos_30d": 19.5, "bid": 1.35, "clicks": 38, "orders": 4, "keyword": "ASIN_B09XXXXXX", "budget": 16, "sv": "0", "ar": "0", "ad_type": "SP"},
            # SP Brand Defense
            {"campaign": "Brand_Defense_SP_B08N5WRWNW", "ad_group": "Brand", "acos_3d": 4.5, "acos_30d": 5.2, "bid": 1.85, "clicks": 45, "orders": 6, "keyword": "brand power cord", "budget": 15, "sv": "2500", "ar": "140000", "ad_type": "SP"},
            {"campaign": "Brand_Defense_SP_B08N5WRWNW", "ad_group": "Brand", "acos_3d": 6.0, "acos_30d": 6.8, "bid": 1.70, "clicks": 40, "orders": 5, "keyword": "official brand cable", "budget": 14, "sv": "1800", "ar": "165000", "ad_type": "SP"},
            # SP B2B
            {"campaign": "B2B_SP_B08N5WRWNW", "ad_group": "B2B", "acos_3d": 19.5, "acos_30d": 21.0, "bid": 1.55, "clicks": 35, "orders": 3, "keyword": "bulk power cord", "budget": 20, "sv": "5500", "ar": "58000", "ad_type": "SP"},
            {"campaign": "B2B_SP_B08N5WRWNW", "ad_group": "B2B", "acos_3d": 22.0, "acos_30d": 24.0, "bid": 1.30, "clicks": 30, "orders": 2, "keyword": "commercial power cable", "budget": 18, "sv": "3200", "ar": "72000", "ad_type": "SP"},
            # SB Brand
            {"campaign": "SB_Brand_B08N5WRWNW", "ad_group": "Brand", "acos_3d": 14.0, "acos_30d": 15.5, "bid": 2.20, "clicks": 78, "orders": 7, "keyword": "brand power cord", "budget": 35, "sv": "2500", "ar": "140000", "ad_type": "SB"},
            {"campaign": "SB_Brand_B08N5WRWNW", "ad_group": "Brand", "acos_3d": 16.5, "acos_30d": 17.8, "bid": 1.95, "clicks": 68, "orders": 5, "keyword": "official store", "budget": 30, "sv": "1200", "ar": "180000", "ad_type": "SB"},
            # SB Competitor
            {"campaign": "SB_Competitor_B08N5WRWNW", "ad_group": "Competitor", "acos_3d": 27.0, "acos_30d": 29.0, "bid": 1.75, "clicks": 55, "orders": 3, "keyword": "competitor brand cord", "budget": 25, "sv": "4800", "ar": "62000", "ad_type": "SB"},
            {"campaign": "SB_Competitor_B08N5WRWNW", "ad_group": "Competitor", "acos_3d": 31.0, "acos_30d": 33.5, "bid": 1.50, "clicks": 48, "orders": 2, "keyword": "vs competitor cable", "budget": 22, "sv": "2100", "ar": "95000", "ad_type": "SB"},
            # SD Retargeting
            {"campaign": "SD_Retarget_B08N5WRWNW", "ad_group": "Views", "acos_3d": 20.0, "acos_30d": 22.0, "bid": 1.10, "clicks": 85, "orders": 5, "keyword": "Views Retargeting", "budget": 28, "sv": "0", "ar": "0", "ad_type": "SD"},
            {"campaign": "SD_Retarget_B08N5WRWNW", "ad_group": "Views", "acos_3d": 24.0, "acos_30d": 25.5, "bid": 0.95, "clicks": 72, "orders": 4, "keyword": "Purchases Retargeting", "budget": 24, "sv": "0", "ar": "0", "ad_type": "SD"},
            # SD Lookalike
            {"campaign": "SD_Lookalike_B08N5WRWNW", "ad_group": "Similar", "acos_3d": 32.0, "acos_30d": 34.0, "bid": 0.85, "clicks": 95, "orders": 2, "keyword": "Similar Products", "budget": 20, "sv": "0", "ar": "0", "ad_type": "SD"},
            {"campaign": "SD_Lookalike_B08N5WRWNW", "ad_group": "Similar", "acos_3d": 36.5, "acos_30d": 38.0, "bid": 0.72, "clicks": 110, "orders": 1, "keyword": "Lookalike Audience", "budget": 18, "sv": "0", "ar": "0", "ad_type": "SD"},
        ]
        core_keywords = {"power cord", "3 prong power cord", "heavy duty power cord", "ac power cable", "extension cord", "power adapter"}
        for d in demo:
            campaigns.append({
                "asin": target_asin,
                "campaign": d["campaign"], "ad_group": d["ad_group"], "ad_type": d["ad_type"],
                "budget": d["budget"], "acos_3d": d["acos_3d"], "acos_30d": d["acos_30d"],
                "bid": d["bid"], "clicks": d["clicks"], "orders": d["orders"],
                "keyword": d["keyword"],
                "cvr": d["orders"] / d["clicks"] * 100 if d["clicks"] > 0 else 0,
                "is_core": d["keyword"] in core_keywords,
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

@app.get("/api/reports/{report_id}")
def api_get_report(report_id: int, request: Request):
    user_id = request.headers.get('x-user-id')
    role = request.headers.get('x-user-role', 'member')
    report = db.get_report_detail(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    if role != 'admin' and str(report.get('user_id')) != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此报告")
    return report

# --- Snapshots ---

@app.post("/api/snapshots")
def api_save_snapshot(req: SnapshotRequest, request: Request):
    user_id = request.headers.get('x-user-id')
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    snapshot_id = db.save_snapshot(
        int(user_id), req.asin, req.dimension, req.snapshot_date, req.metrics_json
    )
    return {"success": True, "id": snapshot_id}

@app.get("/api/snapshots")
def api_get_snapshots(request: Request, asin: str = "", dimension: str = "week", period: str = ""):
    user_id = request.headers.get('x-user-id')
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    dim = period or dimension
    snapshots = db.get_snapshots(int(user_id), asin, dim)
    return snapshots

@app.delete("/api/snapshots/{snapshot_id}")
def api_delete_snapshot(snapshot_id: int, request: Request):
    user_id = request.headers.get('x-user-id')
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    ok = db.delete_snapshot(snapshot_id)
    return {"success": ok}

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
