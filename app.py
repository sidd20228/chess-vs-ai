from flask import Flask, request, jsonify, render_template
import chess
import chess.engine
import os

app = Flask(__name__)

engine_path = "./stockfish.exe" if os.name == 'nt' else "./stockfish"
board = chess.Board()
move_history = []
player_color = "White"
engine = None
last_prob = None

def get_engine():
    global engine
    if engine is None:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(engine_path)
            print(f"Stockfish initialized from {engine_path}")
        except Exception as e:
            print(f"Failed to initialize Stockfish: {e}")
    return engine

def set_difficulty(level):
    engine = get_engine()
    if engine is None:
        return
    skill_levels = {'Easy': 5, 'Medium': 10, 'Hard': 20}
    engine.configure({"Skill Level": skill_levels.get(level, 10)})

def get_win_probability():
    global last_prob
    engine = get_engine()
    if engine is None:
        return 50
    if last_prob is not None and not board.is_game_over():
        return last_prob
    try:
        info = engine.analyse(board, chess.engine.Limit(time=0.5))
        score = info.get("score", chess.engine.Cp(0)).relative.score()
        if player_color == "Black":
            score = -score
        last_prob = 50 + 50 * (score / (abs(score) + 200)) if score != 0 else 50
        return max(0, min(100, last_prob))
    except Exception as e:
        print(f"Error in get_win_probability: {e}")
        return 50

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/move', methods=['POST'])
def make_move():
    global board, move_history, player_color, last_prob
    engine = get_engine()
    if engine is None:
        return jsonify({'error': 'Stockfish not available'}), 500
    data = request.json
    move = data.get('move')
    try:
        if move == 'reset':
            board = chess.Board()  # Fresh board instance
            move_history = []
            last_prob = None
            difficulty = data.get('difficulty', 'Medium')
            player_color = data.get('player_color', 'White')
            set_difficulty(difficulty)
            print(f"Reset: player_color={player_color}, turn={'White' if board.turn else 'Black'}, FEN={board.fen()}")
            if player_color == "Black":
                result = engine.play(board, chess.engine.Limit(time=0.1))
                ai_move = result.move.uci()
                board.push(result.move)
                move_history.append(ai_move)
                print(f"AI (White) moved: {ai_move}, turn={'White' if board.turn else 'Black'}, FEN={board.fen()}")
                return jsonify({
                    'fen': board.fen(),
                    'move': ai_move,
                    'probability': get_win_probability(),
                    'history': move_history,
                    'player_color': player_color
                })
            return jsonify({
                'fen': board.fen(),
                'move': None,
                'probability': get_win_probability(),
                'history': move_history,
                'player_color': player_color
            })
        board.push_uci(move)
        move_history.append(move)
        last_prob = None
        print(f"Player moved: {move}, turn={'White' if board.turn else 'Black'}, FEN={board.fen()}")
        if board.is_game_over():
            return jsonify({
                'fen': board.fen(),
                'move': None,
                'result': board.result(),
                'probability': get_win_probability(),
                'history': move_history,
                'player_color': player_color
            })
        result = engine.play(board, chess.engine.Limit(time=0.1))
        ai_move = result.move.uci()
        board.push(result.move)
        move_history.append(ai_move)
        print(f"AI moved: {ai_move}, turn={'White' if board.turn else 'Black'}, FEN={board.fen()}")
        response = {
            'fen': board.fen(),
            'move': ai_move,
            'probability': get_win_probability(),
            'history': move_history,
            'player_color': player_color
        }
        if board.is_game_over():
            response['result'] = board.result()
        return jsonify(response)
    except ValueError:
        return jsonify({'error': 'Invalid move'}), 400

@app.route('/fen', methods=['GET'])
def get_fen():
    return jsonify({
        'fen': board.fen(),
        'probability': get_win_probability(),
        'history': move_history,
        'player_color': player_color
    })

@app.route('/hint', methods=['GET'])
def get_hint():
    global board, player_color
    engine = get_engine()
    if engine is None:
        return jsonify({'error': 'Stockfish not available'}), 500
    try:
        if board.is_game_over():
            return jsonify({'hint': None, 'message': 'Game is over'})

        print(f"Hint requested: player_color={player_color}, turn={'White' if board.turn else 'Black'}, FEN={board.fen()}")

        # Ensure hint matches player_color
        if player_color == "White":
            if board.turn == chess.WHITE:
                result = engine.play(board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Hint for White (direct): {hint}")
                return jsonify({'hint': hint})
            else:
                temp_board = board.copy()
                black_move = engine.play(temp_board, chess.engine.Limit(time=0.1)).move
                temp_board.push(black_move)
                result = engine.play(temp_board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Simulated Black move: {black_move.uci()}, hint for White: {hint}")
                return jsonify({'hint': hint})
        elif player_color == "Black":
            if board.turn == chess.BLACK:
                result = engine.play(board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Hint for Black (direct): {hint}")
                return jsonify({'hint': hint})
            else:
                temp_board = board.copy()
                white_move = engine.play(temp_board, chess.engine.Limit(time=0.1)).move
                temp_board.push(white_move)
                result = engine.play(temp_board, chess.engine.Limit(time=0.1))
                hint = result.move.uci()
                print(f"Simulated White move: {white_move.uci()}, hint for Black: {hint}")
                return jsonify({'hint': hint})
    except Exception as e:
        print(f"Error in get_hint: {e}")
        return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    set_difficulty('Medium')
    app.run(host='0.0.0.0', port=5000)