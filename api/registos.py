import json
import os
from http.server import BaseHTTPRequestHandler
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

COLUMNS = [
    "ID", "Idade", "Sexo", "Município", "Doença de Base",
    "Tipo de Ferida", "Localização", "Tempo de Evolução (dias)",
    "Tamanho (cm)", "Profundidade", "Infecção (Sim/Não)",
    "Tratamento", "Data Início", "Data Avaliação", "Evolução",
    "Cicatrização (Sim/Não)", "Complicações", "Desfecho"
]

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS não configurado nas variáveis de ambiente do Vercel.")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet_id = os.environ.get("SHEET_ID")
    if not sheet_id:
        raise Exception("SHEET_ID não configurado nas variáveis de ambiente do Vercel.")
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.sheet1

def rows_to_dicts(sheet):
    records = sheet.get_all_records()
    return records

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json"
    }

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        try:
            sheet = get_sheet()
            path = self.path.split("?")[0]

            if path == "/api/registos":
                records = rows_to_dicts(sheet)
                body = json.dumps(records, ensure_ascii=False)
                self._respond(200, body)

            elif path == "/api/estatisticas":
                records = rows_to_dicts(sheet)
                stats = {"total": len(records), "por_sexo": {}, "por_tipo_ferida": {}, "infeccao": {}, "cicatrizacao": {}}
                for r in records:
                    for field, key in [("Sexo","por_sexo"),("Tipo de Ferida","por_tipo_ferida"),("Infecção (Sim/Não)","infeccao"),("Cicatrização (Sim/Não)","cicatrizacao")]:
                        v = str(r.get(field, "")).strip()
                        if v:
                            stats[key][v] = stats[key].get(v, 0) + 1
                self._respond(200, json.dumps(stats, ensure_ascii=False))
            else:
                self._respond(404, json.dumps({"error": "Rota não encontrada"}))
        except Exception as e:
            self._respond(500, json.dumps({"error": str(e)}))

    def do_POST(self):
        try:
            sheet = get_sheet()
            data = self._read_body()
            records = rows_to_dicts(sheet)
            ids = [int(r.get("ID", 0)) for r in records if str(r.get("ID","")).isdigit()]
            next_id = max(ids) + 1 if ids else 1
            data["ID"] = next_id
            row = [str(data.get(col, "")) for col in COLUMNS]

            # If sheet is empty, add header row first
            if sheet.row_count == 0 or not sheet.row_values(1):
                sheet.append_row(COLUMNS)
            sheet.append_row(row)
            self._respond(201, json.dumps({"message": "Registo adicionado com sucesso!", "id": next_id}, ensure_ascii=False))
        except Exception as e:
            self._respond(500, json.dumps({"error": str(e)}))

    def do_PUT(self):
        try:
            sheet = get_sheet()
            # Extract ID from path: /api/registos/5
            parts = self.path.rstrip("/").split("/")
            record_id = parts[-1]
            data = self._read_body()
            all_values = sheet.get_all_values()
            if not all_values:
                self._respond(404, json.dumps({"error": "Folha vazia"}))
                return
            header = all_values[0]
            id_col = header.index("ID") + 1 if "ID" in header else 1
            for i, row in enumerate(all_values[1:], start=2):
                if str(row[id_col-1]) == str(record_id):
                    new_row = [str(data.get(col, row[j] if j < len(row) else "")) for j, col in enumerate(header)]
                    sheet.update(f"A{i}", [new_row])
                    self._respond(200, json.dumps({"message": "Registo actualizado!"}, ensure_ascii=False))
                    return
            self._respond(404, json.dumps({"error": "Registo não encontrado"}))
        except Exception as e:
            self._respond(500, json.dumps({"error": str(e)}))

    def do_DELETE(self):
        try:
            sheet = get_sheet()
            parts = self.path.rstrip("/").split("/")
            record_id = parts[-1]
            all_values = sheet.get_all_values()
            if not all_values:
                self._respond(404, json.dumps({"error": "Folha vazia"}))
                return
            header = all_values[0]
            id_col = header.index("ID") if "ID" in header else 0
            for i, row in enumerate(all_values[1:], start=2):
                if str(row[id_col]) == str(record_id):
                    sheet.delete_rows(i)
                    self._respond(200, json.dumps({"message": "Registo eliminado!"}, ensure_ascii=False))
                    return
            self._respond(404, json.dumps({"error": "Registo não encontrado"}))
        except Exception as e:
            self._respond(500, json.dumps({"error": str(e)}))

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        return json.loads(body)

    def _respond(self, code, body):
        self.send_response(code)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass
