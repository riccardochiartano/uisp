"""
Referto Basket - App Streamlit per la gestione di partite di basket
Requisiti: pip install streamlit reportlab pandas pypdf
Avvio:      streamlit run referto_basket.py

Metti il file Referto_Uisp.pdf nella stessa cartella dello script
per abilitare il download del referto ufficiale UISP compilato.
"""

import streamlit as st
from datetime import datetime, date
import csv
import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ──────────────────────────────────────────────
#  CONFIGURAZIONE PAGINA
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Referto Basket",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .big-score  { font-size:3.5rem; font-weight:900; text-align:center; }
    .team-name  { font-size:1.4rem; font-weight:700; text-align:center; }
    .foul-badge { background:#ff4b4b; color:white; border-radius:50%;
                  padding:2px 8px; font-weight:700; }
    .to-badge   { background:#f39c12; color:white; border-radius:6px;
                  padding:2px 8px; font-weight:700; font-size:0.85rem; }
    div[data-testid="stButton"] button { width:100%; }
    .log-entry  { font-size:0.85rem; padding:2px 0; border-bottom:1px solid #eee; }
    .ended-banner { background:#2d3561; color:white; padding:12px; border-radius:8px;
                    text-align:center; font-size:1.3rem; font-weight:700; margin-bottom:12px; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
#  REGOLE TIMEOUT
# ──────────────────────────────────────────────
def timeout_max(quarter: int) -> int:
    if quarter <= 2:   return 2   # primo tempo
    elif quarter <= 4: return 3   # secondo tempo
    else:              return 1   # ogni supplementare

def timeout_period(quarter: int) -> str:
    if quarter <= 2:   return "1T"
    elif quarter <= 4: return "2T"
    else:              return f"S{quarter - 4}"

def period_label(p: str) -> str:
    if p == "1T": return "1 Tempo"
    if p == "2T": return "2 Tempo"
    return f"Suppl. {p[1:]}"

# ──────────────────────────────────────────────
#  SESSION STATE
# ──────────────────────────────────────────────
def _init():
    defaults = {
        "phase": "setup",
        "match_date": date.today(),
        "location": "",
        "competition": "",
        "team_a_name": "Squadra A",
        "team_b_name": "Squadra B",
        "players_a": [],
        "players_b": [],
        "score_a": 0,
        "score_b": 0,
        "fouls_a": 0,
        "fouls_b": 0,
        "quarter": 1,
        "timeouts": {"A": {}, "B": {}},
        "stats": {},
        "partials": [],
        "quarter_start_a": 0,
        "quarter_start_b": 0,
        "time_start": None,
        "time_end": None,
        "quarter_times": [],
        "current_quarter_start": None,
        "log": [],
        "confirm_end": False,
        "campo": "",
        # Campi extra referto UISP
        "gara_n": "",
        "girone": "",
        "arbitro_1": "",
        "arbitro_2": "",
        "ingresso_pagamento": False,
        "sponsor_a": "",
        "sponsor_b": "",
        "staff_a": {
            "allenatore": "", "tess_allenatore": "",
            "aiuto_allenatore": "", "tess_aiuto": "",
            "accompagnatore": "", "tess_accompagnatore": "",
            "dirigente": "", "tess_dirigente": "",
            "medico": "", "tess_medico": "",
            "dir_arbitri": "", "tess_dir_arbitri": "",
            "massaggiatore": "", "tess_massaggiatore": "",
            "scorer": "", "tess_scorer": "",
            "prep_fisico": "", "tess_prep_fisico": "",
        },
        "staff_b": {
            "allenatore": "", "tess_allenatore": "",
            "aiuto_allenatore": "", "tess_aiuto": "",
            "accompagnatore": "", "tess_accompagnatore": "",
            "dirigente": "", "tess_dirigente": "",
            "medico": "", "tess_medico": "",
            "dir_arbitri": "", "tess_dir_arbitri": "",
            "massaggiatore": "", "tess_massaggiatore": "",
            "scorer": "", "tess_scorer": "",
            "prep_fisico": "", "tess_prep_fisico": "",
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
ss = st.session_state

# ──────────────────────────────────────────────
#  UTILITY
# ──────────────────────────────────────────────
def player_key(team: str, num: str) -> str:
    return f"{team}_{num}"

def ensure_stats(team: str, num: str):
    k = player_key(team, num)
    if k not in ss.stats:
        ss.stats[k] = {"pts": 0, "fouls": 0}

def now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")

def quarter_label(q: int) -> str:
    labels = {1: "1 quarto", 2: "2 quarto", 3: "3 quarto", 4: "4 quarto"}
    return labels.get(q, f"Suppl. {q - 4}")

def add_points(team: str, player: dict, pts: int):
    ensure_stats(team, player["num"])
    ss.stats[player_key(team, player["num"])]["pts"] += pts
    if team == "A": ss.score_a += pts
    else:           ss.score_b += pts
    _log(team, player, f"+{pts} pt", pts)

def add_foul(team: str, player: dict):
    ensure_stats(team, player["num"])
    ss.stats[player_key(team, player["num"])]["fouls"] += 1
    if team == "A": ss.fouls_a += 1
    else:           ss.fouls_b += 1
    _log(team, player, "Fallo", 0)

def add_timeout(team: str):
    period = timeout_period(ss.quarter)
    ss.timeouts[team].setdefault(period, 0)
    ss.timeouts[team][period] += 1
    tname = ss[f"team_{team.lower()}_name"]
    ss.log.append({"time": now_str(), "quarter": ss.quarter,
                   "team": tname, "num": "—", "name": "—",
                   "event": f"Timeout ({period_label(period)})", "value": 0})

def timeouts_used(team: str) -> int:
    return ss.timeouts[team].get(timeout_period(ss.quarter), 0)

def timeouts_left(team: str) -> int:
    return max(0, timeout_max(ss.quarter) - timeouts_used(team))

def _log(team: str, player: dict, event: str, value: int):
    ss.log.append({"time": now_str(), "quarter": ss.quarter,
                   "team": ss[f"team_{team.lower()}_name"],
                   "num": player["num"], "name": player["name"],
                   "event": event, "value": value})

def undo_last():
    if not ss.log: return
    last = ss.log.pop()
    if last["num"] == "—": return   # evento di sistema
    team = "A" if last["team"] == ss.team_a_name else "B"
    k = player_key(team, last["num"])
    ensure_stats(team, last["num"])
    if last["event"].startswith("+"):
        pts = last["value"]
        ss.stats[k]["pts"] -= pts
        if team == "A": ss.score_a = max(0, ss.score_a - pts)
        else:           ss.score_b = max(0, ss.score_b - pts)
    elif last["event"] == "Fallo":
        ss.stats[k]["fouls"] = max(0, ss.stats[k]["fouls"] - 1)
        if team == "A": ss.fouls_a = max(0, ss.fouls_a - 1)
        else:           ss.fouls_b = max(0, ss.fouls_b - 1)

def next_quarter():
    t = now_str()
    ss.partials.append({"q": ss.quarter,
                        "score_a": ss.score_a - ss.quarter_start_a,
                        "score_b": ss.score_b - ss.quarter_start_b,
                        "to_a": timeouts_used("A"),
                        "to_b": timeouts_used("B")})
    if ss.current_quarter_start:
        ss.quarter_times.append({"q": ss.quarter,
                                  "start": ss.current_quarter_start, "end": t})
    ss.quarter += 1
    ss.current_quarter_start = t
    ss.quarter_start_a = ss.score_a
    ss.quarter_start_b = ss.score_b
    # falli si azzerano solo nei quarti regolamentari (non nei supplementari)
    if ss.quarter <= 4:
        ss.fouls_a = 0
        ss.fouls_b = 0
    ss.log.append({"time": t, "quarter": ss.quarter - 1,
                   "team": "—", "num": "—", "name": "—",
                   "event": f"Fine {quarter_label(ss.quarter-1)} / Inizio {quarter_label(ss.quarter)}",
                   "value": 0})

def end_game():
    t = now_str()
    ss.partials.append({"q": ss.quarter,
                        "score_a": ss.score_a - ss.quarter_start_a,
                        "score_b": ss.score_b - ss.quarter_start_b,
                        "to_a": timeouts_used("A"),
                        "to_b": timeouts_used("B")})
    if ss.current_quarter_start:
        ss.quarter_times.append({"q": ss.quarter,
                                  "start": ss.current_quarter_start, "end": t})
    ss.time_end = t
    ss.log.append({"time": t, "quarter": ss.quarter,
                   "team": "—", "num": "—", "name": "—",
                   "event": "FINE PARTITA", "value": 0})
    ss.phase = "ended"

# ──────────────────────────────────────────────
#  PDF
# ──────────────────────────────────────────────
def build_pdf() -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    BLUE   = colors.HexColor("#2d3561")
    LBLUE  = colors.HexColor("#eef3ff")
    LGREY  = colors.HexColor("#f7f7f7")
    RED    = colors.HexColor("#ff4b4b")
    TA     = colors.HexColor("#1a73e8")
    TB     = colors.HexColor("#e84118")

    def sty(name, **kw):
        base = {"fontName": "Helvetica", "fontSize": 10, "spaceAfter": 4}
        base.update(kw)
        return ParagraphStyle(name, **base)

    ts  = sty("t",  fontSize=18, fontName="Helvetica-Bold", alignment=TA_CENTER,
              textColor=BLUE, spaceAfter=4)
    ss2 = sty("s",  fontSize=10, alignment=TA_CENTER,
              textColor=colors.HexColor("#555555"), spaceAfter=6)
    h2  = sty("h2", fontSize=13, fontName="Helvetica-Bold",
              spaceBefore=14, spaceAfter=5, textColor=BLUE)
    sm  = sty("sm", fontSize=8,  textColor=colors.HexColor("#777777"),
              alignment=TA_CENTER)

    story = []

    # ── PAG 1: Intestazione + Risultato + Parziali ──────────────────────
    story.append(Paragraph("REFERTO PARTITA DI BASKET", ts))

    info_parts = [x for x in [ss.competition, ss.location,
                               ss.match_date.strftime("%d/%m/%Y")] if x]
    story.append(Paragraph("   |   ".join(info_parts), ss2))

    time_txt = []
    if ss.time_start: time_txt.append(f"Inizio: {ss.time_start}")
    if ss.time_end:   time_txt.append(f"Fine: {ss.time_end}")
    if time_txt:
        story.append(Paragraph("     ".join(time_txt), ss2))

    story.append(HRFlowable(width="100%", thickness=2, color=RED))
    story.append(Spacer(1, 10))

    # Punteggio finale
    status = "RISULTATO FINALE" if ss.phase == "ended" else "PUNTEGGIO IN CORSO"
    score_data = [
        [status, "", ""],
        [ss.team_a_name, "VS", ss.team_b_name],
        [str(ss.score_a), "", str(ss.score_b)],
    ]
    st_tbl = Table(score_data, colWidths=[7*cm, 3*cm, 7*cm])
    st_tbl.setStyle(TableStyle([
        ("SPAN",       (0,0), (2,0)),
        ("FONTNAME",   (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,0),  10),
        ("FONTSIZE",   (0,1), (-1,1),  14),
        ("FONTSIZE",   (0,2), (-1,2),  34),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TEXTCOLOR",  (0,0), (-1,0),  colors.HexColor("#888888")),
        ("TEXTCOLOR",  (0,2), (0,2),   TA),
        ("TEXTCOLOR",  (2,2), (2,2),   TB),
        ("BACKGROUND", (0,0), (-1,0),  colors.HexColor("#f5f5f5")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [LBLUE, colors.white]),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.lightgrey),
        ("TOPPADDING",    (0,2), (-1,2), 10),
        ("BOTTOMPADDING", (0,2), (-1,2), 10),
    ]))
    story.append(st_tbl)
    story.append(Spacer(1, 16))

    # Parziali
    if ss.partials:
        story.append(Paragraph("Parziali per quarto", h2))
        p_hdr = ["Periodo", "Orario", ss.team_a_name, ss.team_b_name]
        p_rows = [p_hdr]
        cum_a, cum_b = 0, 0
        for p in ss.partials:
            cum_a += p["score_a"]
            cum_b += p["score_b"]
            qt = next((x for x in ss.quarter_times if x["q"] == p["q"]), None)
            orario = f"{qt['start']} - {qt['end']}" if qt else "—"
            to_a = f"{p.get('to_a',0)} TO" if p.get("to_a",0) else "0 TO"
            to_b = f"{p.get('to_b',0)} TO" if p.get("to_b",0) else "0 TO"
            p_rows.append([
                quarter_label(p["q"]),
                orario,
                f"Parz: {p['score_a']}   Tot: {cum_a}\n{to_a}",
                f"Parz: {p['score_b']}   Tot: {cum_b}\n{to_b}",
            ])
        pt = Table(p_rows, colWidths=[3*cm, 4.5*cm, 5*cm, 5*cm])
        pt.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0),   BLUE),
            ("TEXTCOLOR",    (0,0), (-1,0),   colors.white),
            ("FONTNAME",     (0,0), (-1,0),   "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1),  9),
            ("ALIGN",        (0,0), (-1,-1),  "CENTER"),
            ("VALIGN",       (0,0), (-1,-1),  "MIDDLE"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LGREY]),
            ("GRID",         (0,0), (-1,-1),  0.4, colors.HexColor("#cccccc")),
            ("TOPPADDING",    (0,1), (-1,-1),  5),
            ("BOTTOMPADDING", (0,1), (-1,-1),  5),
        ]))
        story.append(pt)

    # ── PAG 2: Statistiche ──────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Statistiche giocatori", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))

    for tl, tname, players, chex in [
        ("A", ss.team_a_name, ss.players_a, "#1a73e8"),
        ("B", ss.team_b_name, ss.players_b, "#e84118"),
    ]:
        story.append(Paragraph(tname, ParagraphStyle(
            f"th{tl}", fontSize=12, fontName="Helvetica-Bold",
            spaceBefore=12, spaceAfter=4, textColor=colors.HexColor(chex)
        )))
        hdr = ["#", "Giocatore", "Data nasc.", "Punti", "Falli"]
        rows = [hdr]
        for p in sorted(players, key=lambda x: int(x["num"]) if x["num"].isdigit() else 0):
            k = player_key(tl, p["num"])
            s = ss.stats.get(k, {"pts": 0, "fouls": 0})
            rows.append([p["num"], p["name"], p.get("dob", "—"),
                         str(s["pts"]), str(s["fouls"])])
        tot_pts   = sum(ss.stats.get(player_key(tl, p["num"]), {"pts":0})["pts"]   for p in players)
        tot_fouls = sum(ss.stats.get(player_key(tl, p["num"]), {"fouls":0})["fouls"] for p in players)
        rows.append(["", "TOTALE", "", str(tot_pts), str(tot_fouls)])

        to_txt = "Timeout: " + (", ".join(
            f"{period_label(per)}: {n}"
            for per, n in sorted(ss.timeouts[tl].items())
        ) or "nessuno")
        rows.append(["", to_txt, "", "", ""])

        t = Table(rows, colWidths=[1.2*cm, 7*cm, 3.2*cm, 2.2*cm, 2.2*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0),   BLUE),
            ("TEXTCOLOR",   (0,0), (-1,0),   colors.white),
            ("FONTNAME",    (0,0), (-1,0),   "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1),  9),
            ("ALIGN",       (0,0), (-1,-1),  "CENTER"),
            ("ALIGN",       (1,1), (1,-1),   "LEFT"),
            ("ROWBACKGROUNDS", (0,1), (-1,-3), [colors.white, LGREY]),
            ("BACKGROUND",  (0,-2), (-1,-2), colors.HexColor("#e8f4e8")),
            ("FONTNAME",    (0,-2), (-1,-2), "Helvetica-Bold"),
            ("BACKGROUND",  (0,-1), (-1,-1), colors.HexColor("#fff8e1")),
            ("SPAN",        (1,-1), (4,-1)),
            ("GRID",        (0,0), (-1,-1),  0.4, colors.HexColor("#cccccc")),
        ]))
        story.append(t)

    # ── PAG 3: Log ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Cronologia eventi", h2))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 6))

    l_hdr = ["Ora", "Quarto", "Squadra", "#", "Giocatore", "Evento"]
    l_rows = [l_hdr] + [
        [e["time"], quarter_label(e["quarter"]), e["team"],
         e["num"], e["name"], e["event"]]
        for e in ss.log
    ]
    lt = Table(l_rows, colWidths=[1.8*cm, 2.5*cm, 4*cm, 1*cm, 4.5*cm, 3*cm], repeatRows=1)
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0),   BLUE),
        ("TEXTCOLOR",  (0,0), (-1,0),   colors.white),
        ("FONTNAME",   (0,0), (-1,0),   "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1),  8),
        ("ALIGN",      (0,0), (-1,-1),  "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LGREY]),
        ("GRID",       (0,0), (-1,-1),  0.3, colors.HexColor("#dddddd")),
    ]))
    story.append(lt)

    doc.build(story)
    buf.seek(0)
    return buf.read()

