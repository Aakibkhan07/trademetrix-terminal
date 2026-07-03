import logging
import operator
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Expr(ABC):
    @abstractmethod
    def evaluate(self, context: dict) -> Any:
        ...


class ValueExpr(Expr):
    def __init__(self, value: Any):
        self._value = value

    def evaluate(self, context: dict) -> Any:
        return self._value


class VariableExpr(Expr):
    def __init__(self, name: str):
        self._name = name

    def evaluate(self, context: dict) -> Any:
        parts = self._name.split(".")
        val = context
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = getattr(val, part, None)
            if val is None:
                return None
        return val


class BinaryExpr(Expr):
    def __init__(self, op: str, left: Expr, right: Expr):
        self._op = op
        self._left = left
        self._right = right
        self._ops = {
            "AND": lambda a, b: bool(a) and bool(b),
            "OR": lambda a, b: bool(a) or bool(b),
            ">": operator.gt,
            "<": operator.lt,
            ">=": operator.ge,
            "<=": operator.le,
            "==": operator.eq,
            "!=": operator.ne,
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "/": operator.truediv,
            "%": operator.mod,
            "POW": operator.pow,
        }

    def evaluate(self, context: dict) -> Any:
        left_val = self._left.evaluate(context)
        right_val = self._right.evaluate(context)
        op_func = self._ops.get(self._op)
        if not op_func:
            raise ValueError(f"Unknown operator: {self._op}")
        try:
            return op_func(left_val, right_val)
        except Exception as e:
            logger.debug("Expression evaluation error: %s", e)
            return None


class UnaryExpr(Expr):
    def __init__(self, op: str, operand: Expr):
        self._op = op
        self._operand = operand
        self._ops = {
            "NOT": lambda a: not bool(a),
            "-": lambda a: -a if a is not None else None,
            "+": lambda a: +a if a is not None else None,
        }

    def evaluate(self, context: dict) -> Any:
        val = self._operand.evaluate(context)
        op_func = self._ops.get(self._op)
        if not op_func:
            raise ValueError(f"Unknown unary operator: {self._op}")
        return op_func(val)


class IfElseExpr(Expr):
    def __init__(self, condition: Expr, then_expr: Expr, else_expr: Expr | None = None):
        self._condition = condition
        self._then = then_expr
        self._else = else_expr

    def evaluate(self, context: dict) -> Any:
        if self._condition.evaluate(context):
            return self._then.evaluate(context)
        if self._else:
            return self._else.evaluate(context)
        return None


class FunctionExpr(Expr):
    def __init__(self, name: str, args: list[Expr]):
        self._name = name
        self._args = args
        self._functions = _builtin_functions()

    def evaluate(self, context: dict) -> Any:
        func = self._functions.get(self._name)
        if not func:
            raise ValueError(f"Unknown function: {self._name}")
        arg_vals = [a.evaluate(context) for a in self._args]
        return func(*arg_vals)


class GroupExpr(Expr):
    def __init__(self, expressions: list[Expr], logic: str = "AND"):
        self._expressions = expressions
        self._logic = logic

    def evaluate(self, context: dict) -> Any:
        results = [e.evaluate(context) for e in self._expressions]
        if self._logic == "AND":
            return all(results)
        elif self._logic == "OR":
            return any(results)
        return results


def _builtin_functions() -> dict:
    import math
    return {
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "round": round,
        "sqrt": math.sqrt,
        "floor": math.floor,
        "ceil": math.ceil,
        "len": len,
        "str": str,
        "float": float,
        "int": int,
        "bool": bool,
        "crosses_above": _crosses_above,
        "crosses_below": _crosses_below,
        "between": _between,
        "percent_change": _percent_change,
    }


def _crosses_above(series1: list, series2: list | float) -> bool:
    if not isinstance(series1, list) or len(series1) < 2:
        return False
    target = series2 if isinstance(series2, (int, float)) else (series2[-1] if isinstance(series2, list) and series2 else 0)
    return series1[-2] <= target and series1[-1] > target


def _crosses_below(series1: list, series2: list | float) -> bool:
    if not isinstance(series1, list) or len(series1) < 2:
        return False
    target = series2 if isinstance(series2, (int, float)) else (series2[-1] if isinstance(series2, list) and series2 else 0)
    return series1[-2] >= target and series1[-1] < target


def _between(value: float, low: float, high: float) -> bool:
    return low <= value <= high


def _percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def parse_expression(expr_def: dict) -> Expr:
    expr_type = expr_def.get("type", "value")
    if expr_type == "value":
        return ValueExpr(expr_def.get("value"))
    elif expr_type == "variable":
        return VariableExpr(expr_def["name"])
    elif expr_type == "binary":
        return BinaryExpr(
            expr_def["op"],
            parse_expression(expr_def["left"]),
            parse_expression(expr_def["right"]),
        )
    elif expr_type == "unary":
        return UnaryExpr(
            expr_def["op"],
            parse_expression(expr_def["operand"]),
        )
    elif expr_type == "ifelse":
        return IfElseExpr(
            parse_expression(expr_def["condition"]),
            parse_expression(expr_def["then"]),
            parse_expression(expr_def.get("else")),
        )
    elif expr_type == "function":
        return FunctionExpr(
            expr_def["name"],
            [parse_expression(a) for a in expr_def.get("args", [])],
        )
    elif expr_type == "group":
        return GroupExpr(
            [parse_expression(e) for e in expr_def.get("expressions", [])],
            expr_def.get("logic", "AND"),
        )
    raise ValueError(f"Unknown expression type: {expr_type}")
