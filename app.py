from flask import Flask, request, jsonify, render_template
import chess
import chess.engine

app = Flask(__name__)

board = chess.Board()
move_history = []
player_color = "White"  # Default to White
try:
    engine = chess.engine.SimpleEngine.popen_uci("./stockfish")
    print("Stockfish initialized successfully")
except Exception as e:
    print(f"Failed to initialize Stockfish: {e}")
    engine = None

def set_difficulty(level):
    if engine is None:
        return
    skill_levels = {'Easy': 5, 'Medium': 10, 'Hard': 20}
    skill = skill_levels.get(level, 10)
    engine.configure({"Skill Level": skill})
    print(f"Set difficulty to {level} (Skill Level: {skill})")

def get_win_probability():
    if engine is None:
        print("Engine unavailable, returning default 50%")
        return 50
    try:
        print(f"Current FEN: {board.fen()}")
        if board.is_checkmate():
            outcome = board.outcome()
            winner = outcome.winner
            print(f"Checkmate detected: Winner = {winner}")
            return 100 if (winner and player_color == "White") or (not winner and player_color == "Black") else 0
        if board.is_stalemate() or board.is_insufficient_material() or board.is_seventyfive_moves():
            print("Draw detected")
            return 50

        info = engine.analyse(board, chess.engine.Limit(time=0.5))
        score = info.get("score")
        if score is None:
            print("No score returned, defaulting to 50%")
            return 50
        
        relative_score = score.relative
        if isinstance(relative_score, chess.engine.Cp):
            cp = relative_score.score()
            # Adjust probability based on player color (White = positive, Black = negative)
            if player_color == "Black":
                cp = -cp
            probability = 50 + 50 * (cp / (abs(cp) + 200)) if cp != 0 else 50
            print(f"Centipawns: {cp}, Calculated Probability: {probability:.2f}%")
            return max(0, min(100, probability))
        elif isinstance(relative_score, chess.engine.Mate):
            mate_in = relative_score.score()
            print(f"Mate in {mate_in} detected")
            return 100 if (mate_in > 0 and player_color == "White") or (mate_in < 0 and player_color == "Black") else 0
        else:
            print("Unknown score type, defaulting to 50%")
            return 50
    except Exception as e:
        print(f"Error in get_win_probability: {e}")
        return 50

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/move', methods=['POST'])
def make_move():
    global board, move_history, player_color
    if engine is None:
        return jsonify({'error': 'Stockfish not available'}), 500
    data = request.json
    move = data.get('move')
    
    try:
        if move == 'reset':
            board.reset()
            move_history = []
            difficulty = data.get('difficulty', 'Medium')
            player_color = data.get('player_color', 'White')
            set_difficulty(difficulty)
            print(f"Reset: Player color = {player_color}")
            if player_color == "Black":  # AI moves first
                result = engine.play(board, chess.engine.Limit(time=1.0))
                ai_move = result.move.uci()
                board.push(result.move)
                move_history.append(ai_move)
                prob = get_win_probability()
                print(f"AI first move {ai_move}: Probability = {prob}")
                return jsonify({'fen': board.fen(), 'move': ai_move, 'probability': prob, 'history': move_history, 'player_color': player_color})
            prob = get_win_probability()
            return jsonify({'fen': board.fen(), 'move': None, 'probability': prob, 'history': move_history, 'player_color': player_color})
        
        board.push_uci(move)
        move_history.append(move)
        if board.is_game_over():
            prob = get_win_probability()
            print(f"Game over after human move: Probability = {prob}")
            return jsonify({'fen': board.fen(), 'move': None, 'result': board.result(), 'probability': prob, 'history': move_history, 'player_color': player_color})
        
        result = engine.play(board, chess.engine.Limit(time=1.0))
        ai_move = result.move.uci()
        board.push(result.move)
        move_history.append(ai_move)
        
        prob = get_win_probability()
        print(f"After AI move {ai_move}: Probability = {prob}")
        response = {'fen': board.fen(), 'move': ai_move, 'probability': prob, 'history': move_history, 'player_color': player_color}
        if board.is_game_over():
            response['result'] = board.result()
        return jsonify(response)
    except ValueError:
        return jsonify({'error': 'Invalid move'}), 400
    except Exception as e:
        print(f"Error in /move: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/fen', methods=['GET'])
def get_fen():
    if engine is None:
        return jsonify({'fen': board.fen(), 'probability': 50, 'history': move_history, 'player_color': player_color})
    try:
        prob = get_win_probability()
        print(f"FEN request: Probability = {prob}")
        return jsonify({'fen': board.fen(), 'probability': prob, 'history': move_history, 'player_color': player_color})
    except Exception as e:
        print(f"Error in /fen: {e}")
        return jsonify({'fen': board.fen(), 'probability': 50, 'history': move_history, 'player_color': player_color})

if __name__ == '__main__':
    try:
        set_difficulty('Medium')
        app.run(debug=True)
    finally:
        if engine:
            engine.quit()