# ──────────────────────────────────────────────
#  CSV
# ──────────────────────────────────────────────
def build_csv() -> str:
    out = io.StringIO()
    w = csv.writer(out)
    # Metadati: righe commentate con # META per poter ricostruire la partita
    d = ss.match_date
    meta = [
        ("competition", ss.competition),
        ("location",    ss.location),
        ("match_date",  d.strftime("%d/%m/%Y") if d else ""),
        ("campo",       ss.campo),
        ("team_a",      ss.team_a_name),
        ("team_b",      ss.team_b_name),
    ]
    for key, val in meta:
        w.writerow([f"#META", key, val])
    # Roster squadra A
    for p in ss.players_a:
        w.writerow([f"#PLAYER_A", p["num"], p["name"], p.get("dob","—")])
    # Roster squadra B
    for p in ss.players_b:
        w.writerow([f"#PLAYER_B", p["num"], p["name"], p.get("dob","—")])
    # Log eventi
    w.writerow(["Ora", "Quarto", "Squadra", "Numero", "Giocatore", "Evento"])
    for e in ss.log:
        w.writerow([e["time"], quarter_label(e["quarter"]), e["team"],
                    e["num"], e["name"], e["event"]])
    return out.getvalue()


def parse_csv(content: str) -> dict | None:
    """Ricostruisce lo stato della partita da un CSV esportato dall'app."""
    from datetime import datetime as dt
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    meta       = {}
    players_a  = []
    players_b  = []
    log_rows   = []
    in_log     = False

    for row in rows:
        if not row: continue
        if row[0] == "#META" and len(row) >= 3:
            meta[row[1]] = row[2]
        elif row[0] == "#PLAYER_A" and len(row) >= 3:
            players_a.append({"num": row[1], "name": row[2],
                               "dob": row[3] if len(row)>3 else "—"})
        elif row[0] == "#PLAYER_B" and len(row) >= 3:
            players_b.append({"num": row[1], "name": row[2],
                               "dob": row[3] if len(row)>3 else "—"})
        elif row[0] == "Ora":
            in_log = True
        elif in_log and len(row) >= 6:
            log_rows.append({
                "time":    row[0],
                "quarter": row[1],
                "team":    row[2],
                "num":     row[3],
                "name":    row[4],
                "event":   row[5],
            })

    if not meta and not log_rows:
        return None

    team_a = meta.get("team_a", "Squadra A")
    team_b = meta.get("team_b", "Squadra B")

    # Ricostruisci statistiche dal log
    stats = {}
    score_a = score_b = 0
    partials_map  = {}  # quarter -> {score_a, score_b}
    qt_start_map  = {}  # quarter -> start time
    qt_end_map    = {}  # quarter -> end time
    timeouts      = {"A": {}, "B": {}}
    time_start    = None
    time_end      = None
    current_q     = 1
    q_score_start_a = q_score_start_b = 0

    def _period_key(q):
        if q <= 2:   return "1T"
        elif q <= 4: return "2T"
        else:        return f"S{q-4}"

    for e in log_rows:
        ev = e["event"]
        tm = e["team"]
        num = e["num"]

        # Prima riga = ora inizio
        if time_start is None and num != "—":
            time_start = e["time"]
        elif time_start is None and ev not in ("FINE PARTITA",):
            time_start = e["time"]

        # Prova a estrarre il numero di quarto
        try:
            q_str = e["quarter"]
            # "1 quarto" -> 1, "Suppl. 1" -> 5, ecc.
            q_map = {"1 quarto":1,"2 quarto":2,"3 quarto":3,"4 quarto":4}
            if q_str in q_map:
                q = q_map[q_str]
            elif "Suppl." in q_str:
                n = int(q_str.replace("Suppl.","").strip())
                q = 4 + n
            else:
                q = current_q
        except:
            q = current_q

        if q != current_q:
            # Cambio quarto
            partials_map[current_q] = {
                "q": current_q,
                "score_a": score_a - q_score_start_a,
                "score_b": score_b - q_score_start_b,
            }
            qt_end_map[current_q] = e["time"]
            qt_start_map[q] = e["time"]
            q_score_start_a = score_a
            q_score_start_b = score_b
            current_q = q

        if qt_start_map.get(current_q) is None and num != "—":
            qt_start_map[current_q] = e["time"]

        # Punti
        if ev.startswith("+") and "pt" in ev:
            try:
                pts = int(ev.split("+")[1].split(" ")[0])
            except:
                pts = 0
            tl = "A" if tm == team_a else "B"
            k = f"{tl}_{num}"
            if k not in stats: stats[k] = {"pts":0,"fouls":0}
            stats[k]["pts"] += pts
            if tl == "A": score_a += pts
            else:         score_b += pts

        # Fallo
        elif ev == "Fallo":
            tl = "A" if tm == team_a else "B"
            k = f"{tl}_{num}"
            if k not in stats: stats[k] = {"pts":0,"fouls":0}
            stats[k]["fouls"] += 1

        # Timeout
        elif "Timeout" in ev:
            tl = "A" if tm == team_a else "B"
            pk = _period_key(current_q)
            timeouts[tl].setdefault(pk, 0)
            timeouts[tl][pk] += 1

        # Fine partita
        elif ev == "FINE PARTITA":
            time_end = e["time"]
            partials_map[current_q] = {
                "q": current_q,
                "score_a": score_a - q_score_start_a,
                "score_b": score_b - q_score_start_b,
            }
            qt_end_map[current_q] = e["time"]

    # Assembla quarter_times
    quarter_times = []
    for qn in sorted(set(list(qt_start_map.keys()) + list(qt_end_map.keys()))):
        if qn in qt_start_map and qn in qt_end_map:
            quarter_times.append({"q": qn,
                                   "start": qt_start_map[qn],
                                   "end":   qt_end_map[qn]})

    partials = [partials_map[q] for q in sorted(partials_map.keys())]

    # Data partita
    try:
        from datetime import date as date_cls
        md = meta.get("match_date","")
        match_date = dt.strptime(md, "%d/%m/%Y").date() if md else date_cls.today()
    except:
        match_date = date.today()

    # Ricostruisci log nella struttura interna
    internal_log = []
    for e in log_rows:
        try:
            q_str = e["quarter"]
            q_map2 = {"1 quarto":1,"2 quarto":2,"3 quarto":3,"4 quarto":4}
            if q_str in q_map2: qn = q_map2[q_str]
            elif "Suppl." in q_str: qn = 4+int(q_str.replace("Suppl.","").strip())
            else: qn = 1
        except: qn = 1
        internal_log.append({
            "time":    e["time"],
            "quarter": qn,
            "team":    e["team"],
            "num":     e["num"],
            "name":    e["name"],
            "event":   e["event"],
            "value":   0,
        })

    return {
        "phase":        "ended" if time_end else "game",
        "competition":  meta.get("competition",""),
        "location":     meta.get("location",""),
        "match_date":   match_date,
        "campo":        meta.get("campo",""),
        "team_a_name":  team_a,
        "team_b_name":  team_b,
        "players_a":    players_a,
        "players_b":    players_b,
        "stats":        stats,
        "score_a":      score_a,
        "score_b":      score_b,
        "fouls_a":      0,
        "fouls_b":      0,
        "quarter":      current_q,
        "timeouts":     timeouts,
        "partials":     partials,
        "quarter_times":quarter_times,
        "time_start":   time_start or "",
        "time_end":     time_end or "",
        "log":          internal_log,
        "quarter_start_a": q_score_start_a,
        "quarter_start_b": q_score_start_b,
        "current_quarter_start": None,
        "confirm_end":  False,
    }

