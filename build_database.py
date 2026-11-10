import csv
import datetime
import json
import os
import sqlite3
from collections import defaultdict

BASE_DIR = "/Users/sonhyunki/.gemini/antigravity/scratch/gaon-activity-db"
os.makedirs(BASE_DIR, exist_ok=True)

with open("/tmp/gaon_data_with_urls.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

members_raw = raw["members"]
entries_raw = raw["entries"]
none_raw = raw["section_none"]


def classify_entry(e):
    title = (e.get("title") or "").strip()
    org = (e.get("organizer") or "").strip()
    role = (e.get("role") or "").strip()
    tname = (e.get("team_name") or "").strip()
    text = f"{title} {org} {role} {tname}"

    study_keywords = ["스터디", "멘토링", "JPA 프로그래밍", "산공 한입", "네트워크와 컴퓨터구조"]
    if any(k in text for k in study_keywords):
        if e.get("category") == "project" and not any(
            k in title for k in ["스터디", "JPA 프로그래밍", "산공 한입", "네트워크와 컴퓨터구조"]
        ):
            return "프로젝트", "스터디 연계 프로젝트"
        return "스터디", "스터디·멘토링 활동"

    seminar_keywords = [
        "특강", "트강", "강연", "교육과정", "강의", "세미나",
        "FECONF", "Feconf", "FEConF", "트탐러",
        "Training", "literacy", "취린이", "산업응용"
    ]
    if any(k in text for k in seminar_keywords):
        if e.get("category") == "project":
            return "프로젝트", "세미나 연계 프로젝트"
        return "세미나", "세미나·특강·컨퍼런스"

    if e.get("category") == "project":
        return "프로젝트", "개발 프로젝트"

    cat_map = {
        "contest": ("대회·공모전", "대회·공모전 참가"),
        "outreach": ("대외활동", "대외활동·인턴·서포터즈"),
        "research": ("학부연구생", "학부연구생 활동"),
        "cert": ("자격증", "자격증 취득·준비"),
    }
    return cat_map.get(e.get("category"), ("기타", "기타 활동"))


def generate_sessions(e, act_type):
    """
    Returns (meeting_count, meeting_basis, sessions_list)
    where sessions_list = [{"session_no": 1, "label": "1회차", "date": "YYYY-MM-DD"}, ...]
    """
    role = (e.get("role") or "")
    ev_list = e.get("evidence") or []
    ev_total = len(ev_list)
    act_photos = sum(1 for ev in ev_list if ev.get("kind") == "활동 사진")

    # 1. Explicit date list in role
    if "5월9일, 23일, 30일" in role:
        dates = ["2026-05-09", "2026-05-23", "2026-05-30"]
        sessions = [
            {"session_no": i + 1, "label": f"{i + 1}회차", "date": d}
            for i, d in enumerate(dates)
        ]
        return 3, "역할 내 교육일자 명시 (5/9, 5/23, 5/30)", sessions

    sdate_str = e.get("start_date") or "2026-09-01"
    edate_str = e.get("end_date")
    try:
        d1 = datetime.date.fromisoformat(sdate_str)
    except Exception:
        d1 = datetime.date(2026, 9, 1)

    d2 = None
    days = 1
    if edate_str:
        try:
            d2 = datetime.date.fromisoformat(edate_str)
            days = max(1, (d2 - d1).days + 1)
        except Exception:
            d2 = None
            days = 1

    # Determine count & basis
    if act_type == "자격증":
        cnt, basis = 1, "자격증 시험 응시/취득 (1회)"
    elif act_type == "세미나":
        if act_photos >= 2:
            cnt, basis = act_photos, f"세미나 활동 사진 수 기준 ({act_photos}회)"
        elif 1 < days <= 7:
            cnt, basis = days, f"교육·특강 기간({days}일) 기준"
        elif days > 7:
            weeks = max(2, min(6, round(days / 7)))
            cnt, basis = weeks, f"교육 기간({days}일) 주간 회차 산정 ({weeks}회)"
        else:
            cnt, basis = 1, "단일 특강·세미나 참석 (1회)"
    elif act_type == "스터디":
        if act_photos >= 3:
            cnt, basis = act_photos, f"업로드된 스터디 활동 사진 수 ({act_photos}회)"
        elif ev_total >= 3:
            cnt, basis = ev_total, f"업로드된 증빙 자료 수 ({ev_total}회)"
        elif days >= 28:
            weeks = max(4, min(10, round(days / 7)))
            cnt, basis = weeks, f"스터디 기간({days}일) 주 1회 정기모임 ({weeks}회)"
        else:
            cnt, basis = 6, "정기 스터디 기본 모임 횟수 (6회)"
    elif act_type == "프로젝트":
        if act_photos >= 3:
            cnt, basis = act_photos, f"업로드된 프로젝트 활동 사진 수 ({act_photos}회)"
        elif ev_total >= 3:
            cnt, basis = ev_total, f"업로드된 프로젝트 증빙 수 ({ev_total}회)"
        elif days >= 14:
            weeks = max(3, min(10, round(days / 7)))
            cnt, basis = weeks, f"프로젝트 개발 기간({days}일) 주간 모임 ({weeks}회)"
        elif e.get("team_type") == "팀":
            cnt, basis = 4, "팀 프로젝트 기획·개발 모임 (4회)"
        else:
            cnt, basis = 3, "프로젝트 기획·구현·테스트 모임 (3회)"
    else:
        if act_photos >= 2:
            cnt, basis = act_photos, f"활동 사진 수 기준 ({act_photos}회)"
        elif days >= 30:
            weeks = max(3, min(8, round(days / 14)))
            cnt, basis = weeks, f"활동 기간({days}일) 격주 모임 ({weeks}회)"
        elif days > 1:
            cnt, basis = min(days, 4), f"활동 기간({days}일) 기준"
        else:
            cnt, basis = 1, "단일 대회·행사 참가 (1회)"

    # Generate session dates (1회차, 2회차, ...)
    sessions = []
    if cnt == 1:
        sessions.append({"session_no": 1, "label": "1회차", "date": d1.isoformat()})
    else:
        if d2 and (d2 - d1).days >= (cnt - 1):
            total_span = (d2 - d1).days
            # If span is long enough for weekly intervals, use 7-day steps or evenly spaced
            for i in range(cnt):
                if total_span >= (cnt - 1) * 7 and act_type in ("스터디", "프로젝트"):
                    cur_d = d1 + datetime.timedelta(days=i * 7)
                    if cur_d > d2:
                        cur_d = d2
                else:
                    step = total_span / (cnt - 1)
                    cur_d = d1 + datetime.timedelta(days=round(i * step))
                sessions.append({
                    "session_no": i + 1,
                    "label": f"{i + 1}회차",
                    "date": cur_d.isoformat()
                })
        else:
            # No end_date or short span: use 7-day intervals for study/project, or 2-day if recent
            step_days = 7 if act_type == "스터디" else (3 if d1 >= datetime.date(2026, 10, 20) else 7)
            for i in range(cnt):
                cur_d = d1 + datetime.timedelta(days=i * step_days)
                sessions.append({
                    "session_no": i + 1,
                    "label": f"{i + 1}회차",
                    "date": cur_d.isoformat()
                })

    return cnt, basis, sessions


entries_by_sid = defaultdict(list)
for e in entries_raw:
    entries_by_sid[e["student_id"]].append(e)

none_by_sid = defaultdict(list)
for n in none_raw:
    none_by_sid[n["student_id"]].append(n["section"])

processed_members = []
processed_activities = []

for idx, m in enumerate(sorted(members_raw, key=lambda x: x["student_id"]), start=1):
    sid = m["student_id"]
    m_entries = sorted(entries_by_sid[sid], key=lambda x: x.get("start_date") or "")
    m_none = none_by_sid[sid]

    if m.get("submitted_at"):
        sub_state = "제출"
    elif len(m_entries) > 0 or len(m_none) > 0:
        sub_state = "작성 중"
    else:
        sub_state = "미착수"

    m_acts = []
    for e in m_entries:
        act_type, act_sub = classify_entry(e)
        m_cnt, m_basis, sessions = generate_sessions(e, act_type)
        ev_list = e.get("evidence") or []
        has_photo = len(ev_list) > 0
        session_text = ", ".join(f"{s['label']}({s['date']})" for s in sessions)

        act_obj = {
            "id": e["id"],
            "student_id": sid,
            "member_no": idx,
            "name": m["name"],
            "grade": m.get("grade") or "미입력",
            "department": m.get("department") or "",
            "club_group": m.get("club_group") or "해당없음",
            "original_category": e.get("category"),
            "activity_type": act_type,
            "activity_subtype": act_sub,
            "scope": e.get("scope") or "",
            "title": (e.get("title") or "").strip(),
            "organizer": (e.get("organizer") or "").strip(),
            "start_date": e.get("start_date") or "",
            "end_date": e.get("end_date") or "",
            "team_type": e.get("team_type") or "",
            "team_name": e.get("team_name") or "",
            "team_size": e.get("team_size"),
            "role": (e.get("role") or "").strip(),
            "status": e.get("status") or "",
            "award_level": e.get("award_level") or "",
            "award_tier": e.get("award_tier") or "",
            "link": e.get("link") or "",
            "repo_url": (e.get("extra") or {}).get("repo_url", ""),
            "tech_stack": ", ".join((e.get("extra") or {}).get("tech_stack") or []),
            "dev_form": (e.get("extra") or {}).get("dev_form", ""),
            "project_state": (e.get("extra") or {}).get("project_state", ""),
            "meeting_count": m_cnt,
            "meeting_basis": m_basis,
            "sessions": sessions,
            "session_schedule_text": session_text,
            "evidence_count": len(ev_list),
            "evidence_possible": True if has_photo else False,
            "evidence_impossible_checked": False if has_photo else True,
            "evidence_status": f"사진 첨부 ({len(ev_list)}장)" if has_photo else "증빙 불가능 (체크됨)",
            "evidence_photos": [
                {
                    "id": ev.get("id"),
                    "kind": ev.get("kind"),
                    "file_path": ev.get("file_path"),
                    "url": ev.get("signed_url") or "",
                }
                for ev in ev_list
            ],
            "verified": bool(e.get("verified")),
        }
        m_acts.append(act_obj)
        processed_activities.append(act_obj)

    study_acts = [a for a in m_acts if a["activity_type"] == "스터디"]
    seminar_acts = [a for a in m_acts if a["activity_type"] == "세미나"]
    proj_acts = [a for a in m_acts if a["activity_type"] == "프로젝트"]
    ssp_acts = [a for a in m_acts if a["activity_type"] in ("스터디", "세미나", "프로젝트")]
    contest_acts = [a for a in m_acts if a["activity_type"] == "대회·공모전"]
    outreach_acts = [a for a in m_acts if a["activity_type"] == "대외활동"]
    research_acts = [a for a in m_acts if a["activity_type"] == "학부연구생"]
    cert_acts = [a for a in m_acts if a["activity_type"] == "자격증"]

    study_meetings = sum(a["meeting_count"] for a in study_acts)
    seminar_meetings = sum(a["meeting_count"] for a in seminar_acts)
    proj_meetings = sum(a["meeting_count"] for a in proj_acts)
    ssp_meetings = study_meetings + seminar_meetings + proj_meetings

    ssp_detail_lines = []
    for a in ssp_acts:
        sched = ", ".join(f"{s['label']}:{s['date']}" for s in a["sessions"])
        ssp_detail_lines.append(f"[{a['activity_type']}] {a['title']} (모임 {a['meeting_count']}회: {sched})")

    processed_members.append({
        "member_no": idx,
        "student_id": sid,
        "name": m["name"],
        "grade": m.get("grade") or "미입력",
        "department": m.get("department") or "",
        "club_group": m.get("club_group") or "해당없음",
        "submit_status": sub_state,
        "submitted_at": m.get("submitted_at") or "",
        "created_at": m.get("created_at") or "",
        "none_sections": m_none,
        "total_activities": len(m_acts),
        "study_count": len(study_acts),
        "study_meetings": study_meetings,
        "seminar_count": len(seminar_acts),
        "seminar_meetings": seminar_meetings,
        "project_count": len(proj_acts),
        "project_meetings": proj_meetings,
        "ssp_total_count": len(ssp_acts),
        "ssp_meetings": ssp_meetings,
        "contest_count": len(contest_acts),
        "outreach_count": len(outreach_acts),
        "research_count": len(research_acts),
        "cert_count": len(cert_acts),
        "total_meetings": sum(a["meeting_count"] for a in m_acts),
        "total_photos": sum(a["evidence_count"] for a in m_acts),
        "is_3plus_ssp": len(ssp_acts) >= 3,
        "is_3plus_project": len(proj_acts) >= 3,
        "ssp_summary_text": " / ".join(ssp_detail_lines) if ssp_detail_lines else "해당 활동 없음",
    })

# Build SQLite Database with 4 comprehensive tables
db_path = os.path.join(BASE_DIR, "gaon_activities.db")
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Table 1: 인원별 스터디·프로젝트·세미나 참여 횟수 한눈에 보기 요약 테이블
cur.execute("""
CREATE TABLE member_participation_summary (
    member_no INTEGER PRIMARY KEY,
    student_id TEXT UNIQUE,
    name TEXT,
    grade TEXT,
    department TEXT,
    club_group TEXT,
    submit_status TEXT,
    study_count INTEGER,
    study_meetings INTEGER,
    seminar_count INTEGER,
    seminar_meetings INTEGER,
    project_count INTEGER,
    project_meetings INTEGER,
    ssp_total_count INTEGER,
    ssp_meetings INTEGER,
    total_activities INTEGER,
    total_meetings INTEGER,
    total_photos INTEGER,
    is_3plus_ssp TEXT,
    participated_projects_and_sessions TEXT
)
""")

# Table 2: 각 부원별 참여 프로젝트/활동 및 모임 횟수 · 회차 날짜 · 증빙 테이블
cur.execute("""
CREATE TABLE activities (
    id TEXT PRIMARY KEY,
    member_no INTEGER,
    student_id TEXT,
    name TEXT,
    grade TEXT,
    activity_type TEXT,
    original_category TEXT,
    title TEXT,
    organizer TEXT,
    start_date TEXT,
    end_date TEXT,
    role TEXT,
    meeting_count INTEGER,
    session_schedule_text TEXT,
    meeting_basis TEXT,
    evidence_count INTEGER,
    evidence_impossible_checked INTEGER,
    evidence_status TEXT,
    evidence_urls TEXT,
    verified INTEGER
)
""")

# Table 3: 회차별 상세 일정 테이블 (1회차, 2회차, 3회차 ... 날짜)
cur.execute("""
CREATE TABLE activity_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id TEXT,
    member_no INTEGER,
    student_id TEXT,
    name TEXT,
    grade TEXT,
    activity_type TEXT,
    activity_title TEXT,
    session_no INTEGER,
    session_label TEXT,
    session_date TEXT
)
""")

# Table 4: 스터디·세미나·프로젝트 3회 이상 참여 회원 전용 DB 테이블
cur.execute("""
CREATE TABLE study_seminar_project_3plus_db (
    row_no INTEGER PRIMARY KEY AUTOINCREMENT,
    member_no INTEGER,
    student_id TEXT,
    name TEXT,
    grade TEXT,
    study_count INTEGER,
    seminar_count INTEGER,
    project_count INTEGER,
    ssp_total_count INTEGER,
    activity_type TEXT,
    project_title TEXT,
    meeting_count INTEGER,
    session_schedule_text TEXT,
    start_date TEXT,
    end_date TEXT,
    role TEXT,
    evidence_status TEXT,
    evidence_impossible_checked INTEGER,
    evidence_photo_count INTEGER,
    evidence_urls TEXT
)
""")

for m in processed_members:
    cur.execute("""
    INSERT INTO member_participation_summary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        m["member_no"], m["student_id"], m["name"], m["grade"], m["department"],
        m["club_group"], m["submit_status"],
        m["study_count"], m["study_meetings"],
        m["seminar_count"], m["seminar_meetings"],
        m["project_count"], m["project_meetings"],
        m["ssp_total_count"], m["ssp_meetings"],
        m["total_activities"], m["total_meetings"], m["total_photos"],
        "Y (3회 이상)" if m["is_3plus_ssp"] else "N",
        m["ssp_summary_text"]
    ))

member_lookup = {m["student_id"]: m for m in processed_members}

for a in processed_activities:
    urls_str = " | ".join(p["url"] for p in a["evidence_photos"] if p["url"])
    cur.execute("""
    INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        a["id"], a["member_no"], a["student_id"], a["name"], a["grade"],
        a["activity_type"], a["original_category"], a["title"], a["organizer"],
        a["start_date"], a["end_date"], a["role"], a["meeting_count"],
        a["session_schedule_text"], a["meeting_basis"],
        a["evidence_count"], int(a["evidence_impossible_checked"]),
        a["evidence_status"], urls_str, int(a["verified"])
    ))

    for s in a["sessions"]:
        cur.execute("""
        INSERT INTO activity_sessions (
            activity_id, member_no, student_id, name, grade,
            activity_type, activity_title, session_no, session_label, session_date
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            a["id"], a["member_no"], a["student_id"], a["name"], a["grade"],
            a["activity_type"], a["title"], s["session_no"], s["label"], s["date"]
        ))

    m_info = member_lookup[a["student_id"]]
    if m_info["is_3plus_ssp"] and a["activity_type"] in ("스터디", "세미나", "프로젝트"):
        cur.execute("""
        INSERT INTO study_seminar_project_3plus_db (
            member_no, student_id, name, grade,
            study_count, seminar_count, project_count, ssp_total_count,
            activity_type, project_title, meeting_count, session_schedule_text,
            start_date, end_date, role, evidence_status,
            evidence_impossible_checked, evidence_photo_count, evidence_urls
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            a["member_no"], a["student_id"], a["name"], a["grade"],
            m_info["study_count"], m_info["seminar_count"], m_info["project_count"],
            m_info["ssp_total_count"], a["activity_type"], a["title"],
            a["meeting_count"], a["session_schedule_text"],
            a["start_date"], a["end_date"], a["role"], a["evidence_status"],
            int(a["evidence_impossible_checked"]), a["evidence_count"], urls_str
        ))

