let board;
let game;
let playerColor = 'White';
let pendingMove = null;
let currentGameId = null;
let username = localStorage.getItem('username') || null;
let selectedSquare = null;
let useTapToMove = /Mobi|Android/i.test(navigator.userAgent); // Default to tap-to-move on mobile

// --- Sound setup ---
const moveSound = new Audio('/static/move.wav');
const captureSound = new Audio('/static/capture.wav');
const checkSound = new Audio('/static/check.wav');

// --- Move navigation state ---
let fullMoveHistory = [];
let navMoveIndex = -1; // -1 means latest position

// --- Timer setup ---
let whiteTime = 300; // default 5 min
let blackTime = 300;
let whiteTimerInterval = null;
let blackTimerInterval = null;
let activeColor = 'w'; // 'w' or 'b'

function initializeBoard() {
    if (typeof Chessboard === 'undefined') {
        console.error("Chessboard.js not loaded!");
        return;
    }
    if (typeof Chess === 'undefined') {
        console.error("Chess.js not loaded! Please include it.");
        return;
    }

    game = new Chess();
    board = Chessboard('board', {
        draggable: !useTapToMove,
        position: 'start',
        onDrop: onDrop,
        onSnapEnd: onSnapEnd,
        onDragStart: onDragStart,
        onMouseoverSquare: onMouseoverSquare,
        onMouseoutSquare: onMouseoutSquare,
        onSquareClick: onSquareClick,
        pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
        orientation: playerColor.toLowerCase()
    });

    const $board = $('#board');
    $board.on('touchstart', function(e) {
        console.log("Touchstart on board:", e.originalEvent.touches[0]);
    });
    $board.on('touchmove', function(e) {
        console.log("Touchmove on board:", e.originalEvent.touches[0]);
    });

    // Desktop: Click handler for tap-to-move
    $board.on('click', '.square-55d63', function() {
        const classes = $(this).attr('class').split(' ');
        const squareClass = classes.find(cls => cls.startsWith('square-') && cls !== 'square-55d63');
        if (squareClass) {
            const square = squareClass.replace('square-', '');
            onSquareClick(square);
        }
    });

    // Mobile: Touchend handler for tap-to-move
    $board.on('touchend', '.square-55d63', function(e) {
        e.preventDefault();
        const classes = $(this).attr('class').split(' ');
        const squareClass = classes.find(cls => cls.startsWith('square-') && cls !== 'square-55d63');
        if (squareClass) {
            const square = squareClass.replace('square-', '');
            onSquareClick(square);
        }
    });

    // Log board dimensions
    console.log("Board dimensions:", {
        width: $board.width(),
        height: $board.height(),
        parentWidth: $board.parent().width(),
        parentHeight: $board.parent().height()
    });

    console.log("Board initialized with useTapToMove:", useTapToMove);
    updateStatus();
    fetchFen();
    updateInteractionModeUI();
}

function updateInteractionModeUI() {
    $('#mode-text').text(useTapToMove ? 'Tap to Move' : 'Drag to Move');
    console.log("Interaction mode updated to:", useTapToMove ? 'Tap to Move' : 'Drag to Move');
}

function onDragStart(source, piece, position, orientation) {
    const isPlayerTurn = (playerColor === 'White' && game.turn() === 'w') || (playerColor === 'Black' && game.turn() === 'b');
    if (!isPlayerTurn) {
        console.log("Not your turn! Player color:", playerColor, "Game turn:", game.turn());
        return false;
    }
    if (game.game_over()) {
        console.log("Game is over, cannot drag pieces!");
        return false;
    }
    if ((playerColor === 'White' && piece.search(/^b/) !== -1) ||
        (playerColor === 'Black' && piece.search(/^w/) !== -1)) {
        console.log("Cannot drag opponent's piece!");
        return false;
    }
    console.log("Drag started:", source, piece);
    return true;
}

