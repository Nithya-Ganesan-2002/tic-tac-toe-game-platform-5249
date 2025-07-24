from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from uuid import uuid4

app = FastAPI(
    title="Tic Tac Toe Game Platform",
    description="Backend API for user authentication and game management (creation, move submission, history, score tracking) for Tic Tac Toe.",
    version="0.1.0",
    openapi_tags=[
        {"name": "users", "description": "User registration, login, and user info endpoints."},
        {"name": "games", "description": "Game creation, move submission, game state endpoints."},
        {"name": "scores", "description": "Score tracking and leaderboard endpoints."}
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory mock storage (replaceable with persistent DB) ---
users_db: Dict[str, dict] = {}  # key: username, value: {username, password, scores}
tokens_db: Dict[str, str] = {}  # key: token, value: username
games_db: Dict[str, dict] = {}  # key: game_id, value: game dict

# --- Models ---

class RegisterRequest(BaseModel):
    username: str = Field(..., description="User's unique username.")
    password: str = Field(..., description="Password for authentication.")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class GameCreateRequest(BaseModel):
    opponent: str = Field(..., description="Username of the opponent.")

class GameState(BaseModel):
    game_id: str
    players: List[str] = Field(..., description="List of participating players (X and O).")
    board: List[List[Optional[str]]] = Field(..., description="3x3 board state, each cell is 'X', 'O', or None.")
    next_turn: str = Field(..., description="'X' or 'O'; whose move is next.")
    winner: Optional[str] = Field(None, description="Username of the winner, if any.")
    moves: List[dict] = Field(..., description="List of moves with details.")

class MoveRequest(BaseModel):
    row: int = Field(..., description="Row index (0-2) for move.")
    col: int = Field(..., description="Column index (0-2) for move.")

class MoveRecord(BaseModel):
    player: str
    symbol: str
    row: int
    col: int

class GameHistoryResponse(BaseModel):
    game_id: str
    history: List[MoveRecord]
    winner: Optional[str] = None

class ScoreEntry(BaseModel):
    username: str
    wins: int = 0
    losses: int = 0
    draws: int = 0

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def authenticate_user(username: str, password: str) -> bool:
    user = users_db.get(username)
    return user is not None and user["password"] == password

def get_user_from_token(token: str = Depends(oauth2_scheme)):
    username = tokens_db.get(token)
    if username is None or username not in users_db:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return username

@app.get("/", tags=["health"])
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}

# PUBLIC_INTERFACE
@app.post("/register", summary="Register a new user", description="Creates a new user account.", tags=["users"])
def register(request: RegisterRequest):
    """Register a new user."""
    username = request.username
    if username in users_db:
        raise HTTPException(status_code=400, detail="Username already exists.")
    users_db[username] = {"username": username, "password": request.password, "scores": {"wins": 0, "losses": 0, "draws": 0}}
    return {"message": "User registered successfully."}

# PUBLIC_INTERFACE
@app.post("/token", response_model=TokenResponse, summary="User login", description="Authenticate and return access token.", tags=["users"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and provide a token."""
    username = form_data.username
    password = form_data.password
    if not authenticate_user(username, password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    # mock a token
    token = str(uuid4())
    tokens_db[token] = username
    return TokenResponse(access_token=token)

# PUBLIC_INTERFACE
@app.get("/me", summary="Get current user profile", tags=["users"])
def get_me(username: str = Depends(get_user_from_token)):
    """Return current authenticated user's info and score."""
    user = users_db.get(username)
    return {"username": user["username"], "scores": user["scores"]}

# PUBLIC_INTERFACE
@app.post("/games", response_model=GameState, summary="Create a new game", description="Create a Tic Tac Toe game with another player.", tags=["games"])
def create_game(request: GameCreateRequest, username: str = Depends(get_user_from_token)):
    """Create a new game."""
    if request.opponent not in users_db:
        raise HTTPException(status_code=404, detail="Opponent does not exist")
    if request.opponent == username:
        raise HTTPException(status_code=400, detail="Cannot play against yourself.")
    game_id = str(uuid4())
    players = [username, request.opponent]
    board = [[None for _ in range(3)] for _ in range(3)]
    games_db[game_id] = {
        "game_id": game_id,
        "players": players,
        "symbols": {players[0]: "X", players[1]: "O"},  # first user is X
        "board": board,
        "moves": [],
        "next_turn": players[0],
        "winner": None,
    }
    return GameState(
        game_id=game_id,
        players=players,
        board=board,
        next_turn=players[0],
        winner=None,
        moves=[]
    )

# PUBLIC_INTERFACE
@app.get("/games/{game_id}", response_model=GameState, summary="Get game state", tags=["games"])
def get_game(game_id: str, username: str = Depends(get_user_from_token)):
    """Return current state of a game."""
    game = games_db.get(game_id)
    if not game or username not in game["players"]:
        raise HTTPException(status_code=404, detail="Game not found or access denied")
    return GameState(
        game_id=game["game_id"],
        players=game["players"],
        board=game["board"],
        next_turn=game["next_turn"],
        winner=game["winner"],
        moves=game["moves"]
    )

# PUBLIC_INTERFACE
@app.post("/games/{game_id}/move", response_model=GameState, summary="Submit a move", tags=["games"])
def submit_move(game_id: str, move: MoveRequest, username: str = Depends(get_user_from_token)):
    """Submit a move for a game."""
    game = games_db.get(game_id)
    if not game or username not in game["players"]:
        raise HTTPException(status_code=404, detail="Game not found or access denied")
    if game["winner"]:
        raise HTTPException(status_code=400, detail="Game already has a winner.")
    symbol = game["symbols"][username]
    row, col = move.row, move.col
    if game["next_turn"] != username:
        raise HTTPException(status_code=400, detail="It is not your turn.")
    if not (0 <= row < 3 and 0 <= col < 3):
        raise HTTPException(status_code=400, detail="Invalid board position.")
    if game["board"][row][col] is not None:
        raise HTTPException(status_code=400, detail="Cell already taken.")
    game["board"][row][col] = symbol
    move_record = {"player": username, "symbol": symbol, "row": row, "col": col}
    game["moves"].append(move_record)
    # Switch turns
    next_player = [p for p in game["players"] if p != username][0]
    game["next_turn"] = next_player

    # Check winner or draw
    winner = check_winner(game["board"])
    if winner:
        game["winner"] = username  # current movemaker is winner
        users_db[username]["scores"]["wins"] += 1
        users_db[next_player]["scores"]["losses"] += 1
    elif is_draw(game["board"]):
        game["winner"] = "draw"
        users_db[username]["scores"]["draws"] += 1
        users_db[next_player]["scores"]["draws"] += 1

    return GameState(
        game_id=game["game_id"],
        players=game["players"],
        board=game["board"],
        next_turn=game["next_turn"],
        winner=game["winner"],
        moves=game["moves"]
    )

def check_winner(board: List[List[Optional[str]]]) -> Optional[str]:
    """Return player symbol ('X' or 'O') that has won, if any."""
    for s in ("X", "O"):
        bs = board
        # Check rows, columns, diagonals
        if any(all(cell == s for cell in row) for row in bs):
            return s
        if any(all(bs[i][j] == s for i in range(3)) for j in range(3)):
            return s
        if all(bs[i][i] == s for i in range(3)) or all(bs[i][2-i] == s for i in range(3)):
            return s
    return None

def is_draw(board: List[List[Optional[str]]]) -> bool:
    return all(board[i][j] is not None for i in range(3) for j in range(3))

# PUBLIC_INTERFACE
@app.get("/games", response_model=List[GameState], summary="Get user's games", description="Get all games for the authenticated user.", tags=["games"])
def get_user_games(username: str = Depends(get_user_from_token)):
    """Retrieve all games the user is in."""
    result = []
    for g in games_db.values():
        if username in g["players"]:
            result.append(GameState(
                game_id=g["game_id"],
                players=g["players"],
                board=g["board"],
                next_turn=g["next_turn"],
                winner=g["winner"],
                moves=g["moves"]
            ))
    return result

# PUBLIC_INTERFACE
@app.get("/games/{game_id}/history", response_model=GameHistoryResponse, summary="Game move history", tags=["games"])
def get_game_history(game_id: str, username: str = Depends(get_user_from_token)):
    """Return move history for a specific game."""
    game = games_db.get(game_id)
    if not game or username not in game["players"]:
        raise HTTPException(status_code=404, detail="Game not found or access denied")
    moves = [MoveRecord(**m) for m in game["moves"]]
    return GameHistoryResponse(
        game_id=game_id,
        history=moves,
        winner=game.get("winner")
    )

# PUBLIC_INTERFACE
@app.get("/leaderboard", response_model=List[ScoreEntry], summary="Get global leaderboard", tags=["scores"])
def get_leaderboard():
    """Return all users, sorted by number of wins."""
    all_scores = []
    for user in users_db.values():
        entry = ScoreEntry(
            username=user["username"],
            wins=user["scores"]["wins"],
            losses=user["scores"]["losses"],
            draws=user["scores"]["draws"]
        )
        all_scores.append(entry)
    all_scores.sort(key=lambda s: s.wins, reverse=True)
    return all_scores
