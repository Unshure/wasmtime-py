import asyncio
import ctypes
from .. import _ffi as ffi, StoreContext, WasmtimeError
from typing import Optional, Callable


LAST_EXCEPTION: Optional[Exception] = None


def catch_exceptions(store_raw: 'ctypes._Pointer[ffi.wasmtime_context_t]', func: Callable[[StoreContext], None]) -> ctypes.c_size_t:
    store = StoreContext(store_raw)
    exception = None
    try:
        func(store)
    except WasmtimeError as e:
        exception = e
    except Exception as e:
        global LAST_EXCEPTION
        LAST_EXCEPTION = e
        exception = WasmtimeError("python exception")
    finally:
        store._invalidate()

    if exception:
        return ctypes.cast(exception._consume(), ctypes.c_void_p).value # type: ignore
    return 0 # type: ignore


def enter_wasm(func: Callable[[], 'ctypes._Pointer[ffi.wasmtime_error_t]']) -> None:
    ptr = func()
    if ptr:
        error = WasmtimeError._from_ptr(ptr)
        maybe_raise_last_exn()
        raise error


def maybe_raise_last_exn() -> None:
    global LAST_EXCEPTION
    if LAST_EXCEPTION is None:
        return
    exn = LAST_EXCEPTION
    LAST_EXCEPTION = None
    raise exn


async def poll_future(future: 'ctypes._Pointer[ffi.wasmtime_call_future_t]') -> None:
    """
    Poll a wasmtime_call_future_t until completion, yielding to the asyncio
    event loop between polls.

    The future is deleted when polling completes or on error.
    """
    try:
        while not ffi.wasmtime_call_future_poll(future):
            await asyncio.sleep(0)
    finally:
        ffi.wasmtime_call_future_delete(future)