function onMouseoverSquare(square, piece) {
    if (!piece || !useTapToMove) return;
    const moves = game.moves({ square: square, verbose: true });
    if (moves.length === 0) return;

    const squaresToHighlight = moves.map(move => move.to);
    squaresToHighlight.forEach(square => {
        $(`#board .square-${square}`).addClass('highlight-move');
    });
}

function onMouseoutSquare(square, piece) {
    if (!useTapToMove) return;
    $(`#board .square-55d63`).removeClass('highlight-move');
}

function onSquareClick(square) {
    console.log("onSquareClick triggered for square:", square);
    console.log("Current useTapToMove state:", useTapToMove);
    if (!useTapToMove) {
        console.log("Tap-to-move is disabled, skipping onSquareClick logic");
        return;
    }
    if (game.game_over()) {
        console.log("Game is over, cannot make moves!");
        selectedSquare = null;
        $(`#board .square-55d63`).removeClass('highlight-selected highlight-move');
        return;
    }
    const piece = game.get(square);
    console.log("Piece on square:", piece);
    if (selectedSquare) {
        console.log("Selected square exists:", selectedSquare, "Attempting move to:", square);
        const move = {
            from: selectedSquare,
            to: square,
            promotion: 'q'
        };
        const isPlayerTurn = (playerColor === 'White' && game.turn() === 'w') || (playerColor === 'Black' && game.turn() === 'b');
        console.log("Is player's turn?", isPlayerTurn, "Player color:", playerColor, "Game turn:", game.turn());
        if (!isPlayerTurn) {
            console.log("Not your turn! Clearing selection.");
            selectedSquare = null;
            $(`#board .square-55d63`).removeClass('highlight-selected highlight-move');
            return;
        }
        const pieceOnSquare = game.get(selectedSquare);
        console.log("Piece on selected square:", pieceOnSquare);
        const isPawn = pieceOnSquare && pieceOnSquare.type === 'p';
        const isPromotion = isPawn && (
            (pieceOnSquare.color === 'w' && square.charAt(1) === '8') ||
            (pieceOnSquare.color === 'b' && square.charAt(1) === '1')
        );
        console.log("Is this a promotion move?", isPromotion);
        if (isPromotion) {
            console.log("Pawn promotion detected:", selectedSquare, square);
            pendingMove = { source: selectedSquare, target: square };
            $('#promotion-modal').removeClass('hidden');
            selectedSquare = null;
            $(`#board .square-55d63`).removeClass('highlight-selected highlight-move');
            return;
        }
        console.log("Current FEN before move:", game.fen());
        const validMove = game.move(move);
        console.log("Move result:", validMove);
        if (validMove === null) {
            console.log("Invalid move:", selectedSquare, square);
            selectedSquare = null;
            $(`#board .square-55d63`).removeClass('highlight-selected highlight-move');
            return;
        }
        // Play sound
        if (game.in_check()) {
            checkSound.play();
        } else if (validMove.captured) {
            captureSound.play();
        } else {
            moveSound.play();
        }
        console.log("Move is valid, sending to server:", selectedSquare + square);
        makeServerMove(selectedSquare + square);
        selectedSquare = null;
        $(`#board .square-55d63`).removeClass('highlight-selected highlight-move');
        return;
    }
    if (piece && (
        (playerColor === 'White' && piece.color === 'w') ||
        (playerColor === 'Black' && piece.color === 'b')
    )) {
        console.log("Selecting piece on square:", square);
        selectedSquare = square;
        $(`#board .square-${square}`).addClass('highlight-selected');
        const moves = game.moves({ square: square, verbose: true });
        console.log("Possible moves:", moves);
        const squaresToHighlight = moves.map(move => move.to);
        squaresToHighlight.forEach(square => {
            $(`#board .square-${square}`).addClass('highlight-move');
        });
    } else {
        console.log("No valid piece to select, clearing selection.");
        selectedSquare = null;
        $(`#board .square-55d63`).removeClass('highlight-selected highlight-move');
    }
}

