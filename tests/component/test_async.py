import asyncio
import unittest
from dataclasses import dataclass
from typing import Any, List

from wasmtime import Config, Engine, Store, WasmtimeError
from wasmtime.component import (
    Component, Func, Linker, ResourceAny, ResourceHost, ResourceType,
    U32, Variant,
)


def create_async_config():
    """Helper to create a config with async support enabled."""
    config = Config()
    config.async_stack_size = 1024 * 1024
    config.wasm_component_model_async = True
    return config


def list_component(ty_wit: str):
    """Generate a component WAT that roundtrips a list type."""
    return f"""
        (component
            (import "x" (func $x (param "x" {ty_wit}) (result {ty_wit})))
            (core module $libc
                (memory (export "mem") 1)
                (global $base (mut i32) (i32.const 100))
                (func (export "realloc") (param i32 i32 i32 i32) (result i32)
                    (local $ret i32)
                    local.get 0
                    if unreachable end
                    local.get 1
                    if unreachable end

                    (local.set $ret (global.get $base))
                    (global.set $base
                        (i32.add
                            (global.get $base)
                            (local.get 2)))
                    local.get $ret)
            )
            (core instance $libc (instantiate $libc))
            (core module $a
                (import "" "x" (func (param i32 i32 i32)))
                (func (export "x") (param i32 i32)  (result i32)
                    local.get 0
                    local.get 1
                    i32.const 0
                    call 0
                    i32.const 0)
            )
            (core func $x (canon lower (func $x)
                (memory $libc "mem") (realloc (func $libc "realloc"))))
            (core instance $a (instantiate $a
                (with "" (instance
                    (export "x" (func $x))
                ))
            ))
            (func (export "x") (param "x" {ty_wit}) (result {ty_wit})
                (canon lift (core func $a "x") (memory $libc "mem")
                (realloc (func $libc "realloc"))))
        )
    """


def retptr_component(ty_wit: str, ty_wasm: str):
    """Generate a component WAT that roundtrips a type requiring retptr."""
    return f"""
        (component
            (type $t' {ty_wit})
            (import "t" (type $t (eq $t')))
            (import "x" (func $x (param "x" $t) (result $t)))
            (core module $libc (memory (export "mem") 1))
            (core instance $libc (instantiate $libc))
            (core module $a
                (import "" "x" (func (param {ty_wasm} i32)))
                (func (export "x") (param {ty_wasm})  (result i32)
                    local.get 0
                    local.get 1
                    i32.const 0
                    call 0
                    i32.const 0)
            )
            (core func $x (canon lower (func $x) (memory $libc "mem")))
            (core instance $a (instantiate $a
                (with "" (instance
                    (export "x" (func $x))
                ))
            ))
            (func (export "x") (param "x" $t) (result $t)
                (canon lift (core func $a "x") (memory $libc "mem")))
        )
    """