# ──────────────────────────────────────────────
#  SETUP
# ──────────────────────────────────────────────
def _staff_default():
    return {
        "allenatore": "", "tess_allenatore": "",
        "aiuto_allenatore": "", "tess_aiuto": "",
        "accompagnatore": "", "tess_accompagnatore": "",
        "dirigente": "", "tess_dirigente": "",
        "medico": "", "tess_medico": "",
        "dir_arbitri": "", "tess_dir_arbitri": "",
        "massaggiatore": "", "tess_massaggiatore": "",
        "scorer": "", "tess_scorer": "",
        "prep_fisico": "", "tess_prep_fisico": "",
    }


def render_uisp_fields(location="setup"):
    """Expander con tutti i campi extra del referto UISP.
    location: 'setup' (expanded) o 'sidebar' (collapsed)
    """
    # Assicura che staff_a/staff_b esistano con tutti i campi
    for key in ("staff_a", "staff_b"):
        if key not in ss or not isinstance(ss[key], dict):
            ss[key] = _staff_default()
        else:
            for k, v in _staff_default().items():
                ss[key].setdefault(k, v)

    expanded = (location == "setup")
    with st.expander("📋 Dati per referto UISP (arbitri, staff, ecc.)", expanded=expanded):

        # ── GARA / ARBITRI ────────────────────────────────────────
        st.markdown("**Gara & Arbitri**")
        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
        ss.gara_n   = c1.text_input("N° Gara",   value=ss.get("gara_n",""),   key=f"uisp_gara_n_{location}")
        ss.girone   = c2.text_input("Girone",     value=ss.get("girone",""),   key=f"uisp_girone_{location}")
        ss.arbitro_1 = c3.text_input("1° Arbitro", value=ss.get("arbitro_1",""), key=f"uisp_arb1_{location}")
        ss.arbitro_2 = c4.text_input("Arbitro 2", value=ss.get("arbitro_2",""), key=f"uisp_arb2_{location}")
        c5, c6 = st.columns([1, 3])
        ss.ingresso_pagamento = c5.checkbox(
            "Ingresso a pagamento", value=ss.get("ingresso_pagamento", False),
            key=f"uisp_ingresso_{location}")

        #st.divider()
        #
        ## ── SPONSOR ───────────────────────────────────────────────
        #st.markdown("**Sponsor**")
        #cs1, cs2 = st.columns(2)
        #ss.sponsor_a = cs1.text_input(
        #    f"Sponsor {ss.get('team_a_name','Squadra A')}",
        #    value=ss.get("sponsor_a",""), key=f"uisp_spa_{location}")
        #ss.sponsor_b = cs2.text_input(
        #    f"Sponsor {ss.get('team_b_name','Squadra B')}",
        #    value=ss.get("sponsor_b",""), key=f"uisp_spb_{location}")

        st.divider()

        # ── STAFF SQUADRE ─────────────────────────────────────────
        STAFF_ROLES = [
            ("allenatore",    "tess_allenatore",  "Allenatore"),
        #    ("aiuto_allenatore", "tess_aiuto",    "Aiuto Allenatore"),
        #    ("accompagnatore","tess_accompagnatore","Accompagnatore"),
        #    ("dirigente",     "tess_dirigente",   "2° Dirigente"),
        #    ("medico",        "tess_medico",      "Medico"),
        #    ("dir_arbitri",   "tess_dir_arbitri", "Dir. addetto arbitri"),
        #    ("massaggiatore", "tess_massaggiatore","Massaggiatore"),
        #    ("scorer",        "tess_scorer",      "Scorer"),
        #    ("prep_fisico",   "tess_prep_fisico", "Prep. Fisico"),
        ]

        col_a, col_b = st.columns(2)
        for col, letter, label in [(col_a, "a", ss.get("team_a_name","Squadra A")),
                                    (col_b, "b", ss.get("team_b_name","Squadra B"))]:
            with col:
                st.markdown(f"**Staff — {label}**")
                staff = ss[f"staff_{letter}"]
                for name_key, tess_key, role_label in STAFF_ROLES:
                    r1, r2 = st.columns([3, 2])
                    staff[name_key] = r1.text_input(
                        role_label, value=staff.get(name_key,""),
                        key=f"uisp_{letter}_{name_key}_{location}",
                        placeholder=role_label)
                    #staff[tess_key] = r2.text_input(
                    #    "Tessera", value=staff.get(tess_key,""),
                    #    key=f"uisp_{letter}_{tess_key}_{location}",
                    #    placeholder="N° tessera", label_visibility="collapsed")


