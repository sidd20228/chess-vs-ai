from flask import Flask, request, jsonify, render_template, redirect, url_for, session, g
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import chess
import chess.engine
import os
import sqlite3
import json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Replace with a secure key in production

# Set up logging
handler = RotatingFileHandler('app.log', maxBytes=1000000, backupCount=5)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

# Rate limiting to prevent abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user_data = db.execute('SELECT id, username FROM users WHERE id = ?', (user_id,)).fetchone()
    if user_data:
        return User(user_data['id'], user_data['username'])
    return None

# Database connection management
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('games.db')
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

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

    def get_engine(self):
        if 'engine' not in g:
            engine_path = "./stockfish.exe" if os.name == 'nt' else "./stockfish"
            retries = 3
            for attempt in range(retries):
                try:
                    g.engine = chess.engine.SimpleEngine.popen_uci(engine_path, timeout=10.0)
                    app.logger.info(f"Stockfish initialized from {engine_path}")
                    break
                except Exception as e:
                    app.logger.error(f"Failed to initialize Stockfish (attempt {attempt + 1}/{retries}): {e}")
                    if attempt == retries - 1:
                        g.engine = None
                    else:
                        import time
                        time.sleep(1)  # Wait 1 second before retrying
        return g.engine

    def set_difficulty(self, level):
        engine = self.get_engine()
        if engine is None:
            app.logger.warning("Stockfish engine not available for setting difficulty")
            return
        skill_levels = {'Easy': 5, 'Medium': 10, 'Hard': 20}
        try:
            engine.configure({"Skill Level": skill_levels.get(level, 10)})
            app.logger.info(f"Stockfish difficulty set to {level} (Skill Level: {skill_levels.get(level, 10)})")
        except Exception as e:
            app.logger.error(f"Failed to set Stockfish difficulty: {e}")

    def get_win_probability(self):
        engine = self.get_engine()
        if engine is None:
            app.logger.warning("Stockfish engine not available for win probability calculation")
            return 50
        if self.last_prob is not None and not self.board.is_game_over():
            return self.last_prob
        try:
            info = engine.analyse(self.board, chess.engine.Limit(time=0.5))
            score_obj = info.get("score", chess.engine.Cp(0)).relative
            # Check if the score is a mate score
            if isinstance(score_obj, chess.engine.Mate):
                mate_value = score_obj.mate()  # Positive if winning, negative if losing
                if self.player_color == "Black":
                    mate_value = -mate_value
                # If mate_value is positive, the player is winning (probability 100)
                # If mate_value is negative, the player is losing (probability 0)
                self.last_prob = 100 if mate_value > 0 else 0
            else:
                # Handle centipawn score
                score = score_obj.score()
                if score is None:
                    app.logger.warning("Score is None, defaulting to 0")
                    score = 0
                if self.player_color == "Black":
                    score = -score
                self.last_prob = 50 + 50 * (score / (abs(score) + 200)) if score != 0 else 50
            return max(0, min(100, self.last_prob))
        except Exception as e:
            app.logger.error(f"Error in get_win_probability: {e}")
            return 50

# Clean up Stockfish engine after each request
@app.teardown_request
def cleanup_engine(exception):
    engine = g.pop('engine', None)
    if engine is not None:
        try:
            engine.quit()
            app.logger.info("Stockfish engine closed")
        except Exception as e:
            app.logger.error(f"Failed to close Stockfish engine: {e}")

# Clean up old games
def cleanup_old_games():
    db = get_db()
    threshold = (datetime.utcnow() - timedelta(days=7)).isoformat()
    try:
        db.execute("DELETE FROM games WHERE updated_at < ?", (threshold,))
        db.commit()
        app.logger.info("Cleaned up old games")
    except Exception as e:
        app.logger.error(f"Failed to clean up old games: {e}")