function squareToCoords(square, boardSize) {
    const files = 'abcdefgh';
    const file = files.indexOf(square[0]);
    const rank = parseInt(square[1]);

    const squareSize = boardSize / 8;
    let x, y;

    if (playerColor.toLowerCase() === 'white') {
        x = file * squareSize;
        y = (8 - rank) * squareSize;
    } else {
        x = (7 - file) * squareSize;
        y = (rank - 1) * squareSize;
    }

    return { x: x + squareSize / 2, y: y + squareSize / 2 };
}

function drawHintArrow(fromSquare, toSquare) {
    // Remove any previous hint arrow SVG
    $('.chessboard-63f37 .hint-arrow-svg').remove();
    // Find the chess grid
    const $grid = $('.chessboard-63f37');
    const gridWidth = $grid.width();
    const gridHeight = $grid.height();
    const boardSize = Math.min(gridWidth, gridHeight);
    const from = squareToCoords(fromSquare, boardSize);
    const to = squareToCoords(toSquare, boardSize);
    // Create SVG
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', gridWidth);
    svg.setAttribute('height', gridHeight);
    svg.setAttribute('class', 'hint-arrow-svg');
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.pointerEvents = 'none';
    svg.style.zIndex = '10';
    // Marker
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'arrowhead');
    marker.setAttribute('markerWidth', '10');
    marker.setAttribute('markerHeight', '7');
    marker.setAttribute('refX', '9');
    marker.setAttribute('refY', '3.5');
    marker.setAttribute('orient', 'auto');
    marker.setAttribute('markerUnits', 'strokeWidth');
    const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    polygon.setAttribute('points', '0 0, 10 3.5, 0 7');
    polygon.setAttribute('fill', 'red');
    marker.appendChild(polygon);
    defs.appendChild(marker);
    svg.appendChild(defs);
    // Arrow
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M${from.x},${from.y} L${to.x},${to.y}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'red');
    path.setAttribute('stroke-width', '4');
    path.setAttribute('marker-end', 'url(#arrowhead)');
    svg.appendChild(path);
    // Append SVG to grid
    $grid.css('position', 'relative');
    $grid.append(svg);
}

function clearHintArrow() {
    $('.chessboard-63f37 .hint-arrow-svg').remove();
}

function showToast(message, type = 'success') {
    const background = type === 'success'
        ? "linear-gradient(to right, #00b09b, #96c93d)"
        : type === 'error'
        ? "linear-gradient(to right, #ff5f6d, #ffc371)"
        : "linear-gradient(to right, #2196F3, #21CBF3)";
    Toastify({
        text: message,
        duration: 3000,
        gravity: "top",
        position: "right",
        backgroundColor: background,
        stopOnFocus: true,
    }).showToast();
}

function toggleButtonSpinner(buttonId, enable) {
    const $button = $(`#${buttonId}`);
    $button.find('.spinner').toggle(enable);
    $button.find('span:first').text(enable ? 'Loading...' : $button.find('span:first').data('original-text'));
    $button.prop('disabled', enable);
}