def render_setup():
    st.title("🏀 Referto Basket — Impostazione partita")

    # ── IMPORT DA CSV ────────────────────────────────────────────
    with st.expander("📂 Riprendi da CSV (partita precedente)", expanded=False):
        st.caption("Carica un CSV esportato da una sessione precedente per rigenerare il referto UISP senza reinserire tutti i dati.")
        uploaded = st.file_uploader("Carica file CSV", type=["csv"], key="csv_import")
        if uploaded is not None:
            try:
                content = uploaded.read().decode("utf-8")
                parsed = parse_csv(content)
                if parsed is None:
                    st.error("File CSV non valido o formato non riconosciuto.")
                else:
                    col_p1, col_p2 = st.columns(2)
                    col_p1.success(f"✅ Trovato: **{parsed['team_a_name']}** vs **{parsed['team_b_name']}**")
                    col_p2.info(f"Punteggio: {parsed['score_a']} - {parsed['score_b']}  |  {len(parsed['players_a'])} + {len(parsed['players_b'])} giocatori  |  {len(parsed['partials'])} quarti")
                    bc1, bc2 = st.columns(2)
                    if bc1.button("⬆️ Carica e genera referto UISP", type="primary", use_container_width=True):
                        for k in list(ss.keys()): del ss[k]
                        for k, v in parsed.items(): ss[k] = v
                        st.rerun()
                    if bc2.button("▶️ Riprendi partita da questo punto", use_container_width=True):
                        for k in list(ss.keys()): del ss[k]
                        for k, v in parsed.items(): ss[k] = v
                        ss.phase = "game"
                        # Assicura che current_quarter_start sia impostato
                        if not ss.current_quarter_start:
                            qt = next((x for x in ss.quarter_times if x["q"] == ss.quarter), None)
                            ss.current_quarter_start = qt["start"] if qt else now_str()
                        st.rerun()
            except Exception as e:
                st.error(f"Errore nella lettura del CSV: {e}")

    st.divider()
    with st.expander("ℹ️ Informazioni partita", expanded=True):
        c1, c2, c3 = st.columns(3)
        ss.match_date  = c1.date_input("Data partita", value=ss.match_date)
        ss.location    = c2.text_input("Luogo / Palazzetto", value=ss.location)
        ss.competition = c3.text_input("Competizione", value=ss.competition)
        ss.campo       = st.text_input("Campo (per referto UISP)", value=ss.campo)

    render_uisp_fields(location="setup")

    st.divider()
    col_a, col_b = st.columns(2, gap="large")

    for col, letter in [(col_a, "A"), (col_b, "B")]:
        with col:
            ss[f"team_{letter.lower()}_name"] = st.text_input(
                f"Nome Squadra {letter}",
                value=ss[f"team_{letter.lower()}_name"],
                key=f"tname_{letter}"
            )
            st.subheader(f"Roster — {ss[f'team_{letter.lower()}_name']}")
            players: list = ss[f"players_{letter.lower()}"]

            with st.form(key=f"add_player_{letter}", clear_on_submit=True):
                fc1, fc2, fc3 = st.columns([1, 2, 2])
                num  = fc1.text_input("N°", placeholder="7")
                name = fc2.text_input("Nome", placeholder="Mario Rossi")
                dob  = fc3.text_input("Data nasc. (opz.)", placeholder="15/03/2001")
                if st.form_submit_button("➕ Aggiungi"):
                    if num and name:
                        if any(p["num"] == num for p in players):
                            st.error(f"Numero {num} gia' presente!")
                        else:
                            players.append({"num": num, "name": name, "dob": dob or "—"})
                            st.rerun()
                    else:
                        st.warning("Inserisci almeno numero e nome.")

            if players:
                for i, p in enumerate(players):
                    rc1, rc2, rc3, rc4 = st.columns([1, 3, 2, 1])
                    rc1.write(f"**#{p['num']}**")
                    rc2.write(p["name"])
                    rc3.write(p.get("dob", "—"))
                    if rc4.button("🗑️", key=f"del_{letter}_{i}"):
                        players.pop(i); st.rerun()
            else:
                st.info("Nessun giocatore ancora.")

    st.divider()
    if st.button("🏀 INIZIA PARTITA", type="primary", use_container_width=True):
        if not ss.players_a:
            st.error("Aggiungi almeno un giocatore alla Squadra A!")
        elif not ss.players_b:
            st.error("Aggiungi almeno un giocatore alla Squadra B!")
        else:
            ss.time_start = now_str()
            ss.current_quarter_start = ss.time_start
            ss.phase = "game"
            st.rerun()

# ──────────────────────────────────────────────
#  UISP PDF GENERATOR (referto da zero con ReportLab)
# ──────────────────────────────────────────────
#"""
#Generatore referto ufficiale UISP Basket.
#generate_uisp_pdf(ss_dict) -> bytes
#"""
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

PW, PH = A4
ML = 8*mm; MR = PW-8*mm; MT = PH-6*mm; MB = 6*mm
W  = MR - ML

BLACK = colors.black
LGREY = colors.HexColor("#dddddd")
DGREY = colors.HexColor("#444444")
HLGREY= colors.HexColor("#eeeeee")
BLUE_H= colors.HexColor("#cce0ff")
RED_H = colors.HexColor("#ffcccc")
BLUE_D= colors.HexColor("#3a6bbf")
RED_D = colors.HexColor("#cc3333")
HDR_BG= colors.HexColor("#e8e8e8")


def _quarter_label(q):
    return {1:"1° Periodo",2:"2° Periodo",3:"3° Periodo",4:"4° Periodo"}.get(q,f"Suppl.{q-4}")


