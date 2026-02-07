from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import uvicorn

app = FastAPI()

# Configurando templates
templates = Jinja2Templates(directory="templates")

# Função para conectar ao banco (cria se não existir)
def get_db_connection():
    conn = sqlite3.connect('financeiro.db')
    conn.row_factory = sqlite3.Row
    return conn

# Inicializa a tabela
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            categoria TEXT NOT NULL,
            data DATE DEFAULT (date('now'))
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db_connection()
    gastos = conn.execute("SELECT * FROM gastos ORDER BY id DESC").fetchall()
    
    # Prepara dados para o gráfico
    categorias_db = conn.execute("SELECT categoria, SUM(valor) as total FROM gastos GROUP BY categoria").fetchall()
    conn.close()

    # Formata dados para o JavaScript do gráfico
    labels = [row['categoria'] for row in categorias_db]
    data = [row['total'] for row in categorias_db]
    total_geral = sum(data)

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "gastos": gastos,
        "labels": labels,
        "data": data,
        "total_geral": total_geral
    })

@app.post("/adicionar")
async def adicionar(descricao: str = Form(...), valor: float = Form(...), categoria: str = Form(...)):
    conn = get_db_connection()
    conn.execute("INSERT INTO gastos (descricao, valor, categoria) VALUES (?, ?, ?)", 
                 (descricao, valor, categoria))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/deletar/{id}")
async def deletar(id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM gastos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    # Roda no servidor local, porta 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