$(document).ready(function() {
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    const $html = $('html');
    if (isDarkMode) {
        $html.addClass('dark');
        $('#moon').removeClass('hidden');
        $('#sun').addClass('hidden');
        console.log("Loaded dark mode from localStorage");
    } else {
        $html.removeClass('dark');
        $('#sun').removeClass('hidden');
        $('#moon').addClass('hidden');
        console.log("Loaded light mode from localStorage");
    }

    $('#reset-button span:first').data('original-text', 'Reset');
    $('#save-button span:first').data('original-text', 'Save Game');
    $('#resume-button span:first').data('original-text', 'Resume Game');
    $('#hint-button span:first').data('original-text', 'Get Hint');
    $('#load-game-button span:first').data('original-text', 'Load Game');

    if (username) {
        $('#username-display').text(`Welcome, ${username}`);
        $('#logout-button').removeClass('hidden');
        $('#game-container').removeClass('hidden');
        initializeBoard();
    } else {
        window.location.href = '/login';
    }

    const $toggleButton = $('#dark-mode-toggle');
    if ($toggleButton.length === 0) {
        console.error("Dark mode toggle button not found in DOM!");
    } else {
        console.log("Dark mode toggle button found, attaching click event");
        $toggleButton.on('click', function() {
            console.log("Dark mode toggle clicked");
            $html.toggleClass('dark');
            const isDark = $html.hasClass('dark');
            localStorage.setItem('darkMode', isDark);
            $('#sun').toggleClass('hidden', isDark);
            $('#moon').toggleClass('hidden', !isDark);
            console.log("Switched to " + (isDark ? "dark" : "light") + " mode");
            console.log("Current classes on <html>:", $html.attr('class'));
        });
    }

    $('#interaction-mode').on('click', function() {
        useTapToMove = !useTapToMove;
        board = Chessboard('board', {
            draggable: !useTapToMove,
            position: game.fen(),
            onDrop: onDrop,
            onSnapEnd: onSnapEnd,
            onDragStart: onDragStart,
            onMouseoverSquare: onMouseoverSquare,
            onMouseoutSquare: onMouseoutSquare,
            onSquareClick: onSquareClick,
            pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
            orientation: playerColor.toLowerCase()
        });
        updateInteractionModeUI();
        showToast(`Switched to ${useTapToMove ? 'Tap to Move' : 'Drag to Move'} mode`);
    });

    $('#hint-button').on('click', function() {
        console.log("Hint button clicked");
        toggleButtonSpinner('hint-button', true);
        $.get('/hint', function(data) {
            console.log("Hint response:", data);
            const $hint = $('#hint');
            if (data.hint) {
                const fromSquare = data.hint.slice(0, 2);
                const toSquare = data.hint.slice(2, 4);
                drawHintArrow(fromSquare, toSquare);
                $hint.text(`Hint: ${data.hint}`).removeClass('hidden');
                setTimeout(() => {
                    clearHintArrow();
                    $hint.addClass('hidden');
                }, 5000);
            } else {
                $hint.text(data.message || 'No hint available').removeClass('hidden');
                setTimeout(() => $hint.addClass('hidden'), 5000);
            }
        }).fail(function(xhr, status, error) {
            console.error("Failed to fetch hint:", status, error);
            showToast("Failed to fetch hint", "error");
        }).always(function() {
            toggleButtonSpinner('hint-button', false);
        });
    });

    $('.promotion-option').on('click', function() {
        const promotion = $(this).data('promotion');
        console.log("Promotion chosen:", promotion);
        if (pendingMove) {
            const move = game.move({
                from: pendingMove.source,
                to: pendingMove.target,
                promotion: promotion
            });
            if (move === null) {
                console.error("Invalid promotion move");
                board.position(game.fen());
            } else {
                makeServerMove(pendingMove.source + pendingMove.target + promotion);
            }
            $('#promotion-modal').addClass('hidden');
            pendingMove = null;
        }
    });

    $('#reset-button').on('click', resetGame);
    $('#save-button').on('click', saveGame);
    $('#resume-button').on('click', showResumeModal);
    $('#load-game-button').on('click', resumeGame);
    $('#logout-button').on('click', logout);

    $(document).on('click', '#prev-move', function() {
        if (navMoveIndex === -1) navMoveIndex = fullMoveHistory.length;
        if (navMoveIndex > 1) {
            goToMove(navMoveIndex - 1);
        }
    });
    $(document).on('click', '#next-move', function() {
        if (navMoveIndex === -1) return; // Already live
        goToMove(navMoveIndex + 1);
    });

    setTimeout(() => {
        if (typeof game !== 'undefined' && game && typeof game.turn === 'function') {
            startGameWithTimers();
        }
    }, 1000);
});