class TestAsyncConfig(unittest.TestCase):
    def test_async_config_properties(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        config.wasm_component_model_async_builtins = True
        config.wasm_component_model_async_stackful = True
        config.concurrency_support = True
        Engine(config)

    def test_async_config_type_errors(self):
        config = Config()
        with self.assertRaises(TypeError):
            config.async_stack_size = "not an int"
        with self.assertRaises(TypeError):
            config.wasm_component_model_async = 1
        with self.assertRaises(TypeError):
            config.concurrency_support = "yes"


class TestAsyncLinker(unittest.TestCase):
    def test_add_wasip2_async(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        engine = Engine(config)
        linker = Linker(engine)
        linker.add_wasip2_async()

    def test_add_wasi_http_async(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        engine = Engine(config)
        linker = Linker(engine)
        linker.add_wasip2_async()
        linker.add_wasi_http_async()

    def test_instantiate_async_fail(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (import "x" (func $x))
            )
        """)
        linker = Linker(engine)
        async def run():
            with self.assertRaises(WasmtimeError):
                await linker.instantiate_async(store, component)
        asyncio.run(run())

    def test_linker_locking_async(self):
        config = create_async_config()
        engine = Engine(config)
        linker = Linker(engine)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a (func (export "a")))
                (core instance $a (instantiate $a))
                (func (export "a") (canon lift (core func $a "a")))
            )
        """)
        with linker.root():
            with self.assertRaises(WasmtimeError):
                linker.add_wasip2_async()
            with self.assertRaises(WasmtimeError):
                linker.add_wasi_http_async()
            with self.assertRaises(WasmtimeError):
                asyncio.run(linker.instantiate_async(store, component))

    def test_add_wasip2_async_duplicate(self):
        config = create_async_config()
        engine = Engine(config)
        linker = Linker(engine)
        linker.add_wasip2_async()
        with self.assertRaises(WasmtimeError):
            linker.add_wasip2_async()
        linker.allow_shadowing = True
        linker.add_wasip2_async()


class TestAsyncFunc(unittest.TestCase):
    def test_call_async(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "a"))
                    (func (export "b") (param i32)
                        local.get 0
                        i32.const 100
                        i32.ne
                        if unreachable end)
                    (func (export "c") (result i32) (i32.const 101))
                )
                (core instance $a (instantiate $a))
                (func (export "a") (canon lift (core func $a "a")))
                (func (export "b") (param "x" u32) (canon lift (core func $a "b")))
                (func (export "c") (result u32) (canon lift (core func $a "c")))
            )
        """)
        instance = Linker(engine).instantiate(store, component)

        async def run():
            a = instance.get_func(store, 'a')
            assert a is not None
            ret = await a.call_async(store)
            self.assertIsNone(ret)

            b = instance.get_func(store, 'b')
            assert b is not None
            ret = await b.call_async(store, 100)
            self.assertIsNone(ret)

            c = instance.get_func(store, 'c')
            assert c is not None
            ret = await c.call_async(store)
            self.assertEqual(ret, 101)

        asyncio.run(run())

    def test_instantiate_async(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "a") (result i32) (i32.const 42))
                )
                (core instance $a (instantiate $a))
                (func (export "a") (result u32) (canon lift (core func $a "a")))
            )
        """)
        linker = Linker(engine)

        async def run():
            instance = await linker.instantiate_async(store, component)
            a = instance.get_func(store, 'a')
            assert a is not None
            ret = await a.call_async(store)
            self.assertEqual(ret, 42)

        asyncio.run(run())

    def test_host_func_roundtrip_async(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (import "x" (func $x (param "x" u32) (result u32)))
                (core module $a
                    (import "" "x" (func (param i32) (result i32)))
                    (func (export "x") (param i32) (result i32)
                        local.get 0
                        call 0)
                )
                (core func $x (canon lower (func $x)))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "x" (func $x))
                    ))
                ))
                (func (export "x") (param "x" u32) (result u32)
                    (canon lift (core func $a "x")))
            )
        """)

        def host_add_one(_store, val):
            return val + 1

        linker = Linker(engine)
        with linker.root() as l:
            l.add_func('x', host_add_one)

        async def run():
            instance = await linker.instantiate_async(store, component)
            f = instance.get_func(store, 'x')
            assert f is not None
            ret = await f.call_async(store, 41)
            self.assertEqual(ret, 42)

        asyncio.run(run())

    def test_async_host_func_roundtrip(self):
        config = Config()
        config.async_stack_size = 1024 * 1024
        config.wasm_component_model_async = True
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (import "x" (func $x (param "x" u32) (result u32)))
                (core module $a
                    (import "" "x" (func (param i32) (result i32)))
                    (func (export "x") (param i32) (result i32)
                        local.get 0
                        call 0)
                )
                (core func $x (canon lower (func $x)))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "x" (func $x))
                    ))
                ))
                (func (export "x") (param "x" u32) (result u32)
                    (canon lift (core func $a "x")))
            )
        """)

        async def async_host_add_one(_store, val):
            await asyncio.sleep(0)
            return val + 1

        linker = Linker(engine)
        with linker.root() as l:
            l.add_func_async('x', async_host_add_one)

        async def run():
            instance = await linker.instantiate_async(store, component)
            f = instance.get_func(store, 'x')
            assert f is not None
            ret = await f.call_async(store, 41)
            self.assertEqual(ret, 42)

        asyncio.run(run())

    # -- helpers for async type roundtrips --

    def roundtrip_async(self, wat: str, values: List[Any], bad=TypeError) -> None:
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, wat)
        value_being_tested = None

        def roundtrip(_store, val):
            self.assertEqual(value_being_tested, val)
            return val

        linker = Linker(engine)
        with linker.root() as l:
            l.add_func('x', roundtrip)

        async def run():
            nonlocal value_being_tested
            instance = await linker.instantiate_async(store, component)
            f = instance.get_func(store, 'x')
            assert f is not None
            for val in values:
                value_being_tested = val
                ret = await f.call_async(store, val)
                self.assertEqual(ret, val)
                f.post_return(store)

            class Bad:
                pass
            with self.assertRaises(bad):
                await f.call_async(store, Bad())

        asyncio.run(run())

    def roundtrip_simple_async(self, ty_wit: str, ty_wasm: str, values: List[Any]) -> None:
        wat = f"""
            (component
                (type $t' {ty_wit})
                (import "t" (type $t (eq $t')))
                (import "x" (func $x (param "x" $t) (result $t)))
                (core module $a
                    (import "" "x" (func (param {ty_wasm}) (result {ty_wasm})))
                    (func (export "x") (param {ty_wasm}) (result {ty_wasm})
                        local.get 0
                        call 0)
                )
                (core func $x (canon lower (func $x)))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "x" (func $x))
                    ))
                ))
                (func (export "x") (param "x" $t) (result $t)
                    (canon lift (core func $a "x")))
            )
        """
        self.roundtrip_async(wat, values)

    # -- error path tests --

    def test_call_async_wrong_param_count(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "b") (param i32)
                        local.get 0
                        i32.const 100
                        i32.ne
                        if unreachable end)
                )
                (core instance $a (instantiate $a))
                (func (export "b") (param "x" u32) (canon lift (core func $a "b")))
            )
        """)
        instance = Linker(engine).instantiate(store, component)
        b = instance.get_func(store, 'b')
        assert b is not None

        async def run():
            with self.assertRaises(TypeError):
                await b.call_async(store)
            with self.assertRaises(TypeError):
                await b.call_async(store, 1, 2)

        asyncio.run(run())

    def test_call_async_trap(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "b") (param i32)
                        local.get 0
                        i32.const 100
                        i32.ne
                        if unreachable end)
                )
                (core instance $a (instantiate $a))
                (func (export "b") (param "x" u32) (canon lift (core func $a "b")))
            )
        """)
        instance = Linker(engine).instantiate(store, component)
        b = instance.get_func(store, 'b')
        assert b is not None

        async def run():
            with self.assertRaises(WasmtimeError):
                await b.call_async(store, 999)

        asyncio.run(run())

    def test_call_async_post_return(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "c") (result i32) (i32.const 42))
                )
                (core instance $a (instantiate $a))
                (func (export "c") (result u32) (canon lift (core func $a "c")))
            )
        """)
        instance = Linker(engine).instantiate(store, component)
        c = instance.get_func(store, 'c')
        assert c is not None

        async def run():
            ret = await c.call_async(store)
            self.assertEqual(ret, 42)
            c.post_return(store)
            # Call again after post_return to verify cleanup
            ret = await c.call_async(store)
            self.assertEqual(ret, 42)
            c.post_return(store)

        asyncio.run(run())

    def test_call_async_multiple_sequential(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "c") (result i32) (i32.const 42))
                )
                (core instance $a (instantiate $a))
                (func (export "c") (result u32) (canon lift (core func $a "c")))
            )
        """)
        instance = Linker(engine).instantiate(store, component)
        c = instance.get_func(store, 'c')
        assert c is not None

        async def run():
            for _ in range(10):
                ret = await c.call_async(store)
                self.assertEqual(ret, 42)
                c.post_return(store)

        asyncio.run(run())

    @unittest.skip("async host func exception propagation blocked by ctypes finalizer bug in _linker.py")
    def test_async_host_func_exception(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (import "x" (func $x))
                (core module $a
                    (import "" "x" (func))
                    (func (export "x") call 0)
                )
                (core func $x (canon lower (func $x)))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "x" (func $x))
                    ))
                ))
                (func (export "x") (canon lift (core func $a "x")))
            )
        """)

        async def bad_host_func(_store):
            raise RuntimeError("async oh no")

        linker = Linker(engine)
        with linker.root() as l:
            l.add_func_async('x', bad_host_func)

        async def run():
            instance = await linker.instantiate_async(store, component)
            func = instance.get_func(store, 'x')
            assert func is not None
            with self.assertRaises(RuntimeError) as cm:
                await func.call_async(store)
            self.assertEqual(str(cm.exception), "async oh no")

        asyncio.run(run())

    def test_async_host_func_no_return(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (import "x" (func $x))
                (core module $a
                    (import "" "x" (func))
                    (func (export "x") call 0)
                )
                (core func $x (canon lower (func $x)))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "x" (func $x))
                    ))
                ))
                (func (export "x") (canon lift (core func $a "x")))
            )
        """)
        called = [False]

        async def async_noop(_store):
            await asyncio.sleep(0)
            called[0] = True

        linker = Linker(engine)
        with linker.root() as l:
            l.add_func_async('x', async_noop)

        async def run():
            instance = await linker.instantiate_async(store, component)
            func = instance.get_func(store, 'x')
            assert func is not None
            ret = await func.call_async(store)
            self.assertIsNone(ret)
            self.assertTrue(called[0])

        asyncio.run(run())

    def test_concurrent_async_calls(self):
        config = create_async_config()
        engine = Engine(config)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "c") (result i32) (i32.const 42))
                )
                (core instance $a (instantiate $a))
                (func (export "c") (result u32) (canon lift (core func $a "c")))
            )
        """)

        async def run():
            async def call_once():
                store = Store(engine)
                instance = Linker(engine).instantiate(store, component)
                c = instance.get_func(store, 'c')
                assert c is not None
                ret = await c.call_async(store)
                c.post_return(store)
                return ret

            results = await asyncio.gather(
                call_once(), call_once(), call_once(), call_once(), call_once()
            )
            self.assertEqual(results, [42, 42, 42, 42, 42])

        asyncio.run(run())

    # -- type roundtrip tests --

    def test_call_async_roundtrip_primitive(self):
        self.roundtrip_simple_async('bool', 'i32', [True, False])
        self.roundtrip_simple_async('u8', 'i32', [0, 1, 42, 255])
        self.roundtrip_simple_async('u16', 'i32', [0, 1, 42, 65535])
        self.roundtrip_simple_async('u32', 'i32', [0, 1, 42, 4294967295])
        self.roundtrip_simple_async('u64', 'i64', [0, 1, 42, 18446744073709551615])
        self.roundtrip_simple_async('s8', 'i32', [0, 1, -1, 42, -42, 127, -128])
        self.roundtrip_simple_async('s16', 'i32', [0, 1, -1, 42, -42, 32767, -32768])
        self.roundtrip_simple_async('s32', 'i32', [0, 1, -1, 42, -42, 2147483647, -2147483648])
        self.roundtrip_simple_async('s64', 'i64', [0, 1, -1, 42, -42, 9223372036854775807, -9223372036854775808])
        self.roundtrip_simple_async('f32', 'f32', [0.0, 1.0, -1.0])
        self.roundtrip_simple_async('f64', 'f64', [0.0, 1.0, -1.0])
        self.roundtrip_simple_async('char', 'i32', ['a', 'b'])

    def test_call_async_roundtrip_string(self):
        wat = list_component('string')
        self.roundtrip_async(wat, ['', 'a', 'hello, world!'])

    def test_call_async_roundtrip_list(self):
        wat = list_component('(list u8)')
        self.roundtrip_async(wat, [b'', b'a', b'hello, world!'])
        wat = list_component('(list u32)')
        self.roundtrip_async(wat, [[], [1], [1, 2, 3, 4, 5]])
        with self.assertRaises(TypeError):
            self.roundtrip_async(wat, [[1, 2, 3, 'x']])

    def test_call_async_roundtrip_record(self):
        ty_wit = '(record (field "a" u32) (field "b" bool))'
        ty_wasm = 'i32 i32'
        wat = retptr_component(ty_wit, ty_wasm)

        @dataclass
        class Record:
            a: int
            b: bool
        values = [
            Record(0, False),
            Record(1, True),
            Record(42, False),
            Record(65535, True)
        ]
        self.roundtrip_async(wat, values, bad=AttributeError)

        @dataclass
        class RecordBad:
            a: int
        with self.assertRaises(AttributeError):
            self.roundtrip_async(wat, [RecordBad(0)])

    def test_call_async_roundtrip_tuple(self):
        ty_wit = '(tuple u32 bool)'
        ty_wasm = 'i32 i32'
        wat = retptr_component(ty_wit, ty_wasm)
        values = [(0, False), (1, True), (42, False), (65535, True)]
        self.roundtrip_async(wat, values)
        with self.assertRaises(TypeError):
            self.roundtrip_async(wat, [(0,)])
        with self.assertRaises(TypeError):
            self.roundtrip_async(wat, [(0, 'x')])

    def test_call_async_roundtrip_enum(self):
        self.roundtrip_simple_async('(enum "a" "b" "c")', 'i32', ['a', 'b', 'c'])
        with self.assertRaises(WasmtimeError):
            self.roundtrip_simple_async('(enum "a" "b" "c")', 'i32', ['d'])

    def test_call_async_roundtrip_flags(self):
        vals = [{'a'}, {'b'}, {'c'}, {'a', 'b'}, {'a', 'c'}, {'b', 'c'}]
        self.roundtrip_simple_async('(flags "a" "b" "c")', 'i32', vals)
        with self.assertRaises(WasmtimeError):
            self.roundtrip_simple_async('(flags "a" "b" "c")', 'i32', [{'d'}])

    def test_call_async_roundtrip_variant(self):
        self.roundtrip_simple_async('(variant (case "a") (case "b"))',
                                    'i32',
                                    [Variant('a'), Variant('b')])
        with self.assertRaises(ValueError):
            self.roundtrip_simple_async('(variant (case "a") (case "b"))',
                                        'i32',
                                        [Variant('c')])
        wat = retptr_component('(variant (case "a" u32) (case "b" u64))', 'i32 i64')
        self.roundtrip_async(wat, [Variant('a', 1), Variant('b', 2)])
        wat = retptr_component('(variant (case "a" u32) (case "b" f32))', 'i32 i32')
        self.roundtrip_async(wat, [1, 2.], bad=ValueError)
        wat = retptr_component('(variant (case "a") (case "b" f32))', 'i32 f32')
        self.roundtrip_async(wat, [None, 2.], bad=ValueError)

    def test_call_async_roundtrip_option(self):
        wat = retptr_component('(option u32)', 'i32 i32')
        self.roundtrip_async(wat, [None, 3, 0], bad=ValueError)

    def test_call_async_roundtrip_result(self):
        wat = retptr_component('(result u32 (error f32))', 'i32 i32')
        self.roundtrip_async(wat, [3, 1.], bad=ValueError)
        wat = retptr_component('(result u32)', 'i32 i32')
        self.roundtrip_async(wat, [3, None], bad=ValueError)
        wat = retptr_component('(result (error f32))', 'i32 f32')
        self.roundtrip_async(wat, [3., None], bad=ValueError)
        self.roundtrip_simple_async('(result)', 'i32', [Variant('ok'), Variant('err')])

    # -- parity with test_func sync tests --

    def test_roundtrip_empty_async(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (import "x" (func $x))
                (core module $a
                    (import "" "x" (func))
                    (func (export "x") call 0)
                )
                (core func $x (canon lower (func $x)))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "x" (func $x))
                    ))
                ))
                (func (export "x") (canon lift (core func $a "x")))
            )
        """)

        linker = Linker(engine)
        with linker.root() as l:
            l.add_func('x', lambda _store: None)

        async def run():
            instance = await linker.instantiate_async(store, component)
            f = instance.get_func(store, 'x')
            assert f is not None
            self.assertIsNone(await f.call_async(store))
            f.post_return(store)

        asyncio.run(run())

    def test_type_reflection_async(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, """
            (component
                (core module $a
                    (func (export "a"))
                    (func (export "b") (param i32) (result i32) unreachable)
                )
                (core instance $a (instantiate $a))
                (func (export "a") (canon lift (core func $a "a")))
                (func (export "b") (param "x" u32) (result u32)
                    (canon lift (core func $a "b")))
            )
        """)

        async def run():
            instance = await Linker(engine).instantiate_async(store, component)
            ai = instance.get_export_index(store, 'a')
            bi = instance.get_export_index(store, 'b')
            assert ai is not None
            assert bi is not None
            a = instance.get_func(store, ai)
            b = instance.get_func(store, bi)
            assert a is not None
            assert b is not None
            self.assertEqual(a.type(store).params, [])
            self.assertIsNone(a.type(store).result)
            self.assertEqual(b.type(store).params, [('x', U32())])
            self.assertEqual(b.type(store).result, U32())

        asyncio.run(run())

    def test_resources_async(self):
        config = create_async_config()
        engine = Engine(config)
        store = Store(engine)
        component = Component(engine, f"""
            (component
                (import "t" (type $t (sub resource)))
                (import "mk" (func $mk (result (own $t))))
                (import "borrow" (func $borrow (param "t" (borrow $t))))
                (import "own" (func $own (param "t" (own $t))))
                (core module $a
                    (import "" "mk" (func $mk (result i32)))
                    (import "" "borrow" (func $borrow (param i32)))
                    (import "" "own" (func $own (param i32)))
                    (import "" "drop" (func $drop (param i32)))

                    (func (export "mk") (result i32) call $mk)
                    (func (export "borrow") (param i32)
                        (call $borrow (local.get 0))
                        (call $drop (local.get 0)))
                    (func (export "own") (param i32) local.get 0 call $own)
                )
                (core func $mk (canon lower (func $mk)))
                (core func $borrow (canon lower (func $borrow)))
                (core func $own (canon lower (func $own)))
                (core func $drop (canon resource.drop $t))
                (core instance $a (instantiate $a
                    (with "" (instance
                        (export "mk" (func $mk))
                        (export "borrow" (func $borrow))
                        (export "own" (func $own))
                        (export "drop" (func $drop))
                    ))
                ))
                (func (export "mk") (result (own $t))
                    (canon lift (core func $a "mk")))
                (func (export "borrow") (param "x" (borrow $t))
                    (canon lift (core func $a "borrow")))
                (func (export "own") (param "x" (own $t))
                    (canon lift (core func $a "own")))
            )
        """)

        ty = ResourceType.host(2)

        def mk(_store):
            return ResourceHost.own(1, 2)

        def borrow(_store, b):
            self.assertFalse(b.owned)
            handle = b.to_host(store)
            self.assertEqual(handle.type, 2)

        def own(_store, b):
            self.assertTrue(b.owned)

        linker = Linker(engine)
        with linker.root() as l:
            l.add_resource('t', ty, lambda _store, _rep: None)
            l.add_func('mk', mk)
            l.add_func('borrow', borrow)
            l.add_func('own', own)

        async def run():
            instance = await linker.instantiate_async(store, component)
            f_mk = instance.get_func(store, 'mk')
            f_borrow = instance.get_func(store, 'borrow')
            f_own = instance.get_func(store, 'own')
            assert f_mk is not None
            assert f_borrow is not None
            assert f_own is not None

            r1 = await f_mk.call_async(store)
            self.assertIsInstance(r1, ResourceAny)
            f_mk.post_return(store)
            await f_borrow.call_async(store, r1)
            f_borrow.post_return(store)
            await f_borrow.call_async(store, ResourceHost.own(1, 2))
            f_borrow.post_return(store)
            await f_own.call_async(store, r1)
            f_own.post_return(store)
            await f_own.call_async(store, ResourceHost.own(1, 2))
            f_own.post_return(store)

            with self.assertRaises(TypeError):
                await f_borrow.call_async(store, 1)

            with self.assertRaises(TypeError):
                await f_own.call_async(store, 1)

        asyncio.run(run())
