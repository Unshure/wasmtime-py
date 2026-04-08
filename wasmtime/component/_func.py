from .. import _ffi as ffi, WasmtimeError, Storelike
from ctypes import byref, pointer
import ctypes
from ._types import FuncType
from typing import Any
from ._enter import enter_wasm, poll_future, maybe_raise_last_exn


class Func:
    _func: ffi.wasmtime_component_func_t

    def __init__(self) -> None:
        raise WasmtimeError("Cannot directly construct a `Func`")

    @classmethod
    def _from_raw(cls, func: ffi.wasmtime_component_func_t) -> "Func":
        ty: "Func" = cls.__new__(cls)
        ty._func = func
        return ty

    def __call__(self, store: Storelike, *params: Any) -> Any:
        fty = self.type(store)
        param_tys = fty.params
        result_ty = fty.result
        if len(params) != len(param_tys):
            raise TypeError("wrong number of parameters provided: given %s, expected %s" %
                                (len(params), len(param_tys)))
        param_capi = (ffi.wasmtime_component_val_t * len(params))()
        n = 0
        try:
            for (_name, ty), val in zip(param_tys, params):
                ty.convert_to_c(store, val, pointer(param_capi[n]))
                n += 1
            result_space = None
            result_capi = None
            result_len = 0
            if result_ty is not None:
                result_space = ffi.wasmtime_component_val_t()
                result_capi = byref(result_space)
                result_len = 1

            def run() -> 'ctypes._Pointer[ffi.wasmtime_error_t]':
                return ffi.wasmtime_component_func_call(byref(self._func),
                                                        store._context(),
                                                        param_capi,
                                                        n,
                                                        result_capi,
                                                        result_len)
            enter_wasm(run)

            if result_space is None:
                return None
            assert(result_ty is not None)
            return result_ty.convert_from_c(result_space)

        finally:
            for i in range(n):
                ffi.wasmtime_component_val_delete(byref(param_capi[i]))


    async def call_async(self, store: Storelike, *params: Any) -> Any:
        """
        Invokes this function asynchronously with the given parameters.

        This is the same as `__call__` except it is asynchronous, polling the
        underlying future and yielding to the asyncio event loop between polls.
        Only compatible with stores associated with an async config.
        """
        fty = self.type(store)
        param_tys = fty.params
        result_ty = fty.result
        if len(params) != len(param_tys):
            raise TypeError("wrong number of parameters provided: given %s, expected %s" %
                                (len(params), len(param_tys)))
        param_capi = (ffi.wasmtime_component_val_t * len(params))()
        n = 0
        try:
            for (_name, ty), val in zip(param_tys, params):
                ty.convert_to_c(store, val, pointer(param_capi[n]))
                n += 1
            result_space = None
            result_capi = None
            result_len = 0
            if result_ty is not None:
                result_space = ffi.wasmtime_component_val_t()
                result_capi = byref(result_space)
                result_len = 1

            error_ptr = ctypes.POINTER(ffi.wasmtime_error_t)()
            future = ffi.wasmtime_component_func_call_async(
                byref(self._func),
                store._context(),
                param_capi,
                n,
                result_capi,
                result_len,
                byref(error_ptr))
            if not future:
                if error_ptr:
                    raise WasmtimeError._from_ptr(error_ptr)
                raise WasmtimeError("failed to create async call future")

            await poll_future(future)

            if error_ptr:
                error = WasmtimeError._from_ptr(error_ptr)
                maybe_raise_last_exn()
                raise error

            if result_space is None:
                return None
            assert(result_ty is not None)
            return result_ty.convert_from_c(result_space)

        finally:
            for i in range(n):
                ffi.wasmtime_component_val_delete(byref(param_capi[i]))

    def post_return(self, store: Storelike) -> None:
        """
        Performs any necessary post-return operations for this function.
        """
        def run() -> 'ctypes._Pointer[ffi.wasmtime_error_t]':
            return ffi.wasmtime_component_func_post_return(byref(self._func), store._context())
        enter_wasm(run)

    def type(self, store: Storelike) -> FuncType:
        """
        Returns the type of this function.
        """
        ptr = ffi.wasmtime_component_func_type(byref(self._func), store._context())
        return FuncType._from_ptr(ptr)
