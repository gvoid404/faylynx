import { countWebsiteVersion, postComplete, redirectToCompletionPage } from '../script.js';

export function init() {
    // Load game.css
    if (!document.querySelector('link[href*="game.css"]')) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'css/game.css';
        document.head.appendChild(link);
    }

    const COLS = 3;
    const ROWS = 2;
    const SOLVED = [1, 2, 3, 4, 5, 0]; // 0 = empty slot

    let cells = [];
    let solved = false;
    let tileEls = [];

    const board = document.getElementById('puzzle-board');
    const status = document.getElementById('game-status');
    const shuffleBtn = document.getElementById('shuffle-btn');

    function isSolved(state) {
        return state.every((v, i) => v === SOLVED[i]);
    }

    function shuffle() {
        let state = SOLVED.slice();
        let blank = state.indexOf(0);
        let lastBlank = -1;

        // Random valid slides from the solved state keep the puzzle solvable.
        for (let i = 0; i < 60; i++) {
            const neighbors = getNeighbors(blank).filter(n => n !== lastBlank);
            const next = neighbors[Math.floor(Math.random() * neighbors.length)];
            [state[blank], state[next]] = [state[next], state[blank]];
            lastBlank = blank;
            blank = next;
        }

        // Never start from the solved state.
        if (isSolved(state)) {
            const neighbors = getNeighbors(blank);
            const next = neighbors[0];
            [state[blank], state[next]] = [state[next], state[blank]];
        }

        return state;
    }

    function getNeighbors(index) {
        const row = Math.floor(index / COLS);
        const col = index % COLS;
        const neighbors = [];
        if (col > 0) neighbors.push(index - 1);
        if (col < COLS - 1) neighbors.push(index + 1);
        if (row > 0) neighbors.push(index - COLS);
        if (row < ROWS - 1) neighbors.push(index + COLS);
        return neighbors;
    }

    // Tiles are created once and only their text changes on a move, so each
    // cell keeps a stable DOM element and id across moves.
    function buildBoard() {
        board.innerHTML = '';
        tileEls = [];
        for (let i = 0; i < cells.length; i++) {
            const cell = document.createElement('div');
            cell.id = `tile-cell-${i}`;
            cell.dataset.index = i;
            board.appendChild(cell);
            tileEls.push(cell);
        }
    }

    function render() {
        cells.forEach((value, i) => {
            const cell = tileEls[i];
            if (value === 0) {
                cell.className = 'tile empty';
                cell.textContent = '';
                cell.removeAttribute('aria-label');
            } else {
                cell.className = 'tile';
                cell.textContent = value;
                cell.setAttribute('aria-label', `Tile ${value}`);
            }
        });
        board.classList.toggle('solved', solved);
    }

    function handleClick(e) {
        if (solved) return;

        const tile = e.target.closest('.tile');
        if (!tile || tile.classList.contains('empty')) return;

        const index = Number(tile.dataset.index);
        const blank = cells.indexOf(0);

        if (!getNeighbors(blank).includes(index)) return;

        [cells[blank], cells[index]] = [cells[index], cells[blank]];
        render();
        checkWin();
    }

    function checkWin() {
        if (!isSolved(cells)) return;

        solved = true;
        status.textContent = '🎉 Solved! Nice work.';
        render();

        postComplete({ "webpage": "game" });
        const websiteVersion = location.pathname.split("/")[1] || "";
        if (websiteVersion === countWebsiteVersion) {
            let gameCounts = Number(localStorage.getItem("game"));
            gameCounts++;
            localStorage.setItem("game", gameCounts);
            if (gameCounts >= 3) {
                redirectToCompletionPage("game");
            }
        }
    }

    function newPuzzle() {
        cells = shuffle();
        solved = false;
        status.textContent = '';
        render();
    }

    board.addEventListener('click', handleClick);
    shuffleBtn.addEventListener('click', newPuzzle);

    cells = shuffle();
    buildBoard();
    render();
}

// Cleanup function to remove event listeners when navigating away
export function cleanup() {
    console.log('Cleaning up game page');
}
