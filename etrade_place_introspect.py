# etrade_place_introspect.py — print signatures, docstrings, and (if available) source for E*TRADE wrapper fns.
import inspect
import textwrap

from services import etrade_service as et


def dump_fn(name):
    fn = getattr(et, name, None)
    print(f"\n=== {name} ===")
    if fn is None:
        print("not found")
        return
    try:
        sig = inspect.signature(fn)
        print("signature:", sig)
    except Exception as e:
        print("signature: <unavailable>", e)
    print("annotations:", getattr(fn, "__annotations__", {}))
    print("docstring:\n", (inspect.getdoc(fn) or "<none>"))
    try:
        src = inspect.getsource(fn)
        print("\nsource:\n", textwrap.dedent(src))
    except Exception as e:
        print("\nsource: <unavailable>", e)


for n in [
    "preview_equity_order",
    "place_equity_order",
    "list_open_orders",
    "get_open_orders",
    "list_executed_orders",
    "list_executed_orders_today",
]:
    dump_fn(n)