function fetchFen() {
    $.get('/fen', function(data) {
        console.log("Fetched FEN response:", data);
        playerColor = data.player_color;
        currentGameId = data.game_id;
        board.orientation(playerColor.toLowerCase());
        board.position(data.fen);
        game.load(data.fen);
        updateProbability(data.probability);
        updateHistory(data.history);
        updateStatus();
    }).fail(function(xhr, status, error) {
        console.error("Failed to fetch FEN:", status, error);
        if (xhr.status === 401) {
            window.location.href = '/login';
        } else {
            showToast("Failed to load game state", "error");
        }
    });
}

function onDrop(source, target, piece, newPos, oldPos, orientation) {
    console.log("onDrop called:", source, target, piece);
    const move = {
        from: source,
        to: target,
        promotion: 'q'
    };
    const isPlayerTurn = (playerColor === 'White' && game.turn() === 'w') || (playerColor === 'Black' && game.turn() === 'b');
    if (!isPlayerTurn) {
        console.log("Not your turn!");
        return 'snapback';
    }
    if (game.game_over()) {
        console.log("Game is over, cannot make moves!");
        return 'snapback';
    }
    const pieceOnSquare = game.get(source);
    const isPawn = pieceOnSquare && pieceOnSquare.type === 'p';
    const isPromotion = isPawn && (
        (pieceOnSquare.color === 'w' && target.charAt(1) === '8') ||
        (pieceOnSquare.color === 'b' && target.charAt(1) === '1')
    );
    if (isPromotion) {
        console.log("Pawn promotion detected:", source, target);
        pendingMove = { source, target };
        $('#promotion-modal').removeClass('hidden');
        return;
    }
    const validMove = game.move(move);
    if (validMove === null) {
        console.log("Invalid move:", source, target);
        return 'snapback';
    }
    // Play sound
    if (game.in_check()) {
        checkSound.play();
    } else if (validMove.captured) {
        captureSound.play();
    } else {
        moveSound.play();
    }
    makeServerMove(source + target);
}

function makeServerMove(moveString) {
    console.log("Making server move:", moveString);
    toggleButtonSpinner('reset-button', true);
    $.ajax({
        url: '/move',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ move: moveString, difficulty: $('#difficulty').val(), player_color: playerColor }),
        success: function(response) {
            console.log("Move response:", response);
            if (response.error) {
                console.warn("Move error:", response.error);
                game.undo();
                board.position(game.fen());
                showToast(response.error, "error");
            } else {
                playerColor = response.player_color;
                currentGameId = response.game_id;
                board.orientation(playerColor.toLowerCase());
                board.position(response.fen);
                game.load(response.fen);
                // Update probability if the game is not over
                if (!response.result) {
                    updateProbability(response.probability);
                }
                updateHistory(response.history);
                // Handle game over
                if (response.result) {
                    let resultMessage;
                    if (
                        (response.result === "1-0" && playerColor === "White") ||
                        (response.result === "0-1" && playerColor === "Black")
                    ) {
                        resultMessage = "You win!";
                    } else if (response.result === "1/2-1/2") {
                        resultMessage = "Draw!";
                    } else {
                        resultMessage = "You lose!";
                    }
                    $('#probability').text(resultMessage);
                    $('.probability-fill').css('width', '0%');
                    showToast(resultMessage, "info");
                    // Disable further moves
                    board = Chessboard('board', {
                        draggable: !useTapToMove,
                        position: game.fen(),
                        onDrop: onDrop,
                        onSnapEnd: onSnapEnd,
                        onDragStart: onDragStart,
                        onMouseoverSquare: onMouseoverSquare,
                        onMouseoutSquare: onMouseoutSquare,
                        onSquareClick: onSquareClick,
                        pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
                        orientation: playerColor.toLowerCase()
                    });
                    $('#hint-button').prop('disabled', true);
                }
            }
            updateStatus();
            $('#hint').addClass('hidden');
            clearHintArrow();
            setTimeout(afterMoveSwitchTimer, 500);
        },
        error: function(xhr, status, error) {
            console.error("Move request failed:", status, error);
            if (xhr.status === 401) {
                window.location.href = '/login';
            } else {
                game.undo();
                board.position(game.fen());
                showToast("Failed to make move", "error");
            }
        },
        complete: function() {
            toggleButtonSpinner('reset-button', false);
        }
    });
}