# Save game state to database
def save_game_to_db(user_id, game_state):
    db = get_db()
    now = datetime.utcnow().isoformat()
    move_history_json = json.dumps(game_state.move_history)
    
    try:
        if game_state.current_game_id is None:
            db.execute('''INSERT INTO games (user_id, fen, move_history, player_color, probability, created_at, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, game_state.board.fen(), move_history_json, game_state.player_color, game_state.last_prob, now, now))
            game_state.current_game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            db.execute('''UPDATE games SET fen = ?, move_history = ?, player_color = ?, probability = ?, updated_at = ?
                         WHERE game_id = ?''',
                      (game_state.board.fen(), move_history_json, game_state.player_color, game_state.last_prob, now, game_state.current_game_id))
        db.commit()
        app.logger.info(f"Saved game to database: game_id={game_state.current_game_id}, user_id={user_id}")
    except Exception as e:
        app.logger.error(f"Failed to save game to database: {e}")
        raise
    return game_state.current_game_id

# Load game state from database
def load_game_from_db(game_id, user_id, game_state):
    db = get_db()
    try:
        result = db.execute('''SELECT fen, move_history, player_color, probability FROM games
                             WHERE game_id = ? AND user_id = ?''', (game_id, user_id)).fetchone()
        if result:
            game_state.board = chess.Board(result['fen'])
            game_state.move_history = json.loads(result['move_history'])
            game_state.player_color = result['player_color']
            game_state.last_prob = result['probability']
            game_state.current_game_id = game_id
            app.logger.info(f"Loaded game from database: game_id={game_id}, user_id={user_id}")
            return True
        app.logger.warning(f"Game not found in database: game_id={game_id}, user_id={user_id}")
        return False
    except Exception as e:
        app.logger.error(f"Failed to load game from database: {e}")
        return False

# Load the most recent game for the user
def load_most_recent_game(user_id, game_state):
    db = get_db()
    try:
        result = db.execute('''SELECT game_id, fen, move_history, player_color, probability FROM games
                             WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1''', (user_id,)).fetchone()
        if result:
            game_state.current_game_id = result['game_id']
            game_state.board = chess.Board(result['fen'])
            game_state.move_history = json.loads(result['move_history'])
            game_state.player_color = result['player_color']
            game_state.last_prob = result['probability']
            app.logger.info(f"Loaded most recent game for user_id={user_id}: game_id={result['game_id']}")
            return True
        app.logger.info(f"No recent games found for user_id={user_id}")
        return False
    except Exception as e:
        app.logger.error(f"Failed to load most recent game: {e}")
        return False

# Get list of games for a user
def get_user_games(user_id):
    db = get_db()
    try:
        games = db.execute('''SELECT game_id, created_at, updated_at FROM games
                             WHERE user_id = ? ORDER BY updated_at DESC''', (user_id,)).fetchall()
        result = [{'game_id': row['game_id'], 'created_at': row['created_at'], 'updated_at': row['updated_at']} for row in games]
        app.logger.info(f"Retrieved {len(result)} games for user_id={user_id}")
        return result
    except Exception as e:
        app.logger.error(f"Failed to retrieve user games: {e}")
        return []

# Store only the game_id in the session
def get_game_state():
    if 'game_id' not in session:
        game_state = GameState()
        user_id = str(current_user.id) if current_user.is_authenticated else "guest"
        game_state.current_game_id = save_game_to_db(user_id, game_state)
        session['game_id'] = game_state.current_game_id
    else:
        game_state = GameState()
        user_id = str(current_user.id) if current_user.is_authenticated else "guest"
        if not load_game_from_db(session['game_id'], user_id, game_state):
            game_state = GameState()
            game_state.current_game_id = save_game_to_db(user_id, game_state)
            session['game_id'] = game_state.current_game_id
    return game_state

def save_game_state(game_state):
    user_id = str(current_user.id) if current_user.is_authenticated else "guest"
    session['game_id'] = save_game_to_db(user_id, game_state)

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
    
    db = get_db()
    user_data = db.execute('SELECT id, username, password FROM users WHERE username = ?', (username,)).fetchone()
    
    if user_data and check_password_hash(user_data['password'], password):
        user = User(user_data['id'], user_data['username'])
        login_user(user)
        # Clear any existing game state in session
        session.pop('game_id', None)
        app.logger.info(f"User logged in: username={username}")
        return jsonify({'message': 'Logged in successfully', 'username': user.username})
    app.logger.warning(f"Failed login attempt: username={username}")
    return jsonify({'error': 'Invalid username or password'}), 401

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    # Save the current game state before logging out
    game_state = get_game_state()
    save_game_to_db(str(current_user.id), game_state)
    # Log the user ID before logging out
    app.logger.info(f"User logged out: user_id={current_user.id}")
    # Clear the session
    session.pop('game_id', None)
    logout_user()
    return jsonify({'message': 'Logged out successfully'})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        app.logger.warning("Registration failed: Username or password missing")
        return jsonify({'error': 'Username and password are required'}), 400
    
    hashed_password = generate_password_hash(password)
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        db.commit()
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        user = User(user_id, username)
        login_user(user)
        # Clear any existing game state in session
        session.pop('game_id', None)
        app.logger.info(f"User registered and logged in: username={username}, user_id={user_id}")
        return jsonify({'message': 'Registered and logged in successfully', 'username': username})
    except sqlite3.IntegrityError:
        app.logger.warning(f"Registration failed: Username already exists: {username}")
        return jsonify({'error': 'Username already exists'}), 400

@app.route('/move', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def make_move():
    game_state = get_game_state()
    engine = game_state.get_engine()
    if engine is None:
        app.logger.error("Stockfish engine not available for move")
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
            app.logger.info(f"Reset: player_color={game_state.player_color}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
            if game_state.player_color == "Black":
                result = engine.play(game_state.board, chess.engine.Limit(time=0.5))
                ai_move = result.move.uci()
                game_state.board.push(result.move)
                game_state.move_history.append(ai_move)
                app.logger.info(f"AI (White) moved: {ai_move}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
                save_game_to_db(user_id, game_state)
                save_game_state(game_state)
                cleanup_old_games()
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
            cleanup_old_games()
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
        app.logger.info(f"Player moved: {move}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
        if game_state.board.is_game_over():
            save_game_to_db(user_id, game_state)
            save_game_state(game_state)
            cleanup_old_games()
            return jsonify({
                'fen': game_state.board.fen(),
                'move': None,
                'result': game_state.board.result(),
                'probability': game_state.get_win_probability(),
                'history': game_state.move_history,
                'player_color': game_state.player_color,
                'game_id': game_state.current_game_id
            })
        result = engine.play(game_state.board, chess.engine.Limit(time=0.5))
        ai_move = result.move.uci()
        game_state.board.push(result.move)
        game_state.move_history.append(ai_move)
        app.logger.info(f"AI moved: {ai_move}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")
        save_game_to_db(user_id, game_state)
        save_game_state(game_state)
        cleanup_old_games()
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
        app.logger.warning(f"Invalid move attempted: {move}")
        return jsonify({'error': 'Invalid move'}), 400
    except Exception as e:
        app.logger.error(f"Error in make_move: {e}")
        return jsonify({'error': 'Server error'}), 500

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
@limiter.limit("20 per minute")
def get_hint():
    game_state = get_game_state()
    engine = game_state.get_engine()
    if engine is None:
        app.logger.error("Stockfish engine not available for hint")
        return jsonify({'error': 'Stockfish not available'}), 500
    try:
        if game_state.board.is_game_over():
            return jsonify({'hint': None, 'message': 'Game is over'})

        app.logger.info(f"Hint requested: player_color={game_state.player_color}, turn={'White' if game_state.board.turn else 'Black'}, FEN={game_state.board.fen()}")

        if game_state.player_color == "White":
            if game_state.board.turn == chess.WHITE:
                result = engine.play(game_state.board, chess.engine.Limit(time=0.5))
                hint = result.move.uci()
                app.logger.info(f"Hint for White (direct): {hint}")
                return jsonify({'hint': hint})
            else:
                temp_board = game_state.board.copy()
                black_move = engine.play(temp_board, chess.engine.Limit(time=0.5)).move
                temp_board.push(black_move)
                result = engine.play(temp_board, chess.engine.Limit(time=0.5))
                hint = result.move.uci()
                app.logger.info(f"Simulated Black move: {black_move.uci()}, hint for White: {hint}")
                return jsonify({'hint': hint})
        elif game_state.player_color == "Black":
            if game_state.board.turn == chess.BLACK:
                result = engine.play(game_state.board, chess.engine.Limit(time=0.5))
                hint = result.move.uci()
                app.logger.info(f"Hint for Black (direct): {hint}")
                return jsonify({'hint': hint})
            else:
                temp_board = game_state.board.copy()
                white_move = engine.play(temp_board, chess.engine.Limit(time=0.5)).move
                temp_board.push(white_move)
                result = engine.play(temp_board, chess.engine.Limit(time=0.5))
                hint = result.move.uci()
                app.logger.info(f"Simulated White move: {white_move.uci()}, hint for Black: {hint}")
                return jsonify({'hint': hint})
    except Exception as e:
        app.logger.error(f"Error in get_hint: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/save_game', methods=['POST'])
@login_required
def save_game_endpoint():
    game_state = get_game_state()
    user_id = str(current_user.id)
    game_id = save_game_to_db(user_id, game_state)
    save_game_state(game_state)
    cleanup_old_games()
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

@app.route('/health', methods=['GET'])
def health():
    try:
        engine = chess.engine.SimpleEngine.popen_uci("./stockfish.exe" if os.name == 'nt' else "./stockfish", timeout=10.0)
        engine.configure({"Skill Level": 10})
        board = chess.Board("rnbqkbnr/pppppppp/5n2/8/8/5N2/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        result = engine.play(board, chess.engine.Limit(time=0.5))
        engine.quit()
        app.logger.info("Health check passed")
        return jsonify({'status': 'healthy', 'best_move': result.move.uci()})
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)