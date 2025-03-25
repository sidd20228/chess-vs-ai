let board;
let game;
let playerColor = 'White';
let pendingMove = null;

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
        draggable: true,
        position: 'start',
        onDrop: onDrop,
        onSnapEnd: onSnapEnd,
        pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
        orientation: playerColor.toLowerCase()
    });
    updateStatus();
    fetchFen();
}

function squareToCoords(square, boardSize) {
    const files = 'abcdefgh';
    const file = files.indexOf(square[0]); // a=0, h=7
    const rank = parseInt(square[1]); // 1=1, 8=8

    const squareSize = boardSize / 8;
    let x, y;

    if (playerColor.toLowerCase() === 'white') {
        // White perspective: a1 at bottom-left
        x = file * squareSize; // a=0 (left), h=7*squareSize (right)
        y = (8 - rank) * squareSize; // 1=7*squareSize (bottom), 8=0 (top)
    } else {
        // Black perspective: h8 at bottom-left
        x = (7 - file) * squareSize; // h=0 (left), a=7*squareSize (right)
        y = (rank - 1) * squareSize; // 8=7*squareSize (bottom), 1=0 (top)
    }

    return { x: x + squareSize / 2, y: y + squareSize / 2 }; // Center of square
}

function drawHintArrow(fromSquare, toSquare) {
    const boardSize = $('#board').width(); // Dynamic board size
    const from = squareToCoords(fromSquare, boardSize);
    const to = squareToCoords(toSquare, boardSize);

    console.log(`Drawing hint arrow: ${fromSquare} (${from.x}, ${from.y}) to ${toSquare} (${to.x}, ${to.y})`);

    const $arrow = $('#hint-arrow path');
    const path = `M${from.x},${from.y} L${to.x},${to.y}`;
    $arrow.attr('d', path);
    $('#hint-arrow').removeClass('hidden').attr('class', 'absolute inset-0 w-full h-full pointer-events-none text-red-500 dark:text-red-400');
}

function clearHintArrow() {
    $('#hint-arrow').addClass('hidden');
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

    initializeBoard();

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

    $('#hint-button').on('click', function() {
        console.log("Hint button clicked");
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
            $('#hint').text('Error fetching hint').removeClass('hidden');
            setTimeout(() => $('#hint').addClass('hidden'), 5000);
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
});

function fetchFen() {
    $.get('/fen', function(data) {
        console.log("Fetched FEN response:", data);
        playerColor = data.player_color;
        board.orientation(playerColor.toLowerCase());
        board.position(data.fen);
        game.load(data.fen);
        updateProbability(data.probability);
        updateHistory(data.history);
        updateStatus();
    }).fail(function(xhr, status, error) {
        console.error("Failed to fetch FEN:", status, error);
    });
}

function onDrop(source, target) {
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

    const piece = game.get(source);
    const isPawn = piece && piece.type === 'p';
    const isPromotion = isPawn && (
        (piece.color === 'w' && target.charAt(1) === '8') ||
        (piece.color === 'b' && target.charAt(1) === '1')
    );

    if (isPromotion) {
        console.log("Pawn promotion detected:", source, target);
        pendingMove = { source, target };
        $('#promotion-modal').removeClass('hidden');
        return;
    }

    const validMove = game.move(move);
    if (validMove === null) return 'snapback';

    makeServerMove(source + target);
}

function makeServerMove(moveString) {
    $.ajax({
        url: '/move',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ move: moveString }),
        success: function(response) {
            console.log("Move response:", response);
            if (response.error) {
                console.warn("Move error:", response.error);
                game.undo();
                board.position(game.fen());
            } else {
                playerColor = response.player_color;
                board.orientation(playerColor.toLowerCase());
                board.position(response.fen);
                game.load(response.fen);
                updateProbability(response.probability);
                updateHistory(response.history);
                if (response.result) {
                    $('#status').text(`Game Over: ${response.result}`);
                }
            }
            updateStatus();
            $('#hint').addClass('hidden');
            clearHintArrow();
        },
        error: function(xhr, status, error) {
            console.error("Move request failed:", status, error);
            game.undo();
            board.position(game.fen());
        }
    });
}

function onSnapEnd() {
    board.position(game.fen());
}

function updateStatus() {
    let status = game.turn() === 'w' ? 'White to move' : 'Black to move';
    if (game.in_checkmate()) status = 'Checkmate';
    else if (game.in_draw()) status = 'Draw';
    $('#status').text(status);
}

function updateProbability(probability) {
    console.log("Updating probability:", probability);
    $('.probability-fill').css('width', `${probability}%`);
    $('#probability').text(`${Math.round(probability)}%`);
}

function updateHistory(history) {
    const $historyList = $('#move-history');
    $historyList.empty();
    history.forEach((move, index) => {
        const moveNum = Math.floor(index / 2) + 1;
        const color = index % 2 === 0 ? 'White' : 'Black';
        $historyList.append(`<li class="py-2">${moveNum}. ${color}: ${move}</li>`);
    });
}

function resetGame() {
    const difficulty = $('#difficulty').val();
    const player_color = $('#player-color').val();
    $.ajax({
        url: '/move',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ move: 'reset', difficulty: difficulty, player_color: player_color }),
        success: function(response) {
            console.log("Reset response:", response);
            playerColor = response.player_color;
            board = Chessboard('board', {
                draggable: true,
                position: response.fen,
                onDrop: onDrop,
                onSnapEnd: onSnapEnd,
                pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
                orientation: playerColor.toLowerCase()
            });
            game.load(response.fen);
            updateProbability(response.probability);
            updateHistory(response.history);
            updateStatus();
            $('#hint').addClass('hidden');
            clearHintArrow();
        }
    });
}