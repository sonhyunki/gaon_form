#!/usr/bin/env python3
"""
가온누리(GAON) 동아리 실적 관리 전용 로컬 DB 서버
- 포트 8000에서 웹페이지 서빙 및 실시간 SQLite/JSON DB 영구 저장 API 제공
- 브라우저에서 변경되는 모든 실적 체크·회차 설정이 즉시 SQLite 및 JSON DB에 영구 반영됩니다.
- 실행법: python3 server.py
"""

import http.server
import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "gaon_database.json")
DB_PATH = os.path.join(BASE_DIR, "gaon_activities.db")
PORT = 8000


def sync_to_sqlite(data):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Update checked status and meeting counts
        for a in data.get("activities", []):
            cur.execute("""
            UPDATE gaon_activities
            SET is_gaon_checked = ?,
                meeting_count = ?,
                gaon_category = ?,
                first_session_date = ?,
                last_session_date = ?,
                session_schedule_text = ?,
                gaon_member_count = ?
            WHERE id = ?;
            """, (
                1 if a.get("is_gaon_checked") else 0,
                a.get("meeting_count", 1),
                a.get("gaon_category", "스터디"),
                a.get("first_session_date"),
                a.get("last_session_date"),
                a.get("session_schedule_text"),
                a.get("gaon_member_count", 2),
                a.get("id")
            ))

        # Update member summary totals
        for m in data.get("members", []):
            cur.execute("""
            UPDATE gaon_members
            SET study_count = ?,
                study_meetings = ?,
                seminar_count = ?,
                seminar_meetings = ?,
                project_count = ?,
                project_meetings = ?,
                ssp_total_count = ?,
                ssp_meetings = ?,
                total_activities = ?
            WHERE student_id = ?;
            """, (
                m.get("study_count", 0),
                m.get("study_meetings", 0),
                m.get("seminar_count", 0),
                m.get("seminar_meetings", 0),
                m.get("project_count", 0),
                m.get("project_meetings", 0),
                m.get("ssp_total_count", 0),
                m.get("ssp_meetings", 0),
                m.get("total_activities", 0),
                m.get("student_id")
            ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[SQLite Sync Error]:", e)
        return False


class GaonDBRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Enable CORS
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/state":
            if os.path.exists(JSON_PATH):
                with open(JSON_PATH, "r", encoding="utf-8") as f:
                    content = f.read().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return
        elif self.path == "/api/health":
            body = json.dumps({"status": "ok", "db": "SQLite + JSON"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def do_POST(self):
        if self.path == "/api/save":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body.decode("utf-8"))
                # 1. Save to JSON
                with open(JSON_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # 2. Sync to SQLite
                sqlite_ok = sync_to_sqlite(data)

                resp = json.dumps({
                    "success": True,
                    "sqlite_synced": sqlite_ok,
                    "activities_count": len(data.get("activities", [])),
                    "members_count": len(data.get("members", []))
                }).encode("utf-8")

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                print(f"[DB Saved] {len(data.get('activities', []))} activities saved to gaon_database.json & SQLite!")
                return
            except Exception as e:
                err_resp = json.dumps({"success": False, "error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_resp)))
                self.end_headers()
                self.wfile.write(err_resp)
                return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server_address = ("", port)
    print("=" * 60)
    print(f"🚀 가온누리 DB 서버 실행 중: http://localhost:{port}")
    print(f"📁 SQLite DB 파일: {DB_PATH}")
    print(f"📁 JSON DB 파일: {JSON_PATH}")
    print("브라우저에서 접속하여 수정한 모든 내역이 SQLite와 JSON에 영구 저장됩니다.")
    print("종료하려면 Ctrl+C 를 누르세요.")
    print("=" * 60)
    httpd = http.server.HTTPServer(server_address, GaonDBRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버가 종료되었습니다.")