function onSnapEnd() {
    board.position(game.fen());
}

function updateStatus() {
    if (game.game_over()) {
        if (game.in_checkmate()) {
            const winner = game.turn() === 'w' ? 'Black' : 'White';
            $('#status').text(`Checkmate! ${winner} wins!`);
        } else if (game.in_draw()) {
            $('#status').text('Draw!');
        } else if (game.in_stalemate()) {
            $('#status').text('Stalemate!');
        } else if (game.in_threefold_repetition()) {
            $('#status').text('Draw by threefold repetition!');
        } else if (game.insufficient_material()) {
            $('#status').text('Draw by insufficient material!');
        }
    } else if (game.in_check()) {
        $('#status').text('Check!');
    } else {
        const isPlayerTurn = (playerColor === 'White' && game.turn() === 'w') || (playerColor === 'Black' && game.turn() === 'b');
        $('#status').text(isPlayerTurn ? 'Your turn' : 'AI\'s turn');
    }
}

function updateProbability(probability) {
    console.log("Updating probability:", probability);
    $('.probability-fill').css('width', `${probability}%`);
    $('#probability').text(`Win Probability: ${Math.round(probability)}%`);
}

function updateHistory(history) {
    console.log('updateHistory called with:', history);
    const $historyList = $('#move-history');
    $historyList.empty();
    let tempGame = new Chess();
    let sanMoves = [];
    for (let i = 0; i < history.length; i++) {
        // Convert UCI to SAN for display
        let move = tempGame.move({ from: history[i].slice(0,2), to: history[i].slice(2,4), promotion: history[i].length > 4 ? history[i][4] : undefined });
        if (move) {
            sanMoves.push(move.san);
        }
    }
    for (let i = 0; i < sanMoves.length; i += 2) {
        const moveNumber = Math.floor(i / 2) + 1;
        const whiteMove = sanMoves[i] || "";
        const blackMove = sanMoves[i + 1] || "";
        $historyList.append(
            `<li class="flex space-x-2 py-1">
                <span class="w-8 font-semibold">${moveNumber}.</span>
                <span class="flex-1">${whiteMove}</span>
                <span class="flex-1">${blackMove}</span>
            </li>`
        );
    }
    $historyList.scrollTop($historyList[0].scrollHeight);
    // For navigation, use UCI moves directly
    updateMoveNavigation(history);
    console.log('fullMoveHistory after update:', fullMoveHistory);
}

function resetGame() {
    const difficulty = $('#difficulty').val();
    const player_color = $('#player-color').val();
    toggleButtonSpinner('reset-button', true);
    $.ajax({
        url: '/move',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ move: 'reset', difficulty: difficulty, player_color: player_color }),
        success: function(response) {
            console.log("Reset response:", response);
            playerColor = response.player_color;
            currentGameId = response.game_id;
            board = Chessboard('board', {
                draggable: !useTapToMove,
                position: response.fen,
                onDrop: onDrop,
                onSnapEnd: onSnapEnd,
                onDragStart: onDragStart,
                onMouseoverSquare: onMouseoverSquare,
                onMouseoutSquare: onMouseoutSquare,
                onSquareClick: onSquareClick,
                pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
                orientation: playerColor.toLowerCase()
            });
            game.load(response.fen);
            updateProbability(response.probability);
            updateHistory(response.history);
            updateStatus();
            $('#hint').addClass('hidden');
            clearHintArrow();
            $('#hint-button').prop('disabled', false);
            showToast("Game reset successfully", "success");
            setTimeout(startGameWithTimers, 500);
        },
        error: function(xhr, status, error) {
            console.error("Reset failed:", status, error);
            if (xhr.status === 401) {
                window.location.href = '/login';
            } else {
                showToast("Failed to reset game", "error");
            }
        },
        complete: function() {
            toggleButtonSpinner('reset-button', false);
        }
    });
}

