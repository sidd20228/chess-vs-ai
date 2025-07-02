# Chess vs AI
A web-based chess game where you can play against Stockfish AI. Features difficulty settings, move history, player color choice, sound effects, and a dark mode toggle.

## Setup
1. Clone the repo: `git clone https://github.com/sidd20228/chess-vs-ai.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Ensure the following sound files are present in the `static/` directory:
   - `move.wav` (normal move)
   - `capture.wav` (capture move)
   - `check.wav` (check move)
   You can use chess.com sound files or your own.
4. Run: `python app.py`
5. Open `http://127.0.0.1:5000` in your browser.

## Features
- Play as White or Black against Stockfish AI engine
- Adjustable AI difficulty levels (Easy, Medium, Hard)
- Interactive board with drag-and-drop or tap-to-move options (works on desktop and mobile)
- Real-time move history display with algebraic notation
- Sound effects for move, capture, and check (chess.com-like)
- Dark/Light mode toggle for better visibility
- Win probability indicator
- Hint system to suggest best moves
- Save and resume games
- User authentication system
- Mobile-responsive design
- Visual move highlighting and hints
- Game state indicators (Check, Checkmate, Draw, etc.)
- Automatic game saving on browser close

## Technologies Used
- Python/Flask backend
- JavaScript/jQuery frontend 
- Stockfish chess engine
- Chess.js for game logic
- Chessboard.js for board UI
- SQLite database for game storage
- Tailwind CSS for styling