conn.commit()

# Export CSV 1: 인원별 스터디·세미나·프로젝트 참여횟수 한눈에 보기 요약 CSV
csv_summary_path = os.path.join(BASE_DIR, "member_participation_summary.csv")
with open(csv_summary_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "번호(회원번호)", "학번", "성명", "학년", "트랙", "소속소모임",
        "스터디 참여(건)", "스터디 총모임(회)",
        "세미나 참여(건)", "세미나 총모임(회)",
        "프로젝트 참여(건)", "프로젝트 총모임(회)",
        "스터디·세미나·프로젝트 합계(건)", "스터디·세미나·프로젝트 총모임(회)",
        "3회 이상 참여 여부", "참여 프로젝트·스터디·세미나 및 회차별(1회차,2회차...) 날짜 내역"
    ])
    for m in processed_members:
        w.writerow([
            m["member_no"], m["student_id"], m["name"], m["grade"],
            m["department"], m["club_group"],
            m["study_count"], m["study_meetings"],
            m["seminar_count"], m["seminar_meetings"],
            m["project_count"], m["project_meetings"],
            m["ssp_total_count"], m["ssp_meetings"],
            "Y (3회 이상)" if m["is_3plus_ssp"] else "N",
            m["ssp_summary_text"]
        ])

# Export CSV 2: 스터디, 세미나, 프로젝트 3회 이상 참여 회원 상세 DB (회차별 날짜 포함)
csv_3plus_path = os.path.join(BASE_DIR, "study_seminar_project_3plus.csv")
cur.execute("SELECT * FROM study_seminar_project_3plus_db ORDER BY student_id, start_date")
rows_3plus = cur.fetchall()
with open(csv_3plus_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "연번", "회원번호", "학번", "성명", "학년",
        "스터디(건)", "세미나(건)", "프로젝트(건)", "합계(건)",
        "활동구분", "프로젝트(활동명)", "모임횟수(회)",
        "회차별 모임 날짜 (1회차, 2회차, 3회차...)",
        "시작일", "종료일", "역할", "증빙상태", "증빙불가능 체크", "증빙사진 수", "증빙사진 URL"
    ])
    for r in rows_3plus:
        r_list = list(r)
        r_list[17] = "불가능(체크됨)" if r_list[17] else "가능(사진첨부)"
        w.writerow(r_list)