function saveGame() {
    toggleButtonSpinner('save-button', true);
    $.ajax({
        url: '/save_game',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({}),
        success: function(response) {
            console.log("Save game response:", response);
            currentGameId = response.game_id;
            showToast(`Game saved! Game ID: ${currentGameId}`, "success");
        },
        error: function(xhr, status, error) {
            console.error("Failed to save game:", status, error);
            if (xhr.status === 401) {
                window.location.href = '/login';
            } else {
                showToast("Failed to save game", "error");
            }
        },
        complete: function() {
            toggleButtonSpinner('save-button', false);
        }
    });
}

function showResumeModal() {
    toggleButtonSpinner('resume-button', true);
    $.ajax({
        url: '/user_games',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({}),
        success: function(response) {
            console.log("User games response:", response);
            const $gameList = $('#game-list');
            $gameList.empty();
            if (response.games.length === 0) {
                $gameList.append('<option>No saved games found</option>');
                $('#load-game-button').prop('disabled', true);
            } else {
                response.games.forEach(game => {
                    $gameList.append(`<option value="${game.game_id}">[${game.game_id}] Created: ${game.created_at}, Last Updated: ${game.updated_at}</option>`);
                });
                $('#load-game-button').prop('disabled', false);
            }
            $('#resume-modal').removeClass('hidden');
        },
        error: function(xhr, status, error) {
            console.error("Failed to fetch user games:", status, error);
            if (xhr.status === 401) {
                window.location.href = '/login';
            } else {
                showToast("Failed to fetch saved games", "error");
            }
        },
        complete: function() {
            toggleButtonSpinner('resume-button', false);
        }
    });
}

function resumeGame() {
    const gameId = $('#game-list').val();
    if (!gameId || $('#game-list option').length === 0 || $('#game-list option:first').text() === 'No saved games found') {
        showToast("Please select a game to resume", "error");
        return;
    }
    toggleButtonSpinner('load-game-button', true);
    $.ajax({
        url: '/resume_game',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ game_id: gameId }),
        success: function(response) {
            console.log("Resume game response:", response);
            if (response.error) {
                showToast("Failed to resume game: " + response.error, "error");
            } else {
                playerColor = response.player_color;
                currentGameId = response.game_id;
                board = Chessboard('board', {
                    draggable: !useTapToMove,
                    position: response.fen,
                    onDrop: onDrop,
                    onSnapEnd: onSnapEnd,
                    onDragStart: onDragStart,
                    onMouseoverSquare: onMouseoverSquare,
                    onMouseoutSquare: onMouseoutSquare,
                    onSquareClick: onSquareClick,
                    pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
                    orientation: playerColor.toLowerCase()
                });
                game.load(response.fen);
                updateProbability(response.probability);
                updateHistory(response.history);
                updateStatus();
                $('#hint').addClass('hidden');
                clearHintArrow();
                $('#resume-modal').addClass('hidden');
                $('#hint-button').prop('disabled', false);
                showToast("Game resumed successfully", "success");
                setTimeout(startGameWithTimers, 500);
            }
        },
        error: function(xhr, status, error) {
            console.error("Failed to resume game:", status, error);
            if (xhr.status === 401) {
                window.location.href = '/login';
            } else {
                showToast("Failed to resume game", "error");
            }
        },
        complete: function() {
            toggleButtonSpinner('load-game-button', false);
        }
    });
}

