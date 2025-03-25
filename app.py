from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import chess
import chess.engine
import os
import sqlite3
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Replace with a secure key in production

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    c.execute('SELECT id, username FROM users WHERE id = ?', (user_id,))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1])
    return None

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )''')
    # Games table
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        fen TEXT NOT NULL,
        move_history TEXT NOT NULL,
        player_color TEXT NOT NULL,
        probability REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

# Game state class to manage per-user state
class GameState:
    def __init__(self):
        self.board = chess.Board()
        self.move_history = []
        self.player_color = "White"
        self.last_prob = None
        self.current_game_id = None
        self.engine = None

    def initialize_engine(self):
        if self.engine is None:
            engine_path = "./stockfish.exe" if os.name == 'nt' else "./stockfish"
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
                print(f"Stockfish initialized from {engine_path}")
            except Exception as e:
                print(f"Failed to initialize Stockfish: {e}")
        return self.engine

    def set_difficulty(self, level):
        engine = self.initialize_engine()
        if engine is None:
            return
        skill_levels = {'Easy': 5, 'Medium': 10, 'Hard': 20}
        engine.configure({"Skill Level": skill_levels.get(level, 10)})

    def get_win_probability(self):
        engine = self.initialize_engine()
        if engine is None:
            return 50
        if self.last_prob is not None and not self.board.is_game_over():
            return self.last_prob
        try:
            info = engine.analyse(self.board, chess.engine.Limit(time=0.5))
            score = info.get("score", chess.engine.Cp(0)).relative.score()
            if self.player_color == "Black":
                score = -score
            self.last_prob = 50 + 50 * (score / (abs(score) + 200)) if score != 0 else 50
            return max(0, min(100, self.last_prob))
        except Exception as e:
            print(f"Error in get_win_probability: {e}")
            return 50

# Store game state in session
def get_game_state():
    if 'game_state' not in session:
        game_state = GameState()
        session['game_state'] = {
            'fen': game_state.board.fen(),
            'move_history': game_state.move_history,
            'player_color': game_state.player_color,
            'last_prob': game_state.last_prob,
            'current_game_id': game_state.current_game_id
        }
    game_state = GameState()
    state_dict = session['game_state']
    game_state.board = chess.Board(state_dict['fen'])
    game_state.move_history = state_dict['move_history']
    game_state.player_color = state_dict['player_color']
    game_state.last_prob = state_dict['last_prob']
    game_state.current_game_id = state_dict['current_game_id']
    return game_state

def save_game_state(game_state):
    session['game_state'] = {
        'fen': game_state.board.fen(),
        'move_history': game_state.move_history,
        'player_color': game_state.player_color,
        'last_prob': game_state.last_prob,
        'current_game_id': game_state.current_game_id
    }

# Save game state to database
def save_game_to_db(user_id, game_state):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    move_history_json = json.dumps(game_state.move_history)
    
    if game_state.current_game_id is None:
        c.execute('''INSERT INTO games (user_id, fen, move_history, player_color, probability, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, game_state.board.fen(), move_history_json, game_state.player_color, game_state.last_prob, now, now))
        game_state.current_game_id = c.lastrowid
    else:
        c.execute('''UPDATE games SET fen = ?, move_history = ?, player_color = ?, probability = ?, updated_at = ?
                     WHERE game_id = ?''',
                  (game_state.board.fen(), move_history_json, game_state.player_color, game_state.last_prob, now, game_state.current_game_id))
    
    conn.commit()
    conn.close()
    return game_state.current_game_id

# Load game state from database
def load_game_from_db(game_id, user_id, game_state):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    c.execute('''SELECT fen, move_history, player_color, probability FROM games
                 WHERE game_id = ? AND user_id = ?''', (game_id, user_id))
    result = c.fetchone()
    conn.close()
    
    if result:
        game_state.board = chess.Board(result[0])
        game_state.move_history = json.loads(result[1])
        game_state.player_color = result[2]
        game_state.last_prob = result[3]
        game_state.current_game_id = game_id
        return True
    return False