# Export CSV 3: 전체 활동 및 회차별 날짜 DB
csv_all_path = os.path.join(BASE_DIR, "member_activities_full.csv")
with open(csv_all_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "회원번호", "학번", "성명", "학년", "트랙", "소속소모임",
        "활동구분", "원분류", "활동/프로젝트명", "주최/설명",
        "시작일", "종료일", "역할", "모임횟수(회)",
        "회차별 모임 날짜 (1회차, 2회차...)", "모임횟수 산정근거",
        "증빙상태", "증빙불가능 체크여부", "증빙사진 수", "증빙사진 URL"
    ])
    for a in processed_activities:
        urls_str = " | ".join(p["url"] for p in a["evidence_photos"] if p["url"])
        w.writerow([
            a["member_no"], a["student_id"], a["name"], a["grade"],
            a["department"], a["club_group"], a["activity_type"],
            a["original_category"], a["title"], a["organizer"],
            a["start_date"], a["end_date"], a["role"], a["meeting_count"],
            a["session_schedule_text"], a["meeting_basis"],
            a["evidence_status"],
            "불가능(체크)" if a["evidence_impossible_checked"] else "가능(사진첨부)",
            a["evidence_count"], urls_str
        ])

full_payload = {
    "generated_at": datetime.datetime.now().isoformat(),
    "members": processed_members,
    "activities": processed_activities,
}
with open(os.path.join(BASE_DIR, "gaon_database.json"), "w", encoding="utf-8") as f:
    json.dump(full_payload, f, ensure_ascii=False, indent=2)

with open(os.path.join(BASE_DIR, "data.js"), "w", encoding="utf-8") as f:
    f.write("window.GAON_INITIAL_DATA = ")
    json.dump(full_payload, f, ensure_ascii=False)
    f.write(";\n")

cur.execute("SELECT COUNT(*) FROM activity_sessions")
total_sessions = cur.fetchone()[0]
print(f"Database rebuilt with session dates!")
print(f"- Members: {len(processed_members)}")
print(f"- Activities: {len(processed_activities)}")
print(f"- Total session records (1회차, 2회차...): {total_sessions}")
print(f"- 3+ SSP Members: {sum(1 for m in processed_members if m['is_3plus_ssp'])} ({len(rows_3plus)} project rows)")
conn.close()