function logout() {
    $.ajax({
        url: '/logout',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({}),
        success: function(response) {
            console.log("Logout response:", response);
            localStorage.removeItem('username');
            username = null;
            $('#username-display').text('');
            $('#logout-button').addClass('hidden');
            $('#game-container').addClass('hidden');
            window.location.href = '/login';
            showToast("Logged out successfully", "success");
        },
        error: function(xhr, status, error) {
            console.error("Logout failed:", status, error);
            showToast("Failed to logout", "error");
        }
    });
}

function updateMoveNavigation(history) {
    fullMoveHistory = history.slice();
    navMoveIndex = -1;
    updateNavButtons();
    console.log('updateMoveNavigation: fullMoveHistory =', fullMoveHistory, 'navMoveIndex =', navMoveIndex);
}

function updateNavButtons() {
    // Disable prev if at first move, next if at latest
    const atLive = navMoveIndex === -1;
    const atFirstMove = navMoveIndex === 1;
    $('#prev-move').prop('disabled', atLive ? fullMoveHistory.length <= 1 : atFirstMove);
    $('#next-move').prop('disabled', atLive);
    if (atLive) {
        $('#next-move').attr('title', 'Already at latest move');
    } else {
        $('#next-move').attr('title', 'Go forward');
    }
}

function goToMove(index) {
    if (index < 1) index = 1; // Never show starting position
    if (index > fullMoveHistory.length) index = fullMoveHistory.length;
    const tempGame = new Chess();
    for (let i = 0; i < index; i++) {
        tempGame.move(fullMoveHistory[i]);
    }
    board.position(tempGame.fen());
    navMoveIndex = index;
    if (navMoveIndex === fullMoveHistory.length) {
        board.position(game.fen());
        navMoveIndex = -1;
    }
    updateNavButtons();
}

function getTimeControlSeconds() {
    const mode = $('#time-control').val();
    if (mode === 'blitz') return 300;
    if (mode === 'rapid') return 900;
    if (mode === 'classical') return 1800;
    return 300;
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

function updateTimerDisplays() {
    $('#white-timer').text(formatTime(whiteTime));
    $('#black-timer').text(formatTime(blackTime));
}

function stopAllTimers() {
    clearInterval(whiteTimerInterval);
    clearInterval(blackTimerInterval);
    whiteTimerInterval = null;
    blackTimerInterval = null;
}

function startTimer(color) {
    stopAllTimers();
    if (color === 'w') {
        whiteTimerInterval = setInterval(() => {
            whiteTime--;
            updateTimerDisplays();
            if (whiteTime <= 0) {
                stopAllTimers();
                showTimeout('White');
            }
        }, 1000);
    } else {
        blackTimerInterval = setInterval(() => {
            blackTime--;
            updateTimerDisplays();
            if (blackTime <= 0) {
                stopAllTimers();
                showTimeout('Black');
            }
        }, 1000);
    }
}

function showTimeout(color) {
    showToast(`${color} ran out of time!`, 'error');
    // Disable the board and show losing state
    board = Chessboard('board', {
        draggable: false,
        position: game.fen(),
        pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
        orientation: playerColor.toLowerCase()
    });
    stopAllTimers();
    // Show losing state in status and probability
    if (color === 'White') {
        $('#status').text('White lost on time!');
        $('#probability').text('You lose!');
        $('.probability-fill').css('width', '0%');
    } else {
        $('#status').text('Black lost on time!');
        $('#probability').text('You lose!');
        $('.probability-fill').css('width', '0%');
    }
    $('#hint-button').prop('disabled', true);
}

function resetTimers() {
    const seconds = getTimeControlSeconds();
    whiteTime = seconds;
    blackTime = seconds;
    updateTimerDisplays();
    stopAllTimers();
}

// --- Patch into game logic ---
function startGameWithTimers() {
    resetTimers();
    // Start timer for the player to move
    activeColor = game.turn();
    startTimer(activeColor);
}

// Switch timers after each move
function afterMoveSwitchTimer() {
    activeColor = game.turn();
    startTimer(activeColor);
}