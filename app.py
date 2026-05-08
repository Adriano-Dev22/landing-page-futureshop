from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_troque_em_producao'

DB = 'database.db'



def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                descricao TEXT,
                preco REAL NOT NULL,
                imagem TEXT,
                categoria TEXT
            );

            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                produto_id INTEGER NOT NULL,
                quantidade INTEGER DEFAULT 1,
                data TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                FOREIGN KEY (produto_id) REFERENCES produtos(id)
            );
        ''')

 
        qtd = conn.execute('SELECT COUNT(*) FROM produtos').fetchone()[0]
        if qtd == 0:
            produtos = [
                ('Fone Bluetooth Pro', 'Som cristalino, bateria 40h, cancelamento de ruído.', 299.90, 'fone.jpg', 'Eletrônicos'),
                ('Mochila Urban 25L', 'Impermeável, compartimento notebook até 15".', 189.90, 'mochila.jpg', 'Acessórios'),
                ('Tênis Runner X', 'Solado amortecedor, mesh respirável.', 349.90, 'tenis.jpg', 'Calçados'),
                ('Luminária LED Desk', 'Ajuste de brilho e temperatura, USB-C.', 129.90, 'luminaria.jpg', 'Casa'),
                ('Garrafa Térmica 1L', 'Mantém frio 24h ou quente 12h, aço inox.', 89.90, 'garrafa.jpg', 'Esporte'),
                ('Teclado Mecânico TKL', 'Switch red, RGB por tecla, sem fio.', 459.90, 'teclado.jpg', 'Eletrônicos'),
            ]
            conn.executemany(
                'INSERT INTO produtos (nome, descricao, preco, imagem, categoria) VALUES (?,?,?,?,?)',
                produtos
            )
            conn.commit()



def usuario_logado():
    return session.get('usuario_id') is not None

def get_usuario():
    if not usuario_logado():
        return None
    with get_db() as conn:
        return conn.execute('SELECT * FROM usuarios WHERE id = ?', (session['usuario_id'],)).fetchone()


@app.route('/')
def index():
    categoria = request.args.get('categoria', '')
    with get_db() as conn:
        if categoria:
            produtos = conn.execute(
                'SELECT * FROM produtos WHERE categoria = ?', (categoria,)
            ).fetchall()
        else:
            produtos = conn.execute('SELECT * FROM produtos').fetchall()

        categorias = conn.execute(
            'SELECT DISTINCT categoria FROM produtos'
        ).fetchall()

    return render_template('index.html',
                           produtos=produtos,
                           categorias=categorias,
                           categoria_ativa=categoria,
                           usuario=get_usuario())

@app.route('/produto/<int:id>')
def produto(id):
    with get_db() as conn:
        p = conn.execute('SELECT * FROM produtos WHERE id = ?', (id,)).fetchone()
    if not p:
        flash('Produto não encontrado.', 'error')
        return redirect(url_for('index'))
    return render_template('produto.html', produto=p, usuario=get_usuario())



@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if usuario_logado():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome  = request.form['nome'].strip()
        email = request.form['email'].strip().lower()
        senha = request.form['senha']
        conf  = request.form['confirmar_senha']

        if not nome or not email or not senha:
            flash('Preencha todos os campos.', 'error')
        elif len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'error')
        elif senha != conf:
            flash('As senhas não coincidem.', 'error')
        else:
            try:
                with get_db() as conn:
                    conn.execute(
                        'INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)',
                        (nome, email, generate_password_hash(senha))
                    )
                    conn.commit()
                flash('Cadastro realizado! Faça login.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('E-mail já cadastrado.', 'error')

    return render_template('cadastro.html', usuario=None)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if usuario_logado():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        senha = request.form['senha']

        with get_db() as conn:
            u = conn.execute(
                'SELECT * FROM usuarios WHERE email = ?', (email,)
            ).fetchone()

        if u and check_password_hash(u['senha'], senha):
            session['usuario_id']   = u['id']
            session['usuario_nome'] = u['nome']
            flash(f'Bem-vindo, {u["nome"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('E-mail ou senha incorretos.', 'error')

    return render_template('login.html', usuario=None)

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da conta.', 'info')
    return redirect(url_for('index'))





@app.route('/dashboard')
def dashboard():
    if not usuario_logado():
        flash('Faça login para acessar sua conta.', 'error')
        return redirect(url_for('login'))

    with get_db() as conn:
        pedidos = conn.execute('''
            SELECT pedidos.*, produtos.nome AS prod_nome, produtos.preco,
                   produtos.imagem
            FROM pedidos
            JOIN produtos ON pedidos.produto_id = produtos.id
            WHERE pedidos.usuario_id = ?
            ORDER BY pedidos.data DESC
        ''', (session['usuario_id'],)).fetchall()

    return render_template('dashboard.html',
                           usuario=get_usuario(),
                           pedidos=pedidos)



@app.route('/finalizar_pedido', methods=['POST'])
def finalizar_pedido():
    if not usuario_logado():
        return jsonify({'ok': False, 'msg': 'Não autenticado'}), 401

    data = request.get_json()
    itens = data.get('itens', [])

    if not itens:
        return jsonify({'ok': False, 'msg': 'Carrinho vazio'}), 400

    with get_db() as conn:
        for item in itens:
            conn.execute(
                'INSERT INTO pedidos (usuario_id, produto_id, quantidade) VALUES (?,?,?)',
                (session['usuario_id'], item['id'], item['quantidade'])
            )
        conn.commit()

    return jsonify({'ok': True, 'msg': 'Pedido realizado com sucesso!'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)