# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Search for games of moves and answers: what a duellist, a card player or a tactician looks ahead with.

A game state offers:

- ``moves()``: the moves the side to play has (a list; empty when the game is over)
- ``play(move)``: the state after that move (a new state; the old one unchanged)
- ``done()``: whether the game is over
- ``score()``: how good the state is for the side to play now, from -1 (lost) to 1 (won); for an
  unfinished state, a guess

Two ways to choose a move:

- ``best(state, depth)``: negamax with alpha-beta - for games where both sides see everything (tactics,
  a duel of positions). Exact to its depth.
- ``mcts(state, rng, playouts)``: Monte Carlo tree search - for games with chance or many moves (cards):
  playouts to the end (or ``horizon`` moves) from each choice, the most visited move wins.

Both stop at a **budget** counted in states looked at, never in time, so they choose the same on any
machine (the engine's rule: same state, same choice). Ties go to the earlier move in ``moves()``, and
the sums use no function a machine might round its own way (a log of its own; ``sqrt`` is exact).
"""
from __future__ import annotations

import math


class Budget:
    def __init__(self, nodes):
        self.left = int(nodes)

    def spend(self):
        self.left -= 1
        return self.left >= 0


def best(state, depth=4, nodes=20000):
    """``(move, score)``: the move with the best score ``depth`` moves ahead (negamax, alpha-beta)."""
    budget = Budget(nodes)
    moves = state.moves()
    if not moves:
        return None, state.score()
    choice, top = moves[0], -math.inf
    alpha, beta = -math.inf, math.inf
    for mv in moves:
        v = -_negamax(state.play(mv), depth - 1, -beta, -alpha, budget)
        if v > top:
            choice, top = mv, v
        alpha = max(alpha, v)
        if budget.left < 0:
            break
    return choice, top


def _negamax(state, depth, alpha, beta, budget):
    if not budget.spend() or depth <= 0 or state.done():
        return state.score()
    moves = state.moves()
    if not moves:
        return state.score()
    value = -math.inf
    for mv in moves:
        value = max(value, -_negamax(state.play(mv), depth - 1, -beta, -alpha, budget))
        alpha = max(alpha, value)
        if alpha >= beta:
            break
    return value


_LN2 = 0.6931471805599453


def _ln(x):
    """The natural log by + - * / only, so it comes out the same to the last bit on every machine (``math.log``
    is left to the platform's library): x = m * 2**e, ln m = 2 atanh((m - 1) / (m + 1))."""
    m, e = math.frexp(x)                                    # exact: 0.5 <= m < 1
    m, e = m * 2.0, e - 1
    z = (m - 1.0) / (m + 1.0)
    z2, term, total, k = z * z, z, 0.0, 1
    while k < 60:
        total += term / k
        term *= z2
        k += 2
    return e * _LN2 + 2.0 * total


class _Node:
    __slots__ = ("move", "parent", "children", "untried", "visits", "wins", "who")

    def __init__(self, move, parent, moves, who=None):
        self.move, self.parent = move, parent
        self.children = []
        self.untried = list(moves)
        self.visits = 0
        self.wins = 0.0
        self.who = who                                      # the side that made ``move``


def _side(state, depth):
    """Whose move it is: the state's ``to_play()`` if it has one (a side may make several moves in a row, as
    in cards), else the sides take turns."""
    to_play = getattr(state, "to_play", None)
    return to_play() if to_play is not None else depth % 2


def mcts(state, rng, playouts=400, horizon=60, c=1.4):
    """The move most often chosen by ``playouts`` games played on from here (UCT); ``rng`` is the caller's
    random generator - the level's, so that it is part of what a save keeps."""
    visits = mcts_visits(state, rng, playouts, horizon, c)
    if not visits:
        return None
    best = max(range(len(visits)), key=lambda i: (visits[i][1], -i))
    return visits[best][0]


def mcts_visits(state, rng, playouts=400, horizon=60, c=1.4):
    """``[(move, visits)]`` for the moves from here, in ``moves()``'s order, after ``playouts`` games (UCT).
    Add the visits of searches from several guesses at what cannot be seen, and the most visited move is the
    choice of an information-set search (cards in a hand one does not know)."""
    moves = state.moves()
    if not moves:
        return []
    if len(moves) == 1:
        return [(moves[0], 1)]
    root = _Node(None, None, moves)
    for _ in range(int(playouts)):
        node, s, depth = root, state, 0
        while not node.untried and node.children:           # down the tree by UCT
            node = max(node.children, key=lambda n: (n.wins / n.visits
                                                      + c * math.sqrt(_ln(node.visits) / n.visits)))
            s = s.play(node.move)
            depth += 1
        if node.untried and not s.done():                   # one new move
            mv = node.untried.pop(0)
            who = _side(s, depth)
            s = s.play(mv)
            depth += 1
            child = _Node(mv, node, s.moves(), who)
            node.children.append(child)
            node = child
        steps = 0                                           # a game played on at random
        while not s.done() and steps < horizon:
            ms = s.moves()
            if not ms:
                break
            s = s.play(ms[rng.randrange(len(ms))])
            steps += 1
        result = s.score()                                  # for the side to play at the end ...
        last = _side(s, depth + steps)
        while node is not None:                             # ... and so for each move's maker, up the tree
            node.visits += 1
            if node.who is not None:
                node.wins += ((result if node.who == last else -result) + 1) / 2.0
            node = node.parent
    seen = {repr(n.move): n.visits for n in root.children}
    return [(mv, seen.get(repr(mv), 0)) for mv in moves]
