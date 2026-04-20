"""
Formula Runtime — Safe Python Expression Executor
==================================================
Executes LLM-translated Python formulas at runtime.
Uses AST-based evaluation for safety — no exec() or eval() of raw strings.

Features:
  - AST whitelist: only allows safe operations (math, indexing, comparisons)
  - Input substitution: replaces field references with actual user values
  - Lookup data access: provides in-memory lookup tables as dicts
  - Deterministic: same inputs always produce same outputs
"""

from __future__ import annotations

import ast
import logging
import math
import operator
from typing import Any

logger = logging.getLogger(__name__)

# ── Safe operations whitelist ────────────────────────────────────────

_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_SAFE_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_SAFE_COMPAREOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_SAFE_BUILTINS = {
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "int": int,
    "float": float,
    "str": str,
    "len": len,
    "bool": bool,
    "pow": pow,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    # Math functions
    "math_ceil": math.ceil,
    "math_floor": math.floor,
    "math_log": math.log,
    "math_log10": math.log10,
    "math_exp": math.exp,
    "math_sqrt": math.sqrt,
}

# Names that are NEVER allowed (security)
_FORBIDDEN_NAMES = {
    "__import__", "eval", "exec", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "__builtins__", "open",
    "breakpoint", "exit", "quit", "input", "print",
}


class FormulaRuntime:
    """
    Safely executes LLM-translated Python expressions.
    Uses AST parsing and a restricted evaluator — no raw eval/exec.
    """

    def execute_expression(
        self,
        expression: str,
        inputs: dict[str, Any],
        lookup_data: dict[str, Any],
    ) -> Any:
        """
        Execute a Python expression with the given inputs and lookup data.

        Parameters
        ----------
        expression : str
            Python expression (e.g. "round(inputs['Age'] * 0.5, 2)")
        inputs : dict
            Field name → value mapping from user inputs
        lookup_data : dict
            Sheet name → table data (list of dicts or similar)

        Returns
        -------
        Any
            The computed result, or None if evaluation fails.
        """
        if not expression or not expression.strip():
            return None

        # Security check: reject forbidden names (whole-word match)
        import re as _re
        for forbidden in _FORBIDDEN_NAMES:
            if _re.search(r'\b' + _re.escape(forbidden) + r'\b', expression):
                logger.warning("Forbidden name '%s' in expression — rejected", forbidden)
                return None

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            logger.warning("Failed to parse expression: %s — %s", expression[:100], e)
            return None

        # Build execution context
        context = {
            "inputs": inputs,
            "lookup_data": lookup_data,
            **_SAFE_BUILTINS,
        }

        try:
            result = self._eval_node(tree.body, context)
            return result
        except Exception as e:
            logger.warning("Expression evaluation failed: %s — %s", expression[:100], e)
            return None

    def _eval_node(self, node: ast.AST, context: dict) -> Any:
        """Recursively evaluate an AST node in a restricted context."""

        # Literals
        if isinstance(node, ast.Constant):
            return node.value

        # Variable names
        if isinstance(node, ast.Name):
            name = node.id
            if name in _FORBIDDEN_NAMES:
                raise ValueError(f"Forbidden name: {name}")
            if name in context:
                return context[name]
            raise NameError(f"Unknown variable: {name}")

        # Binary operations (+, -, *, /, etc.)
        if isinstance(node, ast.BinOp):
            op_func = _SAFE_BINOPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            return op_func(left, right)

        # Unary operations (+x, -x)
        if isinstance(node, ast.UnaryOp):
            op_func = _SAFE_UNARYOPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
            return op_func(self._eval_node(node.operand, context))

        # Boolean operations (and, or)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for val in node.values:
                    result = self._eval_node(val, context)
                    if not result:
                        return result
                return result
            elif isinstance(node.op, ast.Or):
                result = False
                for val in node.values:
                    result = self._eval_node(val, context)
                    if result:
                        return result
                return result

        # Comparisons
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                op_func = _SAFE_COMPAREOPS.get(type(op))
                if op_func is None:
                    raise ValueError(f"Unsupported compare op: {type(op).__name__}")
                if not op_func(left, right):
                    return False
                left = right
            return True

        # If expressions (ternary: x if cond else y)
        if isinstance(node, ast.IfExp):
            cond = self._eval_node(node.test, context)
            if cond:
                return self._eval_node(node.body, context)
            return self._eval_node(node.orelse, context)

        # Subscript (dict/list indexing): inputs['key'], data[0]
        if isinstance(node, ast.Subscript):
            obj = self._eval_node(node.value, context)
            if isinstance(node.slice, ast.Constant):
                return obj[node.slice.value]
            elif isinstance(node.slice, ast.Name):
                idx = self._eval_node(node.slice, context)
                return obj[idx]
            else:
                idx = self._eval_node(node.slice, context)
                return obj[idx]

        # Attribute access (limited — only for known safe objects)
        if isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value, context)
            attr = node.attr
            # Allow .get() on dicts, .index() on lists, etc.
            if attr in ("get", "index", "keys", "values", "items", "upper", "lower", "strip"):
                return getattr(obj, attr)
            # Allow DataFrame-like .iloc, .loc, .columns
            if attr in ("iloc", "loc", "columns", "shape", "values"):
                return getattr(obj, attr)
            raise ValueError(f"Forbidden attribute access: .{attr}")

        # Function calls
        if isinstance(node, ast.Call):
            func = self._eval_node(node.func, context)
            args = [self._eval_node(a, context) for a in node.args]
            kwargs = {kw.arg: self._eval_node(kw.value, context) for kw in node.keywords}
            return func(*args, **kwargs)

        # List/tuple literals
        if isinstance(node, ast.List):
            return [self._eval_node(e, context) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(e, context) for e in node.elts)

        # Dict literals
        if isinstance(node, ast.Dict):
            return {
                self._eval_node(k, context): self._eval_node(v, context)
                for k, v in zip(node.keys, node.values)
            }

        # List comprehension (limited)
        if isinstance(node, ast.ListComp):
            return self._eval_listcomp(node, context)

        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def _eval_listcomp(self, node: ast.ListComp, context: dict) -> list:
        """Evaluate a simple list comprehension."""
        if len(node.generators) != 1:
            raise ValueError("Only single-generator list comprehensions supported")

        gen = node.generators[0]
        iterable = self._eval_node(gen.iter, context)
        results = []

        for item in iterable:
            local_ctx = {**context}
            if isinstance(gen.target, ast.Name):
                local_ctx[gen.target.id] = item
            else:
                raise ValueError("Only simple variable targets in comprehensions")

            # Check conditions
            passes = True
            for cond in gen.ifs:
                if not self._eval_node(cond, local_ctx):
                    passes = False
                    break

            if passes:
                results.append(self._eval_node(node.elt, local_ctx))

        return results


# ── Module-level singleton ───────────────────────────────────────────
formula_runtime = FormulaRuntime()
