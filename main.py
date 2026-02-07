from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import uvicorn
import logging
from contextlib import closing

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Meu Controle Financeiro")

# Montando arquivos estáticos (se houver CSS/JS externos)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configurando templates
templates = Jinja2Templates(directory="templates")

DATABASE = 'financeiro.db'

def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")

def init_db():
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS gastos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        descricao TEXT NOT NULL,
                        valor REAL NOT NULL,
                        categoria TEXT NOT NULL,
                        data DATE DEFAULT (date('now'))
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS renda (
                        id INTEGER PRIMARY KEY,
                        valor REAL NOT NULL DEFAULT 0.0
                    )
                ''')
                conn.execute("INSERT OR IGNORE INTO renda (id, valor) VALUES (1, 0.0)")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")

# Inicializa o banco ao iniciar
init_db()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        with closing(get_db_connection()) as conn:
            # Selects don't need transaction context, but closing is important
            gastos = conn.execute("SELECT * FROM gastos ORDER BY id DESC").fetchall()
            categorias_db = conn.execute("SELECT categoria, SUM(valor) as total FROM gastos GROUP BY categoria").fetchall()
            renda_row = conn.execute("SELECT valor FROM renda WHERE id = 1").fetchone()
            renda_mensal = renda_row['valor'] if renda_row else 0.0

        labels = [row['categoria'] for row in categorias_db]
        data = [row['total'] for row in categorias_db]
        total_geral = sum(data)
        saldo_estimado = renda_mensal - total_geral

        return templates.TemplateResponse("index.html", {
            "request": request,
            "gastos": gastos,
            "labels": labels,
            "data": data,
            "total_geral": total_geral,
            "renda_mensal": renda_mensal,
            "saldo_estimado": saldo_estimado
        })
    except Exception as e:
        logger.error(f"Erro na home: {e}")
        return HTMLResponse(content="<h1>Erro interno</h1>", status_code=500)

@app.post("/definir_renda")
async def definir_renda(renda: float = Form(...)):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("UPDATE renda SET valor = ? WHERE id = 1", (renda,))
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"Erro ao definir renda: {e}")
        raise HTTPException(status_code=500, detail="Erro ao definir renda")

@app.post("/adicionar")
async def adicionar(descricao: str = Form(...), valor: float = Form(...), categoria: str = Form(...)):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("INSERT INTO gastos (descricao, valor, categoria) VALUES (?, ?, ?)",
                             (descricao, valor, categoria))
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"Erro ao adicionar: {e}")
        raise HTTPException(status_code=500, detail="Erro ao adicionar despesa")

@app.post("/deletar/{id}")
async def deletar(id: int):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("DELETE FROM gastos WHERE id = ?", (id,))
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"Erro ao deletar: {e}")
        raise HTTPException(status_code=500, detail="Erro ao deletar despesa")

if __name__ == "__main__":
    # Roda no servidor local, porta 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
