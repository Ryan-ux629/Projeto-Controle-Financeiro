from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import uvicorn
import logging
from contextlib import closing
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional
import uuid

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
                # Create table with new schema if not exists
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS gastos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        descricao TEXT NOT NULL,
                        valor REAL NOT NULL,
                        categoria TEXT NOT NULL,
                        data DATE DEFAULT (date('now')),
                        parcela_atual INTEGER DEFAULT 1,
                        total_parcelas INTEGER DEFAULT 1,
                        agrupamento_id TEXT
                    )
                ''')

                # Check for new columns and add if missing (simple migration)
                try:
                    conn.execute("ALTER TABLE gastos ADD COLUMN parcela_atual INTEGER DEFAULT 1")
                except sqlite3.OperationalError:
                    pass # Column likely exists

                try:
                    conn.execute("ALTER TABLE gastos ADD COLUMN total_parcelas INTEGER DEFAULT 1")
                except sqlite3.OperationalError:
                    pass # Column likely exists

                try:
                    conn.execute("ALTER TABLE gastos ADD COLUMN agrupamento_id TEXT")
                except sqlite3.OperationalError:
                    pass # Column likely exists

                conn.execute('''
                    CREATE TABLE IF NOT EXISTS renda (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        descricao TEXT,
                        valor REAL NOT NULL DEFAULT 0.0
                    )
                ''')

                # Check for new column in existing DB (if migrating)
                try:
                    conn.execute("ALTER TABLE renda ADD COLUMN descricao TEXT")
                except sqlite3.OperationalError:
                    pass

                # Remove the default single row assumption if it exists and has no description?
                # For now, we will just start inserting new rows.
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")

# Inicializa o banco ao iniciar
init_db()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, mes: Optional[int] = Query(None), ano: Optional[int] = Query(None)):
    try:
        today = datetime.now()
        current_mes = mes if mes else today.month
        current_ano = ano if ano else today.year

        # Format month for query: 'YYYY-MM'
        target_month_str = f"{current_ano}-{current_mes:02d}"

        with closing(get_db_connection()) as conn:
            # Filter by month
            gastos = conn.execute(
                "SELECT * FROM gastos WHERE strftime('%Y-%m', data) = ? ORDER BY data DESC, id DESC",
                (target_month_str,)
            ).fetchall()

            # Categories summary for the month
            categorias_db = conn.execute(
                "SELECT categoria, SUM(valor) as total FROM gastos WHERE strftime('%Y-%m', data) = ? GROUP BY categoria",
                (target_month_str,)
            ).fetchall()

            # Fetch all income sources
            rendas = conn.execute("SELECT * FROM renda").fetchall()
            renda_mensal = sum(r['valor'] for r in rendas)

        labels = [row['categoria'] for row in categorias_db]
        data = [row['total'] for row in categorias_db]
        total_geral = sum(data)
        saldo_estimado = renda_mensal - total_geral

        # Navigation Logic
        current_date = datetime(current_ano, current_mes, 1)
        prev_date = current_date - relativedelta(months=1)
        next_date = current_date + relativedelta(months=1)

        meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                 "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_nome = meses[current_mes]

        # Determine default date for the form
        if current_mes == today.month and current_ano == today.year:
            default_date = today.strftime('%Y-%m-%d')
        else:
            default_date = f"{current_ano}-{current_mes:02d}-01"

        return templates.TemplateResponse("index.html", {
            "request": request,
            "default_date": default_date,
            "gastos": gastos,
            "rendas": rendas,
            "labels": labels,
            "data": data,
            "total_geral": total_geral,
            "renda_mensal": renda_mensal,
            "saldo_estimado": saldo_estimado,
            "current_mes": current_mes,
            "current_ano": current_ano,
            "mes_nome": mes_nome,
            "prev_mes": prev_date.month,
            "prev_ano": prev_date.year,
            "next_mes": next_date.month,
            "next_ano": next_date.year
        })
    except Exception as e:
        logger.error(f"Erro na home: {e}")
        return HTMLResponse(content="<h1>Erro interno</h1>", status_code=500)

@app.post("/adicionar_renda")
async def adicionar_renda(
    valor: float = Form(...),
    descricao: str = Form("Renda Extra"),
    current_mes: int = Form(None),
    current_ano: int = Form(None)
):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("INSERT INTO renda (descricao, valor) VALUES (?, ?)", (descricao, valor))

        url = "/"
        if current_mes and current_ano:
            url = f"/?mes={current_mes}&ano={current_ano}"
        return RedirectResponse(url=url, status_code=303)
    except Exception as e:
        logger.error(f"Erro ao adicionar renda: {e}")
        raise HTTPException(status_code=500, detail="Erro ao adicionar renda")

@app.post("/deletar_renda/{id}")
async def deletar_renda(
    id: int,
    current_mes: int = Form(None),
    current_ano: int = Form(None)
):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("DELETE FROM renda WHERE id = ?", (id,))

        url = "/"
        if current_mes and current_ano:
            url = f"/?mes={current_mes}&ano={current_ano}"
        return RedirectResponse(url=url, status_code=303)
    except Exception as e:
        logger.error(f"Erro ao deletar renda: {e}")
        raise HTTPException(status_code=500, detail="Erro ao deletar renda")

@app.post("/adicionar")
async def adicionar(
    descricao: str = Form(...),
    valor: float = Form(...),
    categoria: str = Form(...),
    data: str = Form(...),
    parcelas: int = Form(1),
    current_mes: int = Form(None),
    current_ano: int = Form(None)
):
    try:
        # Parse the provided date
        start_date = datetime.strptime(data, '%Y-%m-%d').date()

        # Installment logic
        # If parcelas > 1, the value is usually per installment. Or total?
        # Usually "buy something for 300 in 3x" means 3 payments of 100.
        # Or "buy something for 100 in 3x" means 3 payments of 33.33.
        # The prompt says "algo parcelado que corra nos meses".
        # Standard credit card behavior: Input total purchase price, divide by installments?
        # Or input monthly installment value?
        # Given the form asks "Valor", users might enter the installment value (e.g., "R$ 50,00" for "3x of 50").
        # Let's assume the user enters the INSTALLMENT value. "I'm paying 50 per month".
        # This is simpler and less prone to rounding errors for the user view.
        # If they enter total, they can divide it themselves.
        # So: Value = Installment Value.

        agrupamento_id = str(uuid.uuid4())

        with closing(get_db_connection()) as conn:
            with conn:
                for i in range(parcelas):
                    # Calculate date: Start Date + i months
                    future_date = start_date + relativedelta(months=i)
                    date_str = future_date.strftime('%Y-%m-%d')

                    conn.execute(
                        "INSERT INTO gastos (descricao, valor, categoria, data, parcela_atual, total_parcelas, agrupamento_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (descricao, valor, categoria, date_str, i + 1, parcelas, agrupamento_id)
                    )

        url = "/"
        if current_mes and current_ano:
            url = f"/?mes={current_mes}&ano={current_ano}"
        return RedirectResponse(url=url, status_code=303)
    except Exception as e:
        logger.error(f"Erro ao adicionar: {e}")
        raise HTTPException(status_code=500, detail="Erro ao adicionar despesa")

@app.post("/deletar/{id}")
async def deletar(
    id: int,
    current_mes: int = Form(None),
    current_ano: int = Form(None)
):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("DELETE FROM gastos WHERE id = ?", (id,))

        url = "/"
        if current_mes and current_ano:
            url = f"/?mes={current_mes}&ano={current_ano}"
        return RedirectResponse(url=url, status_code=303)
    except Exception as e:
        logger.error(f"Erro ao deletar: {e}")
        raise HTTPException(status_code=500, detail="Erro ao deletar despesa")

@app.post("/deletar_serie/{agrupamento_id}")
async def deletar_serie(
    agrupamento_id: str,
    current_mes: int = Form(None),
    current_ano: int = Form(None)
):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                conn.execute("DELETE FROM gastos WHERE agrupamento_id = ?", (agrupamento_id,))

        url = "/"
        if current_mes and current_ano:
            url = f"/?mes={current_mes}&ano={current_ano}"
        return RedirectResponse(url=url, status_code=303)
    except Exception as e:
        logger.error(f"Erro ao deletar série: {e}")
        raise HTTPException(status_code=500, detail="Erro ao deletar série de despesas")

if __name__ == "__main__":
    # Roda no servidor local, porta 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
