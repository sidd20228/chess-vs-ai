let board;
let game;
let playerColor = 'White';

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

$(document).ready(function() {
    // Load dark mode preference from localStorage
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

    // Dark mode toggle
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
    let move = game.move({
        from: source,
        to: target,
        promotion: 'q'
    });

    if (move === null) return 'snapback';

    $.ajax({
        url: '/move',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ move: source + target }),
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
        }
    });
}