# Load the most recent game for the user
def load_most_recent_game(user_id, game_state):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    c.execute('''SELECT game_id, fen, move_history, player_color, probability FROM games
                 WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1''', (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        game_state.current_game_id = result[0]
        game_state.board = chess.Board(result[1])
        game_state.move_history = json.loads(result[2])
        game_state.player_color = result[3]
        game_state.last_prob = result[4]
        return True
    return False

# Get list of games for a user
def get_user_games(user_id):
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    c.execute('''SELECT game_id, created_at, updated_at FROM games
                 WHERE user_id = ? ORDER BY updated_at DESC''', (user_id,))
    games = [{'game_id': row[0], 'created_at': row[1], 'updated_at': row[2]} for row in c.fetchall()]
    conn.close()
    return games

@app.route('/')
@login_required
def index():
    game_state = get_game_state()
    # Load the most recent game for the user on login
    if not game_state.current_game_id:
        load_most_recent_game(str(current_user.id), game_state)
        save_game_state(game_state)
    return render_template('index.html')

@app.route('/login', methods=['GET'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    c.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
    user_data = c.fetchone()
    conn.close()
    
    if user_data and check_password_hash(user_data[2], password):
        user = User(user_data[0], user_data[1])
        login_user(user)
        # Clear any existing game state in session
        session.pop('game_state', None)
        return jsonify({'message': 'Logged in successfully', 'username': user.username})
    return jsonify({'error': 'Invalid username or password'}), 401

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    # Save the current game state before logging out
    game_state = get_game_state()
    save_game_to_db(str(current_user.id), game_state)
    # Clear the session
    session.pop('game_state', None)
    logout_user()
    return jsonify({'message': 'Logged out successfully'})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    hashed_password = generate_password_hash(password)
    conn = sqlite3.connect('games.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        user_id = c.lastrowid
        user = User(user_id, username)
        login_user(user)
        # Clear any existing game state in session
        session.pop('game_state', None)
        return jsonify({'message': 'Registered and logged in successfully', 'username': username})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 400
    finally:
        conn.close()

@app.route('/move', methods=['POST'])
@login_required
def make_move():
    game_state = get_game_state()
    engine = game_state.initialize_engine()
    if engine is None:
        return jsonify({'error': 'Stockfish not available'}), 500
    data = request.json
    move = data.get('move')
    user_id = str(current_user.id)
    try:
        if move == 'reset':
            game_state.board = chess.Board()
            game_state.move_history = []
            game_state.last_prob = None
            difficulty = data.get('difficulty', 'Medium')
            game_state.player_color = data.get('player_color', 'White')
            game_state.set_difficulty(difficulty)
            game_state.current_game_id = None
            print(f"Reset: player_color={game_state.player_color}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
            if game_state.player_color == "Black":
                result = engine.play(game_state.board, chess.engine.Limit(time=0.1))
                ai_move = result.move.uci()
                game_state.board.push(result.move)
                game_state.move_history.append(ai_move)
                print(f"AI (White) moved: {ai_move}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
                save_game_to_db(user_id, game_state)
                save_game_state(game_state)
                return jsonify({
                    'fen': game_state.board.fen(),
                    'move': ai_move,
                    'probability': game_state.get_win_probability(),
                    'history': game_state.move_history,
                    'player_color': game_state.player_color,
                    'game_id': game_state.current_game_id
                })
            save_game_to_db(user_id, game_state)
            save_game_state(game_state)
            return jsonify({
                'fen': game_state.board.fen(),
                'move': None,
                'probability': game_state.get_win_probability(),
                'history': game_state.move_history,
                'player_color': game_state.player_color,
                'game_id': game_state.current_game_id
            })
        game_state.board.push_uci(move)
        game_state.move_history.append(move)
        game_state.last_prob = None
        print(f"Player moved: {move}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
        if game_state.board.is_game_over():
            save_game_to_db(user_id, game_state)
            save_game_state(game_state)
            return jsonify({
                'fen': game_state.board.fen(),
                'move': None,
                'result': game_state.board.result(),
                'probability': game_state.get_win_probability(),
                'history': game_state.move_history,
                'player_color': game_state.player_color,
                'game_id': game_state.current_game_id
            })
        result = engine.play(game_state.board, chess.engine.Limit(time=0.1))
        ai_move = result.move.uci()
        game_state.board.push(result.move)
        game_state.move_history.append(ai_move)
        print(f"AI moved: {ai_move}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
        save_game_to_db(user_id, game_state)
        save_game_state(game_state)
        response = {
            'fen': game_state.board.fen(),
            'move': ai_move,
            'probability': game_state.get_win_probability(),
            'history': game_state.move_history,
            'player_color': game_state.player_color,
            'game_id': game_state.current_game_id
        }
        if game_state.board.is_game_over():
            response['result'] = game_state.board.result()
        return jsonify(response)
    except ValueError:
        return jsonify({'error': 'Invalid move'}), 400

@app.route('/fen', methods=['GET'])
@login_required
def get_fen():
    game_state = get_game_state()
    return jsonify({
        'fen': game_state.board.fen(),
        'probability': game_state.get_win_probability(),
        'history': game_state.move_history,
        'player_color': game_state.player_color,
        'game_id': game_state.current_game_id
    })

@app.route('/hint', methods=['GET'])
@login_required
def get_hint():
    game_state = get_game_state()
    engine = game_state.initialize_engine()
    if engine is None:
        return jsonify({'error': 'Stockfish not available'}), 500
    try:
        if game_state.board.is_game_over():
            return jsonify({'hint': None, 'message': 'Game is over'})

        print(f"Hint requested: player_color={game_state.player_color}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")

        if game_state.player_color == "White":
            if game_state.board.turn == chess.WHITE:
                result = engine.play(game_state.board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Hint for White (direct): {hint}")
                return jsonify({'hint': hint})
            else:
                temp_board = game_state.board.copy()
                black_move = engine.play(temp_board, chess.engine.Limit(time=0.1)).move
                temp_board.push(black_move)
                result = engine.play(temp_board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Simulated Black move: {black_move.uci()}, hint for White: {hint}")
                return jsonify({'hint': hint})
        elif game_state.player_color == "Black":
            if game_state.board.turn == chess.BLACK:
                result = engine.play(game_state.board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Hint for Black (direct): {hint}")
                return jsonify({'hint': hint})
            else:
                temp_board = game_state.board.copy()
                white_move = engine.play(temp_board, chess.engine.Limit(time=0.1)).move
                temp_board.push(white_move)
                result = engine.play(temp_board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Simulated White move: {white_move.uci()}, hint for Black: {hint}")
                return jsonify({'hint': hint})
    except Exception as e:
        print(f"Error in get_hint: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/save_game', methods=['POST'])
@login_required
def save_game_endpoint():
    game_state = get_game_state()
    user_id = str(current_user.id)
    game_id = save_game_to_db(user_id, game_state)
    save_game_state(game_state)
    return jsonify({'game_id': game_id})

@app.route('/resume_game', methods=['POST'])
@login_required
def resume_game():
    game_state = get_game_state()
    data = request.json
    game_id = data.get('game_id')
    user_id = str(current_user.id)
    if load_game_from_db(game_id, user_id, game_state):
        save_game_state(game_state)
        return jsonify({
            'fen': game_state.board.fen(),
            'history': game_state.move_history,
            'player_color': game_state.player_color,
            'probability': game_state.get_win_probability(),
            'game_id': game_state.current_game_id
        })
    return jsonify({'error': 'Game not found'}), 404

@app.route('/user_games', methods=['POST'])
@login_required
def user_games():
    user_id = str(current_user.id)
    games = get_user_games(user_id)
    return jsonify({'games': games})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)