def generate_uisp_pdf(ss: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Referto di Gara UISP Basket")
    _page1(c, ss)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


# ── low-level helpers ─────────────────────────────────────────────────────────
class Draw:
    def __init__(self, c):
        self.c = c

    def line(self, x1,y1,x2,y2, lw=0.3, col=BLACK):
        self.c.setLineWidth(lw); self.c.setStrokeColor(col)
        self.c.line(x1,y1,x2,y2)

    def rect(self, x,y,w,h, fill_col=None, stroke_col=BLACK, lw=0.3):
        self.c.setLineWidth(lw); self.c.setStrokeColor(stroke_col)
        if fill_col:
            self.c.setFillColor(fill_col); self.c.rect(x,y,w,h,fill=1,stroke=1)
        else:
            self.c.rect(x,y,w,h,fill=0,stroke=1)

    def txt(self, text, x, y, size=6.5, bold=False, align="left",
            color=BLACK, maxw=None):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        s = str(text)
        if maxw:
            while len(s)>1 and self.c.stringWidth(s,fn,size)>maxw:
                s=s[:-1]
        self.c.setFillColor(color); self.c.setFont(fn, size)
        if align=="center": self.c.drawCentredString(x,y,s)
        elif align=="right": self.c.drawRightString(x,y,s)
        else: self.c.drawString(x,y,s)

    def dots(self, x1, y, x2, size=5.5):
        fn="Helvetica"; self.c.setFont(fn,size)
        dw = self.c.stringWidth(".",fn,size)
        n = max(0, int((x2-x1)/dw))
        self.c.setFillColor(colors.HexColor("#aaaaaa"))
        self.c.drawString(x1, y, "."*n)
        self.c.setFillColor(BLACK)

    def val(self, text, x, y, maxw, size=7):
        if text: self.txt(str(text), x, y+0.8, size=size, maxw=maxw)


def _page1(c, ss):
    d = Draw(c)

    # ── HEADER ────────────────────────────────────────────────────────────────
    y = MT
    R = 5*mm   # row height base

    # Row 1: GARA N | UISP | REFERTO DI GARA
    H = R*1.1
    d.rect(ML, y-H, W, H, lw=0.8)
    d.line(ML+30*mm, y, ML+30*mm, y-H, lw=0.3)
    d.line(MR-52*mm, y, MR-52*mm, y-H, lw=0.3)
    d.txt("GARA N.", ML+1, y-H+1.8, size=7)
    d.val(ss.get("gara_n",""), ML+20*mm, y-H+1, 9*mm, size=7)
    d.txt("UISP  sportpertutti", PW/2, y-H+1.8, size=9, bold=True, align="center",
          color=colors.HexColor("#cc2200"))
    d.txt("REFERTO DI GARA", MR-51*mm, y-H+1.8, size=8, bold=True)
    y -= H

    # Row 2: Den.Soc. A | Den.Soc. B
    H = R
    d.rect(ML, y-H, W, H, lw=0.3)
    d.line(ML+W/2, y, ML+W/2, y-H, lw=0.3)
    d.txt("Denominazione Sociale", ML+1, y-H+1.5, size=6)
    d.dots(ML+37*mm, y-H+1.5, ML+W/2-1)
    d.val(ss.get("team_a_name",""), ML+38*mm, y-H+1, W/2-40*mm, size=7)
    d.txt("Denominazione Sociale", ML+W/2+1, y-H+1.5, size=6)
    d.dots(ML+W/2+37*mm, y-H+1.5, MR-1)
    d.val(ss.get("team_b_name",""), ML+W/2+38*mm, y-H+1, W/2-40*mm, size=7)
    y -= H

    # Row 3: Sponsor A | Sponsor B
    H = R*0.85
    d.rect(ML, y-H, W, H, lw=0.3)
    d.line(ML+W/2, y, ML+W/2, y-H, lw=0.3)
    d.txt("Sponsor", ML+1, y-H+1.5, size=6)
    d.dots(ML+14*mm, y-H+1.5, ML+W/2-1)
    d.val(ss.get("sponsor_a",""), ML+15*mm, y-H+1, W/2-17*mm, size=6)
    d.txt("Sponsor", ML+W/2+1, y-H+1.5, size=6)
    d.dots(ML+W/2+14*mm, y-H+1.5, MR-1)
    d.val(ss.get("sponsor_b",""), ML+W/2+15*mm, y-H+1, W/2-17*mm, size=6)
    y -= H

    # Row 4: Campionato | Località | 1°Arbitro | [Ingresso box]
    H = R*0.9
    CAMP_W = 65*mm; LOC_W = 65*mm; ARB_W = W-CAMP_W-LOC_W-20*mm; ING_W = 20*mm
    d.rect(ML, y-H, W-ING_W, H, lw=0.3)
    d.rect(MR-ING_W, y-H*2, ING_W, H*2, lw=0.5)
    d.line(ML+CAMP_W, y, ML+CAMP_W, y-H, lw=0.3)
    d.line(ML+CAMP_W+LOC_W, y, ML+CAMP_W+LOC_W, y-H, lw=0.3)
    d.txt("Campionato", ML+1, y-H+1.5, size=6)
    d.dots(ML+21*mm, y-H+1.5, ML+CAMP_W-1)
    d.val(ss.get("competition",""), ML+22*mm, y-H+1, CAMP_W-24*mm, size=6)
    d.txt("Località", ML+CAMP_W+1, y-H+1.5, size=6)
    d.dots(ML+CAMP_W+14*mm, y-H+1.5, ML+CAMP_W+LOC_W-1)
    d.val(ss.get("location",""), ML+CAMP_W+15*mm, y-H+1, LOC_W-17*mm, size=6)
    d.txt("1° Arbitro", ML+CAMP_W+LOC_W+1, y-H+1.5, size=6)
    d.dots(ML+CAMP_W+LOC_W+18*mm, y-H+1.5, MR-ING_W-1)
    d.txt("Ingresso a", MR-ING_W+1, y-H*0.4, size=5)
    d.txt("pagamento", MR-ING_W+1, y-H*0.8, size=5)
    # SI / NO
    bw = 5*mm
    d.rect(MR-ING_W+2, y-H*1.85, bw, bw*0.75, lw=0.5)
    if ss.get("ingresso_pagamento", False):
        d.txt("X", MR-ING_W+2+bw/2, y-H*1.35, size=6, align="center")
    d.txt("SI", MR-ING_W+2+bw+1, y-H*1.6, size=6)
    d.rect(MR-ING_W+2+bw*1.7, y-H*1.85, bw, bw*0.75, lw=0.5)
    if not ss.get("ingresso_pagamento", False):
        d.txt("X", MR-ING_W+2+bw*1.7+bw/2, y-H*1.35, size=6, align="center")
    d.txt("NO", MR-ING_W+2+bw*2.7+1, y-H*1.6, size=6)
    y -= H

    # Row 5: Data | Girone | Arbitro
    H = R*0.9
    d.rect(ML, y-H, W-ING_W, H, lw=0.3)
    d.line(ML+CAMP_W, y, ML+CAMP_W, y-H, lw=0.3)
    d.line(ML+CAMP_W+LOC_W, y, ML+CAMP_W+LOC_W, y-H, lw=0.3)
    d.txt("Data", ML+1, y-H+1.5, size=6)
    d_val = ss.get("match_date")
    d.val(d_val.strftime("%d/%m/%Y") if d_val else "", ML+9*mm, y-H+1, 25*mm, size=6)
    d.dots(ML+9*mm, y-H+1.5, ML+CAMP_W*0.55)
    d.txt("Girone", ML+CAMP_W*0.56, y-H+1.5, size=6)
    d.dots(ML+CAMP_W*0.56+12*mm, y-H+1.5, ML+CAMP_W-1)
    d.val(ss.get("girone",""), ML+CAMP_W*0.56+13*mm, y-H+1, ML+CAMP_W-ML-CAMP_W*0.56-14*mm, size=6)
    d.txt("Arbitro", ML+CAMP_W+LOC_W+1, y-H+1.5, size=6)
    d.dots(ML+CAMP_W+LOC_W+13*mm, y-H+1.5, MR-ING_W-1)
    d.val(ss.get("arbitro_1",""), ML+CAMP_W+LOC_W+14*mm, y-H+1, MR-ING_W-ML-CAMP_W-LOC_W-15*mm, size=6)
    y -= H

    # Row 6: Campo | Ore
    H = R*0.9
    d.rect(ML, y-H, W, H, lw=0.3)
    d.line(ML+115*mm, y, ML+115*mm, y-H, lw=0.3)
    d.txt("Campo", ML+1, y-H+1.5, size=6)
    d.dots(ML+11*mm, y-H+1.5, ML+115*mm-1)
    d.val(ss.get("campo",""), ML+12*mm, y-H+1, 102*mm, size=6)
    d.txt("Ore", ML+116*mm, y-H+1.5, size=6)
    d.dots(ML+123*mm, y-H+1.5, MR-1)
    d.val(ss.get("time_start",""), ML+124*mm, y-H+1, 30*mm, size=6)
    y -= H

    Y_BODY_TOP = y

    # ── LAYOUT BODY ───────────────────────────────────────────────────────────
    BOTTOM_H  = 38*mm
    Y_BODY_BOT= MB + BOTTOM_H
    BODY_H    = Y_BODY_TOP - Y_BODY_BOT

    ROSTER_W  = 98*mm
    SCORE_X   = ML + ROSTER_W
    SCORE_W   = W - ROSTER_W

    HALF_H = BODY_H / 2

    # Draw the two team rosters
    _draw_team(d, ss, "A", ML, Y_BODY_TOP, ROSTER_W, HALF_H)
    _draw_team(d, ss, "B", ML, Y_BODY_TOP-HALF_H, ROSTER_W, HALF_H)

    # Draw score grid
    _draw_score_grid(d, SCORE_X, Y_BODY_TOP, SCORE_W, BODY_H, ss)

    # Draw bottom section
    _draw_bottom(d, ML, MB, W, BOTTOM_H, ss)


def _draw_team(d, ss, letter, x0, y_top, w, h):
    team_name = ss.get(f"team_{letter.lower()}_name", f"Squadra {letter}")
    players   = ss.get(f"players_{letter.lower()}", [])
    stats     = ss.get("stats", {})

    # Outer border
    d.rect(x0, y_top-h, w, h, lw=0.7)

    # SQUADRA header row
    SH = 4*mm
    col1 = 0.62
    d.rect(x0, y_top-SH, w*col1, SH, fill_col=HDR_BG, lw=0.5)
    d.rect(x0, y_top-2*SH, w*col1, SH, fill_col=HDR_BG, lw=0.5)
    d.rect(x0+w*col1, y_top-2*SH, w, 2*SH, fill_col=HDR_BG, lw=0.5)
    d.txt(f"SQUADRA  {letter}", x0+2, y_top-SH+1.5, size=7.5, bold=True)
    d.txt(f"COLORE MAGLIA", x0+2, y_top-2*SH+1.5, size=6.5)
    d.txt("SOSPENSIONI", x0+w*0.73, y_top-SH-2, size=6.5, bold=True)

    # period foul boxes
    CH = 3.5*mm
    y_cm = y_top - 2*SH
    #d.rect(x0, y_cm-CH, w*0.58, CH, fill_col=colors.HexColor("#f5f5f5"), lw=0.3)
    #d.txt("COLORE MAGLIA", x0+2, y_cm-CH+1, size=5.5)

    # 4 periodi piccoli box (1°P + 5 caselle, poi 2°P + 5)
    PW2 = w*col1 / 12
    for pi, pl in enumerate(["1°P","1","2","3","4"," ","2°P","1","2","3","4"," "]):
        px = x0 + pi*PW2
        d.rect(px, y_cm-CH, PW2, CH, lw=0.15)
        d.txt(pl, px+PW2/2, y_cm-CH+0.8, size=5, align="center")

    y_cm2 = y_cm-CH
    CH2 = 3.5*mm
    for pi, pl in enumerate(["3°P","1","2","3","4"," ","4°P","1","2","3","4"," "]):
        px = x0 + pi*PW2
        d.rect(px, y_cm2-CH2, PW2, CH2, lw=0.15)
        d.txt(pl, px+PW2/2, y_cm2-CH2+0.8, size=5, align="center")
    
    # Sospensioni box 
    unit = (w * (1 - col1)) / 7 

    x_1 = x0 + w * col1
    d.rect(x_1, y_cm - CH, unit * 2, CH, lw=0.3)
    d.txt("1", x_1 + (unit * 2) / 2, y_cm - CH + 0.8, size=6, align="center")
    x_2 = x_1 + unit * 2
    d.rect(x_2, y_cm - CH, unit * 3, CH, lw=0.3)
    d.txt("2", x_2 + (unit * 3) / 2, y_cm - CH + 0.8, size=6, align="center")
    x_S = x_2 + unit * 3
    d.rect(x_S, y_cm - CH, unit * 2, CH, lw=0.3)
    d.txt("S", x_S + (unit * 2) / 2, y_cm - CH + 0.8, size=6, align="center")
    # riga sotto
    for i in range(2):
        d.rect(x_1 + (i * unit), y_cm2 - CH2, unit, CH2, lw=0.3)
    for i in range(3):
        d.rect(x_2 + (i * unit), y_cm2 - CH2, unit, CH2, lw=0.3)
    for i in range(2):
        d.rect(x_S + (i * unit), y_cm2 - CH2, unit, CH2, lw=0.3)
        
    y_hdr_bot = y_cm2-CH2

    # Column header
    HDR_H = 2*CH
    d.rect(x0, y_hdr_bot-HDR_H, w, HDR_H, fill_col=HDR_BG, lw=0.3)

    # Column layout: TESS(7)|COGNOME(24)|NOME(20)|NM(5)|E(5)|F1-5(5*5=25)  total=91 ~= 98mm
    COLS = [
        ("N°\nTESS",  PW2),
        ("GIOCATORE", (w*col1-PW2)*0.55),   # cognome
        ("",          (w*col1-PW2)*0.45),   # nome
        ("N.",         unit),   # numero maglia
        ("E.",         unit),   # espulsioni
        ("1",          unit),("2",unit),("3",unit),("4",unit),("5",unit),
    ]
    # adjust last to fill width
    used = sum(c2 for _,c2 in COLS)
    COLS[-1] = (COLS[-1][0], COLS[-1][1] + (w - used))

    cx = x0
    col_xs = []
    for ci,(cl,cw) in enumerate(COLS):
        col_xs.append(cx)
        if ci == 0:
            d.txt("N°",   cx+cw/2, y_hdr_bot-HDR_H*0.45, size=4.5, align="center")
            d.txt("TESS", cx+cw/2, y_hdr_bot-HDR_H*0.85, size=4.5, align="center")
        elif ci == 1:
            d.txt("GIOCATORE", cx+cw, y_hdr_bot-HDR_H*0.4, size=6.5, bold=True, align="center")
            d.txt("Cognome",   cx+cw/2, y_hdr_bot-HDR_H*0.85, size=5, align="center")
        elif ci == 2:
            d.txt("Nome", cx+cw/2, y_hdr_bot-HDR_H*0.85, size=5, align="center")
        elif ci == 3:
            d.txt("N.", cx+cw/2, y_hdr_bot-HDR_H*0.5, size=4.5, align="center")
            d.txt("N.", cx+cw/2, y_hdr_bot-HDR_H*0.85, size=4, align="center")
        elif ci == 4:
            d.txt("E.", cx+cw/2, y_hdr_bot-HDR_H*0.5, size=4.5, align="center")
        elif ci == 5:
            span = sum(c3 for _,c3 in COLS[5:])
            d.txt("FALLI", cx+span/2, y_hdr_bot-HDR_H*0.4, size=5.5, bold=True, align="center")
            for fi in range(5):
                d.txt(str(fi+1), cx+fi*unit+2.5*mm, y_hdr_bot-HDR_H*0.85, size=5, align="center")
        #if ci > 0:
        #    d.line(cx, y_hdr_bot, cx, y_hdr_bot-HDR_H, lw=0.2)
        cx += cw
    d.line(cx, y_hdr_bot, cx, y_hdr_bot-HDR_H, lw=0.2)

    # Player rows
    y_rows = y_hdr_bot - HDR_H
    remaining_h = y_rows - (y_top - h)
    N_ROWS = 12
    RH = remaining_h / (N_ROWS + 3.5)  # +3.5 for staff rows

    for ri in range(N_ROWS):
        ry = y_rows - ri*RH
        bg = colors.HexColor("#f8f8f8") if ri%2==1 else colors.white
        d.rect(x0, ry-RH, w, RH, fill_col=bg, lw=0)
        d.line(x0, ry-RH, x0+w, ry-RH, lw=0.2)
        # col separators
        for cxi in col_xs[1:]:
            d.line(cxi, ry, cxi, ry-RH, lw=0.15)
        d.line(x0+w, ry, x0+w, ry-RH, lw=0.2)

        if ri < len(players):
            p = players[ri]
            k = f"{letter}_{p['num']}"
            fouls = int(stats.get(k, {}).get("fouls", 0))
            full = p.get("name","")
            parts = full.split(" ",1)
            d.txt(str(p.get("num","")), col_xs[3]+COLS[3][1]/2, ry-RH+1, size=7, align="center")
            d.txt(parts[0], col_xs[1]+1, ry-RH+1, size=7, maxw=COLS[1][1]-2)
            if len(parts)>1:
                d.txt(parts[1], col_xs[2]+1, ry-RH+1, size=8, maxw=COLS[2][1]-2)
            for fi in range(min(fouls,5)):
                d.txt("X", col_xs[5+fi]+COLS[5+fi][1]/2, ry-RH+1,
                      size=7, bold=True, align="center", color=RED_D)

    # Staff rows — legge i valori da staff_a / staff_b
    staff = ss.get(f"staff_{letter.lower()}", {})
    y_staff = y_rows - N_ROWS*RH

    STAFF_MAIN = [
        ("All.re",       "allenatore",    "tess_allenatore"),
        ("Aiuto All.re", "aiuto_allenatore", "tess_aiuto"),
    ]
    for si, (role, name_key, tess_key) in enumerate(STAFF_MAIN):
        sy = y_staff - si*RH
        d.rect(x0, sy-RH, w*0.6, RH, lw=0.2)
        d.rect(x0+w*0.6, sy-RH, w*0.4, RH, lw=0.2)
        d.txt(role, x0+2, sy-RH+1, size=6)
        val_name = staff.get(name_key, "")
        val_tess = staff.get(tess_key, "")
        if val_name:
            d.txt(val_name, x0+18*mm, sy-RH+1, size=6, maxw=w*0.6-20*mm)
        d.txt("Tess.", x0+w*0.6+2, sy-RH+1, size=6)
        if val_tess:
            d.txt(val_tess, x0+w*0.6+14*mm, sy-RH+1, size=6, maxw=w*0.4-16*mm)
        else:
            d.dots(x0+w*0.6+12*mm, sy-RH+1, x0+w-2)

    STAFF_EXTRA = [
        ("Accompagnatore",       "accompagnatore",  "tess_accompagnatore"),
        ("2° Dirigente",         "dirigente",       "tess_dirigente"),
        ("Medico",               "medico",          "tess_medico"),
        ("Dir. addetto arbitri", "dir_arbitri",     "tess_dir_arbitri"),
        ("Massaggiatore",        "massaggiatore",   "tess_massaggiatore"),
        ("Scorer",               "scorer",          "tess_scorer"),
        ("Prep. Fisico",         "prep_fisico",     "tess_prep_fisico"),
    ]
    y_extra = y_staff - 2*RH
    for role, name_key, tess_key in STAFF_EXTRA:
        if y_extra - RH*0.85 < y_top-h: break
        d.rect(x0, y_extra-RH*0.85, w, RH*0.85, lw=0.15)
        d.txt(role, x0+2, y_extra-RH*0.85+1, size=6, maxw=w*0.38)
        val_name = staff.get(name_key, "")
        val_tess = staff.get(tess_key, "")
        if val_name:
            d.txt(val_name, x0+w*0.38+2, y_extra-RH*0.85+1, size=6, maxw=w*0.42)
        else:
            d.dots(x0+w*0.38, y_extra-RH*0.85+1, x0+w*0.79)
        d.txt("Tess.", x0+w*0.80, y_extra-RH*0.85+1, size=6)
        if val_tess:
            d.txt(val_tess, x0+w*0.80+10*mm, y_extra-RH*0.85+1, size=6, maxw=w*0.2-12*mm)
        else:
            d.dots(x0+w*0.80+9*mm, y_extra-RH*0.85+1, x0+w-2)
        y_extra -= RH*0.85


def _draw_score_grid(d, x0, y_top, w, h, ss):
    final_a = ss.get("score_a", 0)
    final_b = ss.get("score_b", 0)
    team_a  = ss.get("team_a_name", "")
    team_b  = ss.get("team_b_name", "")

    # ── Ricostruisce chi ha segnato: solo sul punto FINALE del canestro ──
    scorer_a = {}   # score_totale -> jersey string
    scorer_b = {}
    sa = sb = 0
    for ev in ss.get("log", []):
        event = ev.get("event", "")
        if not event.startswith("+") or "pt" not in event:
            continue
        try:
            pts = int(event.split("+")[1].split(" ")[0])
        except:
            continue
        jersey = str(ev.get("num", ""))
        if ev.get("team","") == team_a:
            sa += pts
            scorer_a[sa] = jersey   # solo sull'ultimo punto del canestro
        else:
            sb += pts
            scorer_b[sb] = jersey

    # ── Layout: [jersey_A | score_A | score_B | jersey_B] per 4 gruppi ──
    HDR_H = 4.5*mm
    SUB_H = 3.5*mm
    N_GROUPS = 4
    ROWS_PER = 40
    GW = w / N_GROUPS

    JW  = GW * 0.24   # colonna numero maglia A (e B)
    SAW = GW * 0.26   # colonna score A
    SBW = GW * 0.26   # colonna score B
    JBW = GW - JW - SAW - SBW   # colonna numero maglia B

    # Header principale
    d.rect(x0, y_top-HDR_H, w, HDR_H, fill_col=HDR_BG, lw=0.6)
    d.txt("PUNTEGGIO PROGRESSIVO", x0+w/2, y_top-HDR_H+1.5,
          size=7, bold=True, align="center")

    # Colori per quarto: Q1/Q3 rosso, Q2/Q4 blu (alternati)
    QC_LIGHT = [None,
                colors.HexColor("#ffd0d0"), colors.HexColor("#d0e4ff"),
                colors.HexColor("#ffd0d0"), colors.HexColor("#d0e4ff"),
                colors.HexColor("#ffd0d0"), colors.HexColor("#d0e4ff")]
    QC_DARK  = [None, RED_D, BLUE_D, RED_D, BLUE_D, RED_D, BLUE_D]
    QC_JRSY  = [None,
                colors.HexColor("#fff4f4"), colors.HexColor("#f4f8ff"),
                colors.HexColor("#fff4f4"), colors.HexColor("#f4f8ff"),
                colors.HexColor("#fff4f4"), colors.HexColor("#f4f8ff")]

    # Mappa: per ogni punto progressivo, in che quarto è stato segnato
    qt_of_a = {}; qt_of_b = {}
    _sa = _sb = 0
    for _ev in ss.get("log", []):
        _ev_str = _ev.get("event", "")
        if not _ev_str.startswith("+") or "pt" not in _ev_str:
            continue
        try: _pts = int(_ev_str.split("+")[1].split(" ")[0])
        except: continue
        _q = min(max(_ev.get("quarter", 1), 1), 6)
        if _ev.get("team","") == team_a:
            for _ in range(_pts):
                _sa += 1
                qt_of_a[_sa] = _q
        else:
            for _ in range(_pts):
                _sb += 1
                qt_of_b[_sb] = _q

    def _score_bg(num, final, qt_map):
        if num > final:   return colors.white
        q = qt_map.get(num, 1)
        return QC_DARK[q] if num == final else QC_LIGHT[q]

    def _jersey_bg(num, final, qt_map):
        if num > final: return colors.white
        return QC_JRSY[qt_map.get(num, 1)]

    # Sub-header: un rettangolo unificato A e uno B per ogni gruppo
    y_sub = y_top - HDR_H
    for gi in range(N_GROUPS):
        gx   = x0 + gi*GW
        x_sb = gx + JW + SAW
        d.rect(gx,   y_sub-SUB_H, JW+SAW,     SUB_H,
               fill_col=colors.HexColor("#dde8ff"), lw=0.4)
        d.rect(x_sb, y_sub-SUB_H, SBW+JBW,    SUB_H,
               fill_col=colors.HexColor("#ffdde0"), lw=0.4)
        d.txt("A", gx+(JW+SAW)/2,    y_sub-SUB_H+1, size=6, bold=True, align="center")
        d.txt("B", x_sb+(SBW+JBW)/2, y_sub-SUB_H+1, size=6, bold=True, align="center")

    y_grid = y_sub - SUB_H
    GRID_H = h - HDR_H - SUB_H
    RH = GRID_H / ROWS_PER

    for row_i in range(ROWS_PER):
        for gi in range(N_GROUPS):
            num  = gi * ROWS_PER + row_i + 1
            gx   = x0 + gi * GW
            ry   = y_grid - row_i * RH
            x_sa = gx + JW
            x_sb = gx + JW + SAW
            x_jb = gx + JW + SAW + SBW

            bg_sa = _score_bg(num, final_a, qt_of_a)
            bg_sb = _score_bg(num, final_b, qt_of_b)
            bg_ja = _jersey_bg(num, final_a, qt_of_a)
            bg_jb = _jersey_bg(num, final_b, qt_of_b)

            # Celle
            d.c.setLineWidth(0)
            d.c.setFillColor(bg_ja);  d.c.rect(gx,   ry-RH, JW,  RH, fill=1, stroke=0)
            d.c.setFillColor(bg_sa);  d.c.rect(x_sa, ry-RH, SAW, RH, fill=1, stroke=0)
            d.c.setFillColor(bg_sb);  d.c.rect(x_sb, ry-RH, SBW, RH, fill=1, stroke=0)
            d.c.setFillColor(bg_jb);  d.c.rect(x_jb, ry-RH, JBW, RH, fill=1, stroke=0)

            # Bordo riga
            d.c.setStrokeColor(LGREY); d.c.setLineWidth(0.15)
            d.c.line(gx, ry-RH, gx+GW, ry-RH)

            # Numeri score
            fs = 6.5 if num > 99 else 6.5
            d.txt(str(num), x_sa+SAW/2, ry-RH+0.8, size=fs, align="center",
                  color=colors.white if num == final_a else DGREY)
            d.txt(str(num), x_sb+SBW/2, ry-RH+0.8, size=fs, align="center",
                  color=colors.white if num == final_b else DGREY)

            # Numero maglia: SOLO sul punto finale del canestro
            j_a = scorer_a.get(num, "")
            j_b = scorer_b.get(num, "")
            if j_a:
                d.txt(j_a, gx+JW/2, ry-RH+0.8, size=7.5,
                      align="center", color=colors.HexColor("#1a3a7a"))
            if j_b:
                d.txt(j_b, x_jb+JBW/2, ry-RH+0.8, size=7.5,
                      align="center", color=colors.HexColor("#7a1a1a"))

    # Separatori verticali
    for gi in range(N_GROUPS):
        gx   = x0 + gi*GW
        x_sa = gx + JW
        x_sb = gx + JW + SAW
        x_jb = gx + JW + SAW + SBW
        d.line(x_sa, y_grid, x_sa, y_grid-ROWS_PER*RH, lw=0.3)
        d.line(x_sb, y_grid, x_sb, y_grid-ROWS_PER*RH, lw=0.3)
        d.line(x_jb, y_grid, x_jb, y_grid-ROWS_PER*RH, lw=0.3)
    for gi in range(N_GROUPS+1):
        d.line(x0+gi*GW, y_grid, x0+gi*GW, y_grid-ROWS_PER*RH, lw=0.6)

    # Bordo esterno
    d.rect(x0, y_grid-ROWS_PER*RH, w, ROWS_PER*RH+HDR_H+SUB_H, lw=0.8)


def _draw_bottom(d, x0, y0, w, h, ss):
    LEFT_W = 98*mm; RIGHT_W = w - LEFT_W
    d.rect(x0, y0, w, h, lw=0.7)
    d.line(x0+LEFT_W, y0, x0+LEFT_W, y0+h, lw=0.5)

    y_top = y0+h
    PART_W = RIGHT_W*0.62; TIME_W = RIGHT_W-PART_W
    rx0 = x0+LEFT_W

    # ── SINISTRA ──
    RH = h/7
    roles = ["Cronometr.", "Segnapunti.", "Addetto 24\""]
    for ri,role in enumerate(roles):
        ry = y_top - ri*RH
        d.line(x0, ry-RH, x0+LEFT_W, ry-RH, lw=0.2)
        d.txt(role, x0+2, ry-RH+1.5, size=6)
        d.dots(x0+27*mm, ry-RH+1.5, x0+LEFT_W*0.62)
        d.txt("TESS. UISP", x0+LEFT_W*0.63, ry-RH+1.5, size=5.5)
        d.dots(x0+LEFT_W*0.63+14*mm, ry-RH+1.5, x0+LEFT_W-2)

    # Risultato finale
    RF_Y = y_top - 3*RH
    d.rect(x0, RF_Y-RH*0.65, LEFT_W*0.44, RH*0.65, fill_col=HDR_BG, lw=0.4)
    d.txt("RISULTATO FINALE", x0+2, RF_Y-RH*0.65+1.5, size=5.5, bold=True)
    sa=ss.get("score_a",0); sb=ss.get("score_b",0)
    d.txt(f"{sa}  -  {sb}", x0+14*mm, RF_Y-RH-RH*0.65, size=12, bold=True,
          color=colors.HexColor("#2d3561"))
    d.line(x0+LEFT_W*0.44, RF_Y, x0+LEFT_W*0.44, y0+2*RH, lw=0.3)
    d.rect(x0+LEFT_W*0.44, RF_Y-RH*0.65, LEFT_W*0.56, RH*0.65, fill_col=HDR_BG, lw=0.4)
    d.txt("SQUADRA VINCENTE", x0+LEFT_W*0.44+2, RF_Y-RH*0.65+1.5, size=5.5, bold=True)
    vincente = (ss.get("team_a_name","") if sa>sb
                else ss.get("team_b_name","") if sb>sa else "Pari")
    d.txt(vincente, x0+LEFT_W*0.44+3*mm, RF_Y-RH-RH*0.65, size=9, bold=True,
          color=colors.HexColor("#2d3561"), maxw=LEFT_W*0.56-5*mm)

    # Firma capitano
    FIRM_Y = y_top - 5*RH
    d.line(x0, FIRM_Y, x0+LEFT_W, FIRM_Y, lw=0.2)
    #d.txt("Firma del capitano che intende presentare reclamo avverso il risultato di gara",
    #      x0+2, FIRM_Y-2*mm, size=5)
    #d.txt("per la società", x0+2, FIRM_Y-4.5*mm, size=5.5)
    #d.dots(x0+22*mm, FIRM_Y-4.5*mm, x0+LEFT_W*0.7)
    #d.txt("il capitano", x0+2, FIRM_Y-7*mm, size=5.5)
    #d.dots(x0+18*mm, FIRM_Y-7*mm, x0+LEFT_W*0.7)

    # ── DESTRA: risultati parziali + orari ──
    d.rect(rx0, y_top-RH*0.55, RIGHT_W, RH*0.55, fill_col=HDR_BG, lw=0.3)
    d.txt("RISULTATI PARZIALI", rx0+2, y_top-RH*0.55+1.5, size=7, bold=True)
    d.line(rx0+PART_W, y0, rx0+PART_W, y_top, lw=0.3)
    d.line(rx0+PART_W+TIME_W/2, y0, rx0+PART_W+TIME_W/2, y_top, lw=0.3)
    d.txt("INIZIO", rx0+PART_W+2, y_top-RH*0.55+1.5, size=6, bold=True)
    d.txt("FINE",   rx0+PART_W+TIME_W/2+2, y_top-RH*0.55+1.5, size=6, bold=True)

    partials = ss.get("partials",[])
    qt_list  = ss.get("quarter_times",[])
    P_LABELS = ["1° Periodo A","2° Periodo A","3° Periodo A","4° Periodo A","Supplem. A"]
    PR_H = (h - RH*0.55) / 5.3
    cum_a2=cum_b2=0

    for ri2,lbl in enumerate(P_LABELS):
        ry2 = y_top - RH*0.55 - ri2*PR_H
        d.line(rx0, ry2-PR_H, rx0+RIGHT_W, ry2-PR_H, lw=0.2)
        d.txt(lbl, rx0+2, ry2-PR_H+1.5, size=7.5)
        d.dots(rx0+20*mm, ry2-PR_H+1.5, rx0+PART_W*0.5)
        d.txt("B", rx0+PART_W*0.51, ry2-PR_H+1.5, size=7.5)
        d.dots(rx0+PART_W*0.53, ry2-PR_H+1.5, rx0+PART_W-2)

        if ri2 < len(partials):
            p = partials[ri2]
            cum_a2+=p.get("score_a",0); cum_b2+=p.get("score_b",0)
            d.txt(str(cum_a2), rx0+PART_W*0.42, ry2-PR_H+1.5, size=9, bold=True)
            d.txt(str(cum_b2), rx0+PART_W*0.68, ry2-PR_H+1.5, size=9, bold=True)
            qt = next((x for x in qt_list if x["q"]==p["q"]), None)
            if qt:
                d.txt(qt.get("start",""), rx0+PART_W+2, ry2-PR_H+1.5, size=7.5)
                d.txt(qt.get("end",""),   rx0+PART_W+TIME_W/2+2, ry2-PR_H+1.5, size=7.5)

    # Firme arbitri
    #d.txt("Firma 1° Arbitro", rx0+2, y0+4*mm, size=5.5)
    #d.dots(rx0+24*mm, y0+4*mm, rx0+RIGHT_W-2)
    #d.txt("Firma Arbitro",    rx0+2, y0+1.5*mm, size=5.5)
    #d.dots(rx0+21*mm, y0+1.5*mm, rx0+RIGHT_W-2)





# ──────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────
def render_sidebar(game_active: bool):
    with st.sidebar:
        #st.header("Azioni")
        #
        #render_uisp_fields(location="sidebar")
        #st.divider()

        # Referto ufficiale UISP (generato da zero)
        fname_base = f"referto_{ss.match_date.strftime('%Y%m%d')}"
        st.subheader("Referto UISP")
        try:
            ss_dict = {k: ss[k] for k in ["team_a_name","team_b_name","players_a","players_b",
                                           "stats","score_a","score_b","partials","quarter_times",
                                           "match_date","competition","location","campo",
                                           "time_start","phase","log"]}
            uisp_bytes = generate_uisp_pdf(ss_dict)
            st.download_button(
                "Scarica referto UISP",
                data=uisp_bytes,
                file_name=f"referto_uisp_{fname_base}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Errore UISP: {e}")

        st.subheader("Export")
        pdf_bytes = build_pdf()
        #st.download_button("Scarica referto PDF", data=pdf_bytes,
        #                   file_name=f"{fname_base}.pdf",
        #                   mime="application/pdf", use_container_width=True)
        st.download_button("Scarica log CSV", data=build_csv(),
                           file_name=f"{fname_base}.csv",
                           mime="text/csv", use_container_width=True)

        st.divider()
        st.subheader("Partita")
        if game_active:
            if st.button("Annulla ultima azione", use_container_width=True):
                undo_last(); st.rerun()

            #st.divider()
            st.write(f"**Quarto corrente:** {quarter_label(ss.quarter)}")
            if st.button("Prossimo quarto / Supplementare", use_container_width=True):
                next_quarter(); st.rerun()

            st.divider()
            st.subheader("Fine partita")
            if st.button("TERMINA PARTITA", type="primary", use_container_width=True):
                ss.confirm_end = True
            if ss.confirm_end:
                st.warning("Terminare la partita?")
                c1, c2 = st.columns(2)
                if c1.button("Si, termina", use_container_width=True):
                    end_game(); ss.confirm_end = False; st.rerun()
                if c2.button("Annulla", use_container_width=True):
                    ss.confirm_end = False; st.rerun()

        st.divider()
        if st.button("Nuova partita (reset)", use_container_width=True):
            for k in list(ss.keys()): del ss[k]
            st.rerun()



# ──────────────────────────────────────────────
#  PARTITA
# ──────────────────────────────────────────────
def render_game():
    render_sidebar(game_active=True)
    st.title(f"🏀 {quarter_label(ss.quarter).upper()}")
    if ss.time_start:
        st.caption(f"Inizio partita: {ss.time_start}")

    sc1, sc2, sc3 = st.columns([5, 2, 5])
    with sc1:
        st.markdown(f"<div class='team-name'>{ss.team_a_name}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='big-score' style='color:#1a73e8'>{ss.score_a}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<center>Falli squadra: <span class='foul-badge'>{ss.fouls_a}</span>"
            f" &nbsp; Timeout rimasti: <span class='to-badge'>{timeouts_left('A')}</span></center>",
            unsafe_allow_html=True)
    with sc2:
        st.markdown("<div style='font-size:2rem;text-align:center;padding-top:30px'>VS</div>",
                    unsafe_allow_html=True)
    with sc3:
        st.markdown(f"<div class='team-name'>{ss.team_b_name}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='big-score' style='color:#e84118'>{ss.score_b}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<center>Falli squadra: <span class='foul-badge'>{ss.fouls_b}</span>"
            f" &nbsp; Timeout rimasti: <span class='to-badge'>{timeouts_left('B')}</span></center>",
            unsafe_allow_html=True)

    st.divider()

    def team_panel(team_letter: str):
        team_name = ss[f"team_{team_letter.lower()}_name"]
        players   = ss[f"players_{team_letter.lower()}"]
        color     = "#1a73e8" if team_letter == "A" else "#e84118"

        st.markdown(f"<h3 style='color:{color}'>{team_name}</h3>", unsafe_allow_html=True)
        options = [f"#{p['num']} {p['name']}" for p in players]
        sel = st.selectbox("Seleziona giocatore", options,
                           key=f"sel_{team_letter}", index=0 if options else None)
        if sel is None:
            st.info("Nessun giocatore."); return

        player = players[options.index(sel)]
        k = player_key(team_letter, player["num"])
        ensure_stats(team_letter, player["num"])
        st.caption(f"Punti: **{ss.stats[k]['pts']}** | Falli: **{ss.stats[k]['fouls']}**")

        b1, b2, b3, b4 = st.columns(4)
        if b1.button("+1", key=f"p1_{team_letter}", use_container_width=True):
            add_points(team_letter, player, 1); st.rerun()
        if b2.button("+2", key=f"p2_{team_letter}", use_container_width=True):
            add_points(team_letter, player, 2); st.rerun()
        if b3.button("+3", key=f"p3_{team_letter}", use_container_width=True):
            add_points(team_letter, player, 3); st.rerun()
        if b4.button("Fallo", key=f"f_{team_letter}", use_container_width=True):
            add_foul(team_letter, player); st.rerun()

        left = timeouts_left(team_letter)
        if st.button(f"Timeout  ({left} rimanenti)",
                     key=f"to_{team_letter}", use_container_width=True,
                     disabled=(left == 0)):
            add_timeout(team_letter); st.rerun()

        with st.expander("Stat giocatori", expanded=False):
            import pandas as pd
            rows = [{"#": p["num"], "Giocatore": p["name"],
                     "Punti": ss.stats.get(player_key(team_letter, p["num"]), {"pts":0})["pts"],
                     "Falli": ss.stats.get(player_key(team_letter, p["num"]), {"fouls":0})["fouls"]}
                    for p in players]
            if rows:
                st.dataframe(pd.DataFrame(rows).sort_values("Punti", ascending=False),
                             hide_index=True, use_container_width=True)

    pa, pb = st.columns(2, gap="large")
    with pa: team_panel("A")
    with pb: team_panel("B")

    st.divider()
    _render_log()

# ──────────────────────────────────────────────
#  PARTITA TERMINATA
# ──────────────────────────────────────────────
def resume_game():
    """Riprende la partita: rimuove l'evento FINE PARTITA e torna allo stato game."""
    # Rimuovi l'ultimo evento FINE PARTITA dal log
    if ss.log and ss.log[-1]["event"] == "FINE PARTITA":
        ss.log.pop()
    # Rimuovi l'ultimo parziale (quello salvato al momento della fine)
    if ss.partials:
        last_p = ss.partials[-1]
        # Ripristina i contatori di quarto
        ss.quarter_start_a = ss.score_a - last_p["score_a"]
        ss.quarter_start_b = ss.score_b - last_p["score_b"]
        ss.partials.pop()
    # Ripristina il tempo di inizio quarto corrente
    qt = next((x for x in ss.quarter_times if x["q"] == ss.quarter), None)
    if qt:
        ss.current_quarter_start = qt["start"]
        ss.quarter_times = [x for x in ss.quarter_times if x["q"] != ss.quarter]
    ss.time_end = ""
    ss.phase = "game"


def render_ended():
    render_sidebar(game_active=False)

    st.markdown(
        f"<div class='ended-banner'>PARTITA TERMINATA — "
        f"{ss.team_a_name} {ss.score_a} : {ss.score_b} {ss.team_b_name}</div>",
        unsafe_allow_html=True)
    if ss.time_start:
        st.caption(f"Inizio: {ss.time_start}   |   Fine: {ss.time_end}")

    if st.button("↩️ Riprendi partita", use_container_width=True):
        resume_game()
        st.rerun()

    if ss.partials:
        import pandas as pd
        st.subheader("Parziali")
        cum_a, cum_b = 0, 0
        rows = []
        for p in ss.partials:
            cum_a += p["score_a"]; cum_b += p["score_b"]
            qt = next((x for x in ss.quarter_times if x["q"] == p["q"]), None)
            rows.append({
                "Quarto": quarter_label(p["q"]),
                "Inizio": qt["start"] if qt else "—",
                "Fine":   qt["end"]   if qt else "—",
                f"Parz. {ss.team_a_name}": p["score_a"],
                f"Tot. {ss.team_a_name}":  cum_a,
                f"TO {ss.team_a_name}":    p.get("to_a", 0),
                f"Parz. {ss.team_b_name}": p["score_b"],
                f"Tot. {ss.team_b_name}":  cum_b,
                f"TO {ss.team_b_name}":    p.get("to_b", 0),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.divider()
    _render_log()

# ──────────────────────────────────────────────
#  LOG
# ──────────────────────────────────────────────
def _render_log():
    st.subheader("Cronologia eventi")
    if not ss.log:
        st.info("Nessun evento registrato."); return
    for e in reversed(ss.log[-60:]):
        ev = e["event"]
        if e["num"] == "—" or ev == "FINE PARTITA":
            icon = "⚪"
        elif "Timeout" in ev:
            icon = "🕐"
        elif ev == "Fallo":
            icon = "🟠"
        else:
            icon = "🟢"
        st.markdown(
            f"<div class='log-entry'>{icon} <b>{e['time']}</b> "
            f"[{quarter_label(e['quarter'])}] "
            f"<b>{e['team']}</b> — #{e['num']} {e['name']} — {ev}</div>",
            unsafe_allow_html=True)

# ──────────────────────────────────────────────
#  ROUTER
# ──────────────────────────────────────────────
if ss.phase == "setup":
    render_setup()
elif ss.phase == "game":
    render_game()
else:
    render_ended()